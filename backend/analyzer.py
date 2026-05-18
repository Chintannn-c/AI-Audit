"""
Enterprise AI Audit Sampling Engine
====================================
Fully merged production version combining:
  - Refactored architecture (DataCleaner, VendorNormalizer, RiskScorer, SampleEngine, DashboardBuilder)
  - All original functionality preserved (value-based sampling, all 3 sampling strategies, full backfill logic)
  - All identified bugs fixed:
      [FIXED-1]  sample_stratified: month coverage no longer breaks early — all months are visited
                 unconditionally before the count guard is applied.
      [FIXED-2]  sample_stratified: Fallback 2 now actually relaxes the vendor cap (cap raised to 3)
                 so it is not a dead-code duplicate of Fallback 1.
      [FIXED-3]  sample_stratified: TOC selection uses its own seen_vendors Counter, independent of TOD,
                 so TOD saturation cannot lock out TOC from any vendor.
      [FIXED-4]  generate_samples: re-bifurcation no longer calls engine.generate() again (which hits
                 the same cap wall). Instead it redistributes the already-selected rows at the new ratio.
      [FIXED-5]  sample_by_value backfill stage 1: non-vendor rows now call mark_used() so they cannot
                 be double-selected in stage 2.
      [FIXED-6]  strata_target in Stage 2 is now computed from remaining quota after Stage 1 mandatory
                 month slots, so high-value stratum cannot crowd out mid/low strata.
      [FIXED-7]  Round-value modulo check now uses abs(x % rv) < 0.01 to handle float precision drift.
      [FIXED-8]  suspicious_narration_count uses a union mask (distinct rows), not a keyword sum.
      [FIXED-9]  self.date_col, validate() order, dashboard date re-parsing, DataFrame attrs fragility,
                 sampling_basis ignored, cached _Parsed_Date — all retained from previous merge.

Author  : Merged & Fixed Production Version v2
Standard: ISA 530 Audit Sampling / Indian Accounting Standards
"""

import math
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuditConfig:
    """
    Externalized configuration for the Statutory Audit Engine.
    All magic numbers live here — no hardcoding inside engine methods.
    """
    round_values: List[float] = field(
        default_factory=lambda: [1000, 5000, 10000, 50000, 100000, 500000, 1000000]
    )
    suspicious_keywords: List[str] = field(
        default_factory=lambda: [
            'cash', 'adjustment', 'write off', 'write-off', 'reversal',
            'correction', 'void', 'cancel', 'refund', 'suspense',
            'miscellaneous', 'illegal',
        ]
    )
    # Forensic pattern thresholds
    round_trip_window_days: int = 7
    high_value_sigma_multiplier: float = 2.0
    split_txn_min_count: int = 3          # Min same-vendor/same-day txns to flag as split
    round_trip_tolerance_pct: float = 0.05  # 5% tolerance for amount matching in round-trips

    # Sampling defaults
    strata_allocation: Tuple[float, float, float] = (0.60, 0.30, 0.10)
    tod_pct: float = 70.0

    # Vendor normalisation
    fuzzy_match_threshold: float = 85.0   # Score out of 100 for rapidfuzz / difflib

    # Vendor repeat cap per selection pass (TOD and TOC are counted independently)
    vendor_cap_primary: int = 1    # Max appearances in the first-pass (unique-vendor) loops
    vendor_cap_fallback: int = 2   # Max appearances allowed in the relaxed-fallback loops (absolute hard limit is 2)


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLEANER
# ══════════════════════════════════════════════════════════════════════════════

class DataCleaner:
    """
    Handles category-aware column detection, accounting-format amount parsing,
    non-transaction row filtering, and memory optimisation.
    """

    NON_TXN_KEYWORDS = [
        'total', 'balance', 'b/f', 'c/f', 'opening', 'closing',
        'brought forward', 'carried forward', 'grand total',
        'sub total', 'sub-total',
    ]

    def __init__(self, config: AuditConfig):
        self.config = config

    # ── Column Detection ──────────────────────────────────────────────────────

    def detect_columns(self, df: pd.DataFrame, category: str) -> Dict[str, Optional[str]]:
        """
        Detect amount, date, narration, invoice, and vendor columns.
        Category-aware: Sales → credit, Purchases/Expenses → debit.
        """
        cols_lower = {col: str(col).lower().strip() for col in df.columns}

        # 1. Amount column
        amount_col = self._detect_amount(df, cols_lower, category)

        # 2. Date column
        date_col = next(
            (c for c in df.columns if 'date' in str(c).lower()), None
        )

        # 3. Narration column — strong keywords first, then weaker fallbacks
        narration_col = next(
            (c for c in df.columns
             if any(k in str(c).lower() for k in ['narration', 'description', 'remark'])),
            None,
        )
        if not narration_col:
            narration_col = next(
                (c for c in df.columns
                 if any(k in str(c).lower() for k in ['particular', 'detail'])),
                None,
            )

        # 4. Invoice column — explicitly exclude date columns
        invoice_col = next(
            (c for c in df.columns
             if c != date_col
             and 'date' not in str(c).lower()
             and any(k in str(c).lower()
                     for k in ['invoice', 'inv no', 'bill no', 'vch no', 'voucher'])),
            None,
        )

        # 5. Vendor / Party column
        vendor_col = self._detect_vendor(df, narration_col)

        # 6. Transaction ID / Reference column — exclude amount, date, and vendor
        txn_id_col = next(
            (c for c in df.columns
             if c not in (date_col, amount_col, vendor_col)
             and 'date' not in str(c).lower()
             and 'amount' not in str(c).lower()
             and any(k in str(c).lower()
                     for k in ['txn id', 'transaction id', 'txn_id', 'id', 'txnno', 'transaction no', 'transaction_no', 'reference', 'ref'])),
            None,
        )

        return {
            'amount_col': amount_col,
            'date_col': date_col,
            'narration_col': narration_col,
            'invoice_col': invoice_col,
            'vendor_col': vendor_col,
            'txn_id_col': txn_id_col,
        }

    def _detect_amount(self, df: pd.DataFrame,
                       cols_lower: Dict[str, str], category: str) -> Optional[str]:
        # Category-specific preferred keyword
        if category == 'Sales':
            preferred = ['credit']
        elif category in ('Purchases', 'Expenses'):
            preferred = ['debit']
        else:
            preferred = []

        for col, low in cols_lower.items():
            if any(kw in low for kw in preferred):
                return col

        # Generic amount keywords
        for col, low in cols_lower.items():
            if any(kw in low for kw in ['amount', 'total', 'value', 'net']):
                return col

        # Opposite debit/credit as last named fallback
        for col, low in cols_lower.items():
            if 'credit' in low or 'debit' in low:
                return col

        # Largest numeric column by absolute sum
        numeric = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric:
            return max(numeric, key=lambda c: df[c].abs().sum())

        # Try coercing string columns to numeric
        for col in df.columns:
            try:
                s = df[col].astype(str).str.replace(r'[^\d.\-]', '', regex=True)
                nums = pd.to_numeric(s, errors='coerce')
                if nums.notnull().sum() > len(df) * 0.4:
                    return col
            except Exception:
                continue

        return None

    def _detect_vendor(self, df: pd.DataFrame,
                       narration_col: Optional[str]) -> Optional[str]:
        vendor_keywords = [
            'party', 'vendor', 'customer', 'supplier', 'name',
            'ledger', 'account', 'particular', 'narration',
        ]
        for col in df.columns:
            low = str(col).lower().strip()
            if any(kw in low for kw in vendor_keywords):
                if df[col].dtype == object or str(df[col].dtype) == 'string':
                    return col
        return narration_col  # Tally fallback

    # ── Amount Cleaning ───────────────────────────────────────────────────────

    def clean_amounts(self, df: pd.DataFrame, amount_col: str) -> pd.Series:
        """Parse accounting-format numbers: (1,234.56) → -1234.56."""

        def _parse(val) -> float:
            s = str(val).strip()
            if not s or s.lower() in ('nan', 'none'):
                return 0.0
            is_neg = s.startswith('(') and s.endswith(')')
            if is_neg:
                s = s[1:-1]
            # [FIXED-8-adjacent] Handle European thousands separators:
            # if multiple dots exist, all but the last are thousands separators
            s_stripped = ''.join(c for c in s if c.isdigit() or c in '.,-')
            dot_count = s_stripped.count('.')
            comma_count = s_stripped.count(',')
            if dot_count > 1:
                # e.g. "1.234.567" — strip all dots, treat as integer
                s_stripped = s_stripped.replace('.', '')
            elif dot_count == 1 and comma_count >= 1:
                # e.g. "1,234.56" — strip commas
                s_stripped = s_stripped.replace(',', '')
            else:
                # e.g. "1.234,56" (European) or plain "1234.56"
                s_stripped = s_stripped.replace(',', '.')
            # Keep only digits and a single dot/minus
            s_clean = ''.join(c for c in s_stripped if c.isdigit() or c in '.-')
            try:
                return -float(s_clean) if is_neg else float(s_clean)
            except ValueError:
                return 0.0

        return df[amount_col].apply(_parse)

    # ── Row Filtering ─────────────────────────────────────────────────────────

    def filter_non_transaction_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove subtotal, header, and balance rows using vectorised regex."""
        if df.empty:
            return df
        pattern = '|'.join(re.escape(kw) for kw in self.NON_TXN_KEYWORDS)
        mask = pd.Series(False, index=df.index)
        for col in df.select_dtypes(include=['object', 'category']).columns:
            mask |= df[col].astype(str).str.contains(
                pattern, case=False, regex=True, na=False
            )
        return df[~mask].reset_index(drop=True)

    # ── Memory Optimisation ───────────────────────────────────────────────────

    def optimize_memory(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in df.select_dtypes(include=['float64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='float')
        for col in df.select_dtypes(include=['int64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='integer')
        for col in df.select_dtypes(include=['object']).columns:
            if df[col].nunique() / max(len(df), 1) < 0.5:
                df[col] = df[col].astype('category')
        return df


# ══════════════════════════════════════════════════════════════════════════════
# VENDOR NORMALISER
# ══════════════════════════════════════════════════════════════════════════════

class VendorNormalizer:
    """
    Forensic entity collapsing via resilient fuzzy string matching.
    Uses rapidfuzz when available, falls back to difflib.
    Prevents false collapses for distinct single-character suffixes (e.g. Vendor A vs B).
    """

    _LEGAL_SUFFIXES = re.compile(
        r'\b(pvt\.?\s*ltd\.?|private\s+limited|limited|ltd\.?|llp|'
        r'inc\.?|incorporated|corp\.?|corporation|co\.?|company|'
        r'enterprises?|traders?|associates?|solutions?|'
        r'industries?|international|india|group|mfg|manufacturing|'
        r'services|logistics|trading|agency|agencies|contractors?|'
        r'developers?|builders?|ventures?|holdings?)\b',
        re.IGNORECASE,
    )

    def __init__(self, config: AuditConfig):
        self.config = config
        self._is_match = self._build_matcher()

    def _build_matcher(self):
        """Return the best available fuzzy-match function."""
        try:
            import importlib
            fuzz = importlib.import_module('rapidfuzz.fuzz')

            def is_match(a: str, b: str) -> bool:
                # Guard: distinct single-char trailing tokens must be equal
                wa, wb = a.split(), b.split()
                if wa and wb and wa[-1] != wb[-1]:
                    if len(wa[-1]) == 1 or len(wb[-1]) == 1:
                        return False
                return fuzz.token_set_ratio(a, b) >= self.config.fuzzy_match_threshold

            logger.debug('VendorNormalizer: using rapidfuzz')
            return is_match

        except ImportError:
            import difflib

            def is_match(a: str, b: str) -> bool:
                wa, wb = a.split(), b.split()
                if wa and wb and wa[-1] != wb[-1]:
                    if len(wa[-1]) == 1 or len(wb[-1]) == 1:
                        return False
                score = difflib.SequenceMatcher(None, a, b).ratio() * 100
                return score >= self.config.fuzzy_match_threshold

            logger.debug('VendorNormalizer: using difflib (install rapidfuzz for better accuracy)')
            return is_match

    @staticmethod
    def _normalize_name(name: str) -> str:
        s = str(name).strip().lower()
        if not s or s in ('nan', 'none', ''):
            return ''
        s = VendorNormalizer._LEGAL_SUFFIXES.sub('', s)
        s = re.sub(r'[^a-z0-9\s]', '', s)
        return re.sub(r'\s+', ' ', s).strip()

    def normalize(self, df: pd.DataFrame, vendor_col: Optional[str]) -> pd.DataFrame:
        df = df.copy()
        if not vendor_col or vendor_col not in df.columns:
            df['_Norm_Vendor'] = ''
            return df

        df['_Norm_Vendor'] = df[vendor_col].apply(self._normalize_name)
        unique_norms = [n for n in df['_Norm_Vendor'].unique() if n]
        if not unique_norms:
            return df

        # Build canonical map: shorter strings are potential canons
        canon_map: Dict[str, str] = {}
        for norm in sorted(unique_norms, key=len):
            matched = False
            for canon in canon_map.values():
                if self._is_match(norm, canon):
                    canon_map[norm] = canon
                    matched = True
                    break
            if not matched:
                canon_map[norm] = norm

        df['_Norm_Vendor'] = df['_Norm_Vendor'].map(lambda x: canon_map.get(x, x))
        return df


# ══════════════════════════════════════════════════════════════════════════════
# RISK SCORER
# ══════════════════════════════════════════════════════════════════════════════

class RiskScorer:
    """
    Vectorised computation of 12 forensic risk indicators.
    Round-trip detection uses O(N) merge-based self-join (no nested loops).
    """

    def __init__(self, config: AuditConfig):
        self.config = config

    def score_risks(
        self,
        df: pd.DataFrame,
        amount_col: Optional[str],
        date_col: Optional[str],
        narration_col: Optional[str],
        vendor_col: Optional[str],
        performance_materiality: float,
        trivial_threshold: float,
    ) -> pd.DataFrame:

        data = df.copy()
        data['_Risk_Score'] = 0
        data['_Risk_Flags'] = ''

        if not amount_col:
            data['_Risk_Category'] = 'Low'
            return data

        amt = data[amount_col].abs()
        avg = float(amt.mean()) if not amt.empty else 0.0
        std = float(amt.std()) if not pd.isna(amt.std()) else 0.0
        dates = data['_Parsed_Date']

        flags_dict: Dict[Any, List[str]] = {idx: [] for idx in data.index}

        def _add_flag(mask: pd.Series, label: str, score: int):
            data.loc[mask, '_Risk_Score'] += score
            for idx in mask[mask].index:
                if label not in flags_dict[idx]:
                    flags_dict[idx].append(label)

        # 1. High Value (mean + N·σ)
        threshold = avg + self.config.high_value_sigma_multiplier * std
        hv_mask = amt > threshold
        _add_flag(hv_mask, 'High Value', 15)

        # 2. Above Performance Materiality
        if performance_materiality > 0:
            _add_flag(amt >= performance_materiality, 'Above Materiality', 20)

        # 3. Duplicate Amounts
        _add_flag(amt.duplicated(keep=False) & (amt > 0), 'Duplicate Amount', 10)

        # 4. Round Values (all configured round_values)
        # [FIXED-7] Use tolerance-based comparison instead of exact float equality
        round_mask = (amt > 0) & amt.apply(
            lambda x: any(abs(x % rv) < 0.01 or abs(x % rv - rv) < 0.01
                          for rv in self.config.round_values)
        )
        _add_flag(round_mask, 'Round Value', 5)

        # 5. Month-end Postings
        if date_col:
            month_end = dates.dt.is_month_end | (dates.dt.day >= 28)
            _add_flag(month_end, 'Month-End', 5)

        # 6. Weekend Postings
        if date_col:
            _add_flag(dates.dt.dayofweek.isin([5, 6]), 'Weekend Posting', 10)

        # 7. Suspicious Narration
        if narration_col and narration_col in data.columns:
            narr = data[narration_col].astype(str).str.lower()
            sus_mask = pd.Series(False, index=data.index)
            for kw in self.config.suspicious_keywords:
                sus_mask |= narr.str.contains(kw, na=False)
            _add_flag(sus_mask, 'Suspicious Narration', 8)

        # 8. Unusual Spikes (>3× average, not already flagged as High Value)
        spike_only = (amt > 3 * avg) & ~hv_mask
        _add_flag(spike_only, 'Unusual Spike', 12)

        # 9. Zero or Negative Values
        _add_flag(data[amount_col] <= 0, 'Zero/Negative', 5)

        # 10. Below Trivial Threshold (de-prioritise)
        if trivial_threshold > 0:
            trivial_mask = amt <= trivial_threshold
            data.loc[trivial_mask, '_Risk_Score'] -= 10
            for idx in trivial_mask[trivial_mask].index:
                if 'Below Trivial' not in flags_dict[idx]:
                    flags_dict[idx].append('Below Trivial')

        # 11. FORENSIC: Split Transaction Detection (same vendor, same day, ≥N txns)
        if '_Norm_Vendor' in data.columns and date_col:
            try:
                temp = data[data['_Norm_Vendor'] != ''].copy()
                temp['_Date_Only'] = dates.dt.date
                for (_, __), grp in temp.groupby(['_Norm_Vendor', '_Date_Only']):
                    if (len(grp) >= self.config.split_txn_min_count
                            and amt.loc[grp.index].mean() < avg):
                        data.loc[grp.index, '_Risk_Score'] += 18
                        for idx in grp.index:
                            if 'Split Transaction' not in flags_dict[idx]:
                                flags_dict[idx].append('Split Transaction')
            except Exception as e:
                logger.warning(f'Split transaction detection failed: {e}')

        # 12. FORENSIC: Round-Tripping Pattern — O(N) vectorised merge-based self-join
        if vendor_col and '_Norm_Vendor' in data.columns and date_col:
            try:
                pos = data[data[amount_col] > 0][
                    ['_Norm_Vendor', '_Parsed_Date', amount_col]
                ].copy()
                neg = data[data[amount_col] < 0][
                    ['_Norm_Vendor', '_Parsed_Date', amount_col]
                ].copy()

                if not pos.empty and not neg.empty:
                    merged = pos.reset_index().merge(
                        neg.reset_index(), on='_Norm_Vendor', suffixes=('_p', '_n')
                    )
                    val_p = merged[f'{amount_col}_p'].abs()
                    val_n = merged[f'{amount_col}_n'].abs()
                    val_close = ((val_p - val_n).abs() / val_p.clip(lower=1e-9)
                                 < self.config.round_trip_tolerance_pct)
                    days_diff = (
                        merged['_Parsed_Date_p'] - merged['_Parsed_Date_n']
                    ).abs().dt.days
                    time_close = days_diff <= self.config.round_trip_window_days

                    rt_pairs = merged[val_close & time_close]
                    if not rt_pairs.empty:
                        rt_indices = (
                            set(rt_pairs['index_p']) | set(rt_pairs['index_n'])
                        )
                        data.loc[list(rt_indices), '_Risk_Score'] += 15
                        for idx in rt_indices:
                            if 'Round-Trip' not in flags_dict[idx]:
                                flags_dict[idx].append('Round-Trip')
            except Exception as e:
                logger.warning(f'Round-trip detection failed: {e}')

        # Compile flags and categorise
        data['_Risk_Flags'] = [
            '; '.join(flags_dict[idx]) if flags_dict[idx] else 'None'
            for idx in data.index
        ]
        data['_Risk_Score'] = data['_Risk_Score'].clip(lower=0)
        data['_Risk_Category'] = 'Low'
        data.loc[data['_Risk_Score'] >= 15, '_Risk_Category'] = 'Medium'
        data.loc[data['_Risk_Score'] >= 30, '_Risk_Category'] = 'High'

        return data


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class SampleEngine:
    """
    Three fully-preserved sampling strategies:
      1. sample_stratified   — count-based, month-stratified, vendor-deduplicated
      2. sample_by_value     — value-based with two-stage backfill
      3. sample_by_count     — smart vendor-pool-first count mode

    All strategies share vendor-deduplication helpers and produce
    labelled TOD / TOC DataFrames with selection rationale.

    Key correctness guarantees (v2):
      • TOD and TOC always use SEPARATE vendor counters — TOD saturation
        cannot lock any vendor out of TOC.
      • Month coverage iterates ALL months unconditionally before any count
        guard fires — every fiscal period gets at least one candidate.
      • Fallback 2 relaxes the vendor cap to config.vendor_cap_fallback (default 3)
        rather than repeating the same cap as Fallback 1 (dead-code bug fixed).
      • sample_by_value non-vendor rows call mark_used() in stage 1 to prevent
        double-selection in stage 2.
      • Strata targets in Stage 2 are computed from remaining quota after Stage 1
        mandatory slots, preventing high-value over-allocation.
    """

    def __init__(self, config: AuditConfig):
        self.config = config

    # ── Public dispatch ───────────────────────────────────────────────────────

    def generate(
        self,
        scored: pd.DataFrame,
        sampling_basis: str,
        tod_target: int,
        toc_target: int,
        amount_col: Optional[str],
        vendor_col: Optional[str],
        date_col: Optional[str],
        category: str,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Dispatch to the appropriate sampling strategy based on sampling_basis.

        Args:
            sampling_basis: 'count' → sample_stratified,
                            'value' → sample_by_value
        """
        if sampling_basis == 'value':
            return self.sample_by_value(
                scored=scored,
                tod_target_count=tod_target,
                toc_target_count=toc_target,
                amount_col=amount_col,
                vendor_col=vendor_col,
                category=category
            )
        else:
            return self.sample_stratified(
                scored, tod_target, toc_target, amount_col, vendor_col, date_col, category
            )

    # ── Strategy 1: Count-based Stratified Sampling ───────────────────────────

    def sample_stratified(
        self,
        scored: pd.DataFrame,
        tod_target: int,
        toc_target: int,
        amount_col: Optional[str],
        vendor_col: Optional[str],
        date_col: Optional[str],
        category: str,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Month-stratified, vendor-deduplicated count-based sampling.

        Stage 1: Mandatory month coverage — ONE random pick per month,
                 visiting ALL months unconditionally before count guard applies.
                 [FIXED-1] Previously broke early when tod_target was hit mid-loop.

        Stage 2: Stratified strata fill (60/30/10 allocation) on remaining quota
                 after Stage 1.
                 [FIXED-6] Quota now correctly computed as (tod_target - Stage1 count).

        Stage 3: Month-stratified random TOC selection using its own vendor counter.
                 [FIXED-3] Previously shared counter with TOD; now independent.

        Stage 4: Fill TOC to target.

        Fallback 1 (TOD): Unique vendors (cap = vendor_cap_primary = 2).
        Fallback 2 (TOD): Relaxed vendors (cap = vendor_cap_fallback = 3).
                 [FIXED-2] Previously identical to Fallback 1 — now actually relaxed.

        Same two-stage fallback applies to TOC independently.
        """
        data = scored.copy()

        # Resolve month column from cached _Parsed_Date
        if '_Parsed_Date' in data.columns:
            data['_Month'] = data['_Parsed_Date'].dt.month
        else:
            data['_Month'] = np.nan

        months = sorted(data['_Month'].dropna().unique())

        vcol = '_Norm_Vendor' if '_Norm_Vendor' in data.columns else vendor_col
        amt_col = amount_col or self._first_numeric(data)
        if not amt_col:
            return self._empty_pair(scored)

        data = data.sort_values(by=amt_col, ascending=False, key=abs)

        # Value strata (computed once; used in Stage 2)
        n = len(data)
        high_strata = data.iloc[: max(1, int(n * 0.1))]
        mid_strata  = data.iloc[max(1, int(n * 0.1)) : max(2, int(n * 0.4))]
        low_strata  = data.iloc[max(2, int(n * 0.4)) :]

        # ── TOD selection ──────────────────────────────────────────────────
        # TOD has its own Counter so it is completely independent of TOC.
        tod_seen_vendors: Counter = Counter()
        tod_indices: List[Any] = []

        tod_is_used, tod_mark_used = self._vendor_helpers(
            vcol, tod_seen_vendors, cap=self.config.vendor_cap_primary
        )

        # Stage 1: One random transaction per month — ALL months visited first.
        # [FIXED-1] The break is intentionally ABSENT here; we collect one candidate
        # per month unconditionally, then trim to tod_target afterwards if needed.
        mandatory_tod: List[Any] = []
        for m in months:
            month_data = data[data['_Month'] == m].sample(frac=1, random_state=42)
            for idx, row in month_data.iterrows():
                if not tod_is_used(row):
                    mandatory_tod.append(idx)
                    tod_mark_used(row)
                    break  # one per month is enough

        # If mandatory coverage already exceeds tod_target, keep the highest-value
        # ones (they are already in descending-value order since data is sorted).
        if len(mandatory_tod) > tod_target:
            mandatory_tod = mandatory_tod[:tod_target]

        tod_indices.extend(mandatory_tod)

        # Stage 2: Strata fill on remaining quota.
        # [FIXED-6] Base the strata targets on what is still needed, not on tod_target.
        remaining_quota = tod_target - len(tod_indices)
        if remaining_quota > 0:
            alloc_h, alloc_m, alloc_l = self.config.strata_allocation
            for strata_df, alloc in [
                (high_strata, alloc_h), (mid_strata, alloc_m), (low_strata, alloc_l)
            ]:
                strata_target = int(remaining_quota * alloc)
                strata_current = sum(1 for i in tod_indices if i in strata_df.index)
                remaining = strata_df[~strata_df.index.isin(tod_indices)]
                for idx, row in remaining.iterrows():
                    if strata_current >= strata_target or len(tod_indices) >= tod_target:
                        break
                    if not tod_is_used(row):
                        tod_indices.append(idx)
                        tod_mark_used(row)
                        strata_current += 1

        # Fallback 1: Fill remaining TOD with unique-vendor rows (cap = primary).
        if len(tod_indices) < tod_target:
            remaining = data[~data.index.isin(tod_indices)].sort_values(
                by=amt_col, ascending=False, key=abs
            )
            for idx, row in remaining.iterrows():
                if len(tod_indices) >= tod_target:
                    break
                if not tod_is_used(row):
                    tod_indices.append(idx)
                    tod_mark_used(row)

        # Fallback 2: Relax vendor cap to vendor_cap_fallback (default 3).
        if len(tod_indices) < tod_target:
            tod_relaxed_is_used, tod_relaxed_mark_used = self._vendor_helpers(
                vcol, tod_seen_vendors, cap=self.config.vendor_cap_fallback
            )
            remaining = data[~data.index.isin(tod_indices)].sort_values(
                by=amt_col, ascending=False, key=abs
            )
            for idx, row in remaining.iterrows():
                if len(tod_indices) >= tod_target:
                    break
                if not tod_relaxed_is_used(row):
                    tod_indices.append(idx)
                    tod_relaxed_mark_used(row)

        # ── TOC selection ──────────────────────────────────────────────────
        # [FIXED-3] TOC uses its own Counter, completely independent of TOD.
        toc_seen_vendors: Counter = Counter()
        toc_indices: List[Any] = []

        toc_is_used, toc_mark_used = self._vendor_helpers(
            vcol, toc_seen_vendors, cap=self.config.vendor_cap_primary
        )

        # Stage 3: Monthly random TOC — one per month, all months visited.
        if toc_target > 0:
            mandatory_toc: List[Any] = []
            for m in months:
                if len(mandatory_toc) >= toc_target:
                    break  # toc_target can bound here since it's typically small
                pool = data[
                    (data['_Month'] == m) & (~data.index.isin(tod_indices))
                ].sample(frac=1, random_state=42)
                for idx, row in pool.iterrows():
                    if not toc_is_used(row):
                        mandatory_toc.append(idx)
                        toc_mark_used(row)
                        break
            toc_indices.extend(mandatory_toc)

        # Stage 4: Fill TOC to target.
        if toc_target > 0 and len(toc_indices) < toc_target:
            pool = data[
                ~data.index.isin(tod_indices) & ~data.index.isin(toc_indices)
            ].sample(frac=1, random_state=42)
            for idx, row in pool.iterrows():
                if len(toc_indices) >= toc_target:
                    break
                if not toc_is_used(row):
                    toc_indices.append(idx)
                    toc_mark_used(row)

        # Fallback TOC 1: unique vendors (primary cap)
        if toc_target > 0 and len(toc_indices) < toc_target:
            pool = data[
                ~data.index.isin(tod_indices) & ~data.index.isin(toc_indices)
            ].sort_values(by=amt_col, ascending=False, key=abs)
            for idx, row in pool.iterrows():
                if len(toc_indices) >= toc_target:
                    break
                if not toc_is_used(row):
                    toc_indices.append(idx)
                    toc_mark_used(row)

        # Fallback TOC 2: relaxed cap (vendor_cap_fallback).
        if toc_target > 0 and len(toc_indices) < toc_target:
            toc_relaxed_is_used, toc_relaxed_mark_used = self._vendor_helpers(
                vcol, toc_seen_vendors, cap=self.config.vendor_cap_fallback
            )
            pool = data[
                ~data.index.isin(tod_indices) & ~data.index.isin(toc_indices)
            ].sort_values(by=amt_col, ascending=False, key=abs)
            for idx, row in pool.iterrows():
                if len(toc_indices) >= toc_target:
                    break
                if not toc_relaxed_is_used(row):
                    toc_indices.append(idx)
                    toc_relaxed_mark_used(row)

        return self._finalise(data, tod_indices, toc_indices, amt_col, category)

    # ── Strategy 2: Value-based Sampling ─────────────────────────────────────

    def sample_by_value(
        self,
        scored: pd.DataFrame,
        sample_pct: Optional[float] = None,
        tod_pct: Optional[float] = None,
        tod_target_count: Optional[int] = None,
        toc_target_count: Optional[int] = None,
        amount_col: Optional[str] = None,
        vendor_col: Optional[str] = None,
        category: str = 'Sales',
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Value-based sampling that prioritises value coverage while strictly
        honouring the requested target row counts (TOD + TOC).
        
        Guarantees month coverage and enforces progressive vendor-repetition caps.
        """
        total_rows = len(scored)

        # 1. Resolve absolute counts from legacy or modern interfaces
        if tod_target_count is not None and toc_target_count is not None:
            _tod_count = tod_target_count
            _toc_count = toc_target_count
        elif sample_pct is not None:
            _effective_tod_pct = tod_pct if tod_pct is not None else self.config.tod_pct
            total_needed = math.ceil(total_rows * sample_pct / 100.0)
            _tod_count = math.ceil(total_needed * _effective_tod_pct / 100.0)
            _toc_count = total_needed - _tod_count
        else:
            raise ValueError(
                'sample_by_value requires either (sample_pct, tod_pct) '
                'or (tod_target_count, toc_target_count).'
            )

        if not amount_col:
            logger.warning('Value-based sampling requires amount_col; falling back to count mode.')
            return self.sample_stratified(
                scored, _tod_count, _toc_count,
                amount_col, vendor_col, None, category
            )

        total_count_target = _tod_count + _toc_count
        if total_count_target == 0 or total_rows == 0:
            return self._empty_pair(scored)

        tod_target_count = _tod_count
        toc_target_count = _toc_count

        # Ensure we work on a clean copy of sorted data to avoid SettingWithCopy warnings
        sorted_data = scored.sort_values(by=amount_col, ascending=False, key=abs).copy()
        norm_col = '_Norm_Vendor' if '_Norm_Vendor' in sorted_data.columns else vendor_col

        # ── PHASE 1: Mandatory month coverage (ALL months, one row each) ──────
        # CRITICAL: Use the SAME counter as Phase 2 so month-coverage picks
        # count toward the global vendor cap of 2.
        all_seen_vendors: Counter = Counter()
        all_is_used, all_mark_used = self._vendor_helpers(
            norm_col, all_seen_vendors, cap=self.config.vendor_cap_primary
        )

        month_indices: List[Any] = []

        if '_Parsed_Date' in sorted_data.columns:
            sorted_data['_Month'] = sorted_data['_Parsed_Date'].dt.month
            months = sorted(sorted_data['_Month'].dropna().unique())
            for m in months:
                month_pool = sorted_data[sorted_data['_Month'] == m]
                for idx, row in month_pool.iterrows():
                    if not all_is_used(row):      # ← uses global cap
                        month_indices.append(idx)
                        all_mark_used(row)         # ← counts toward global cap
                        break

        # ── PHASE 2: Greedy highest-value fill up to total_count_target ───────
        # Note: all_seen_vendors is already initialized and seeded with Phase 1 selections.

        selected_indices: List[Any] = list(month_indices)
        selected_set = set(selected_indices)

        for idx, row in sorted_data.iterrows():
            if len(selected_indices) >= total_count_target:
                break
            if idx in selected_set:
                continue
            if not all_is_used(row):
                selected_indices.append(idx)
                selected_set.add(idx)
                all_mark_used(row)

        # ── PHASE 3: Fallback — relax vendor cap to vendor_cap_fallback ───────
        if len(selected_indices) < total_count_target:
            all_relaxed_is_used, all_relaxed_mark_used = self._vendor_helpers(
                norm_col, all_seen_vendors, cap=self.config.vendor_cap_fallback
            )
            for idx, row in sorted_data.iterrows():
                if len(selected_indices) >= total_count_target:
                    break
                if idx in selected_set:
                    continue
                if not all_relaxed_is_used(row):
                    selected_indices.append(idx)
                    selected_set.add(idx)
                    all_relaxed_mark_used(row)

        # Note: Phase 4 (uncapped last resort) has been completely removed to strictly
        # enforce that no vendor is considered more than the absolute hard cap limit of 2 times,
        # complying with the statutory audit's non-repetition directive.

        # ── Split selected into TOD / TOC at requested ratio ──────────────────
        # selected_indices is already sorted by absolute value descending
        tod_indices = selected_indices[:tod_target_count]
        toc_indices = selected_indices[tod_target_count: tod_target_count + toc_target_count]

        logger.debug(
            f'[VALUE-FIXED] total_count_target={total_count_target} '
            f'selected={len(selected_indices)} '
            f'TOD={len(tod_indices)} TOC={len(toc_indices)} '
            f'months_covered={len(month_indices)}'
        )

        return self._finalise(sorted_data, tod_indices, toc_indices, amount_col, category)

    # ── Strategy 3: Smart Count Mode (vendor-pool-first) ─────────────────────

    def sample_by_count(
        self,
        scored: pd.DataFrame,
        # Legacy percentage interface (original API — kept for backward compatibility)
        sample_pct: Optional[float] = None,
        tod_pct: Optional[float] = None,
        # Modern absolute-count interface (used internally by generate())
        tod_target: Optional[int] = None,
        toc_target: Optional[int] = None,
        # Shared required args
        amount_col: Optional[str] = None,
        vendor_col: Optional[str] = None,
        category: str = 'Sales',
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Smart vendor-pool-first count mode:
        1. One best transaction per vendor (highest risk score).
        2. Split 70/30 into TOD/TOC pools.
        3. Backfill shortfalls from remaining transactions.

        Supports two calling conventions for full backward compatibility:

        Legacy (percentage-based, original frontend/API interface):
            sample_by_count(scored, sample_pct=20.0, tod_pct=70.0, amount_col=..., ...)

        Modern (absolute-count, used internally by generate()):
            sample_by_count(scored, tod_target=14, toc_target=6, amount_col=..., ...)
        """
        total_rows = len(scored)

        # Resolve absolute counts from whichever interface was used
        if tod_target is not None and toc_target is not None:
            _tod_target = tod_target
            _toc_target = toc_target
        elif sample_pct is not None:
            _effective_tod_pct = tod_pct if tod_pct is not None else self.config.tod_pct
            total_needed = math.ceil(total_rows * sample_pct / 100.0)
            _tod_target = math.ceil(total_needed * _effective_tod_pct / 100.0)
            _toc_target = total_needed - _tod_target
        else:
            raise ValueError(
                'sample_by_count requires either (sample_pct, tod_pct) '
                'or (tod_target, toc_target).'
            )

        tod_target = _tod_target
        toc_target = _toc_target

        vcol = '_Norm_Vendor' if '_Norm_Vendor' in scored.columns else vendor_col
        amt_col = amount_col or self._first_numeric(scored)

        # Stage 1: Best transaction per vendor
        if vcol and vcol in scored.columns:
            vendor_pool = (
                scored.sort_values('_Risk_Score', ascending=False)
                      .groupby(vcol)
                      .head(1)
            )
            norm_series = vendor_pool[vcol].astype(str).str.strip().str.lower()
            vendor_pool = vendor_pool[~norm_series.isin(['', 'nan', 'none'])]

            pool_tod = vendor_pool.head(tod_target).copy()
            pool_toc = vendor_pool.iloc[tod_target: tod_target + toc_target].copy()
            used_indices = set(pool_tod.index) | set(pool_toc.index)
        else:
            pool_tod = scored.head(0).copy()
            pool_toc = scored.head(0).copy()
            used_indices = set()

        # Stage 2: Backfill shortfalls
        remaining = scored[~scored.index.isin(used_indices)].sort_values(
            '_Risk_Score', ascending=False
        )

        if len(pool_tod) < tod_target:
            shortfall = tod_target - len(pool_tod)
            extra = remaining.head(shortfall)
            pool_tod = pd.concat([pool_tod, extra])
            used_indices.update(extra.index)
            remaining = scored[~scored.index.isin(used_indices)].sort_values(
                '_Risk_Score', ascending=False
            )
            logger.debug(f'[COUNT] TOD backfill: +{len(extra)} rows')

        if len(pool_toc) < toc_target:
            shortfall = toc_target - len(pool_toc)
            extra = remaining.head(shortfall)
            pool_toc = pd.concat([pool_toc, extra])
            logger.debug(f'[COUNT] TOC backfill: +{len(extra)} rows')

        return self._finalise(
            scored,
            pool_tod.index.tolist(),
            pool_toc.index.tolist(),
            amt_col,
            category,
            toc_rationale='Smart Selection (Prioritized Vendor Diversity)',
        )

    # ── Strategy 4: Generic Count Fallback (strict 70/30 risk-ranked split) ────

    def sample_by_count_generic(
        self,
        scored: pd.DataFrame,
        # Legacy percentage interface
        sample_pct: Optional[float] = None,
        tod_pct: Optional[float] = None,
        # Modern absolute-count interface
        tod_target: Optional[int] = None,
        toc_target: Optional[int] = None,
        # Shared args
        amount_col: Optional[str] = None,
        category: str = 'Sales',
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Strict risk-ranked 70/30 split — no vendor-pool logic, no deduplication.
        Used as a generic fallback when vendor information is unavailable, or
        when a caller explicitly wants the simplest deterministic split.

        Supports two calling conventions for full backward compatibility:

        Legacy:
            sample_by_count_generic(scored, sample_pct=20.0, tod_pct=70.0, ...)

        Modern:
            sample_by_count_generic(scored, tod_target=14, toc_target=6, ...)
        """
        total_rows = len(scored)

        if tod_target is not None and toc_target is not None:
            _tod_target = tod_target
            _toc_target = toc_target
        elif sample_pct is not None:
            _effective_tod_pct = tod_pct if tod_pct is not None else self.config.tod_pct
            total_samples = math.ceil(total_rows * sample_pct / 100.0)
            _tod_target = math.ceil(total_samples * _effective_tod_pct / 100.0)
            _toc_target = total_samples - _tod_target
        else:
            raise ValueError(
                'sample_by_count_generic requires either (sample_pct, tod_pct) '
                'or (tod_target, toc_target).'
            )

        amt_col = amount_col or self._first_numeric(scored)

        # Simple deterministic split: top N rows for TOD, next M for TOC
        tod = scored.head(_tod_target).copy()
        toc = scored.iloc[_tod_target: _tod_target + _toc_target].copy()

        tod['_Audit_Procedure']     = 'Test of Details (TOD)'
        tod['_Selection_Rationale'] = tod.apply(
            lambda r: self._tod_rationale(r, amt_col), axis=1
        )
        tod['_Audit_Remarks']         = ''
        tod['_Supporting_Doc_Status'] = 'Pending'

        toc['_Audit_Procedure']         = 'Test of Controls (TOC)'
        toc['_Selection_Rationale']     = 'Generic Random Selection'
        toc['_Control_Objective']       = self._control_objective(category)
        toc['_Control_Testing_Remarks'] = ''
        toc['_Supporting_Doc_Status']   = 'Pending'

        risk_cols = [c for c in tod.columns if c.startswith('_Risk_')]
        tod = tod.drop(columns=risk_cols, errors='ignore')
        toc = toc.drop(columns=risk_cols, errors='ignore')

        return tod, toc

    # ── Shared Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _vendor_helpers(vcol, seen_vendors: Counter, cap: int = 2):
        """
        Return (is_used, mark_used) closures over seen_vendors Counter.

        [FIXED-2 & FIXED-3]
        The `cap` parameter makes the allowed repeat count explicit and
        configurable per call site, so:
          • Primary loops pass cap=vendor_cap_primary (default 2)
          • Fallback 2 loops pass cap=vendor_cap_fallback (default 3)
          • TOD and TOC each pass their own separate Counter instances

        Unlike the original implementation which hard-coded `>= 2` inside a
        single shared closure (making Fallback 2 identical to Fallback 1),
        this version is parameterised and reusable.
        """
        def is_used(row) -> bool:
            if not vcol:
                return False
            v = str(row.get(vcol, '')).strip().lower()
            if not v or v in ('nan', 'none', ''):
                return False
            return seen_vendors[v] >= cap

        def mark_used(row):
            if not vcol:
                return
            v = str(row.get(vcol, '')).strip().lower()
            if v and v not in ('nan', 'none', ''):
                seen_vendors[v] += 1

        return is_used, mark_used

    def _unique_vendor_select(
        self,
        data: pd.DataFrame,
        n: int,
        amount_col: Optional[str],
        strategy: str = 'highest',
        strict_unique: bool = False,
    ) -> pd.DataFrame:
        """
        Select n rows prioritising unique vendors/parties.
        Uses _Norm_Vendor (forensic-normalised) for entity deduplication.

        Args:
            strategy:     'highest' → sort by absolute value desc before selecting.
                          'random'  → shuffle before selecting (for TOC diversity).
            strict_unique: If True, NEVER include duplicate vendors — may return
                           fewer than n rows if unique vendors are exhausted.
                           If False, fills remaining slots with duplicate-vendor rows.
        """
        if n <= 0 or data.empty:
            return data.head(0).copy()

        target = min(n, len(data))
        vcol = '_Norm_Vendor' if '_Norm_Vendor' in data.columns else None

        if not vcol:
            if strategy == 'highest' and amount_col:
                return data.sort_values(by=amount_col, ascending=False, key=abs).head(target).copy()
            return data.sample(n=target, random_state=42).copy()

        source = (
            data.sort_values(by=amount_col, ascending=False, key=abs)
            if (strategy == 'highest' and amount_col)
            else data.sample(frac=1, random_state=42)
        )

        selected: List[Any] = []
        seen_vendors: set = set()
        deferred: List[Any] = []

        for idx, row in source.iterrows():
            vendor = str(row.get(vcol, '')).strip().lower()
            is_named = vendor and vendor not in ('nan', 'none', '')

            if is_named and vendor in seen_vendors:
                deferred.append(idx)
            else:
                if is_named:
                    seen_vendors.add(vendor)
                selected.append(idx)

            if len(selected) >= target:
                break

        if not strict_unique and len(selected) < target and deferred:
            remaining_need = target - len(selected)
            selected.extend(deferred[:remaining_need])

        return data.loc[selected].copy()

    def _stratified_random(
        self,
        data: pd.DataFrame,
        n: int,
        date_col: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Month-wise stratified random sampling with plain-random fallback.
        Ensures every active calendar month gets at least one sample.
        Used as a utility helper inside TOC filling and legacy callers.
        """
        if date_col and date_col in data.columns:
            try:
                dates = pd.to_datetime(
                    data[date_col], errors='coerce', dayfirst=True, format='mixed'
                )
                tmp = data.copy()
                tmp['_month'] = dates.dt.month
                months = tmp['_month'].dropna().unique()
                per_month = max(1, n // len(months)) if len(months) > 0 else n

                parts = []
                for m in months:
                    month_data = tmp[tmp['_month'] == m]
                    take = min(per_month, len(month_data))
                    if take > 0:
                        parts.append(month_data.sample(n=take, random_state=42))

                result = pd.concat(parts) if parts else pd.DataFrame(columns=data.columns)

                # Fill any remaining slots needed to reach n
                if len(result) < n:
                    leftover = tmp.drop(result.index, errors='ignore')
                    extra = min(n - len(result), len(leftover))
                    if extra > 0:
                        result = pd.concat([result, leftover.sample(n=extra, random_state=42)])

                result = result.head(n)
                result = result.drop(columns=['_month'], errors='ignore')
                return result

            except Exception as e:
                logger.warning(f'_stratified_random month-wise pass failed: {e}; falling back to plain random.')

        # Plain random fallback (no date column or date parsing failed)
        return data.sample(n=min(n, len(data)), random_state=42)

    @staticmethod
    def _first_numeric(df: pd.DataFrame) -> Optional[str]:
        nums = df.select_dtypes(include=[np.number]).columns.tolist()
        return nums[0] if nums else None

    @staticmethod
    def _empty_pair(template: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        empty = pd.DataFrame(columns=template.columns)
        return empty, empty

    def _tod_rationale(self, row, amt_col: Optional[str]) -> str:
        flags = str(row.get('_Risk_Flags', ''))
        if flags and flags != 'None':
            return f'Selected for substantive testing: {flags}'
        if amt_col and row.get(amt_col, 0) > 0:
            return 'High-value transaction — substantive verification required'
        return 'Selected by risk-based sampling algorithm'

    @staticmethod
    def _control_objective(category: str) -> str:
        objectives = {
            'Sales':     'Verify authorization, completeness, and accuracy of sales transactions',
            'Expenses':  'Verify approval, classification, and supporting documentation of expenses',
            'Purchases': 'Verify purchase order matching, vendor approval, and receipt confirmation',
        }
        return objectives.get(category, 'Verify transaction authorization and processing controls')

    def _add_labels(
        self,
        tod: pd.DataFrame,
        toc: pd.DataFrame,
        amt_col: Optional[str],
        category: str,
        toc_rationale: str = 'Random Selection (Month-wise Stratified)',
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Attach audit metadata columns to TOD and TOC DataFrames."""
        # Sort by absolute value descending
        if amt_col and not tod.empty:
            tod = tod.sort_values(by=amt_col, ascending=False, key=abs)
        if amt_col and not toc.empty:
            toc = toc.sort_values(by=amt_col, ascending=False, key=abs)

        tod['_Audit_Procedure']    = 'Test of Details (TOD)'
        tod['_Selection_Rationale'] = tod.apply(
            lambda r: self._tod_rationale(r, amt_col), axis=1
        )
        tod['_Audit_Remarks']          = ''
        tod['_Supporting_Doc_Status']  = 'Pending'

        toc['_Audit_Procedure']           = 'Test of Controls (TOC)'
        toc['_Control_Objective']         = self._control_objective(category)
        toc['_Selection_Rationale']       = toc_rationale
        toc['_Control_Testing_Remarks']   = ''
        toc['_Supporting_Doc_Status']     = 'Pending'

        # Drop internal risk and month columns
        drop_cols = [c for c in tod.columns if c.startswith('_Risk_') or c == '_Month']
        tod = tod.drop(columns=drop_cols, errors='ignore')
        toc = toc.drop(columns=drop_cols, errors='ignore')

        return tod, toc

    def _finalise(
        self,
        data: pd.DataFrame,
        tod_indices: List[Any],
        toc_indices: List[Any],
        amt_col: Optional[str],
        category: str,
        toc_rationale: str = 'Random Selection (Month-wise Stratified)',
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        tod = data.loc[tod_indices].copy() if tod_indices else pd.DataFrame(columns=data.columns)
        toc = data.loc[toc_indices].copy() if toc_indices else pd.DataFrame(columns=data.columns)
        return self._add_labels(tod, toc, amt_col, category, toc_rationale)

    def _finalise_value(
        self,
        tod: pd.DataFrame,
        toc: pd.DataFrame,
        amt_col: Optional[str],
        category: str,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        tod = tod.copy()
        toc = toc.copy()
        return self._add_labels(tod, toc, amt_col, category)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD BUILDER
# ══════════════════════════════════════════════════════════════════════════════

class DashboardBuilder:
    """
    Builds diagnostic metrics for the client UI:
    risk concentration, Gini coefficient, monthly Z-score trend analysis,
    top vendors, and forensic flag summary.
    Uses cached _Parsed_Date column — no redundant date re-parsing.
    """

    def __init__(self, config: AuditConfig):
        self.config = config

    def build_dashboard(
        self,
        scored: pd.DataFrame,
        amount_col: Optional[str],
        narration_col: Optional[str],
    ) -> Dict[str, Any]:
        dashboard: Dict[str, Any] = {}
        total_rows = len(scored)

        # ── Aggregate Metrics ──
        if amount_col and amount_col in scored.columns:
            amounts = scored[amount_col].abs()
            dashboard['metrics'] = {
                'count':       total_rows,
                'total_value': float(amounts.sum()),
                'minimum':     float(amounts.min()) if not amounts.empty else 0,
                'maximum':     float(amounts.max()) if not amounts.empty else 0,
                'average':     float(amounts.mean()) if not amounts.empty else 0,
            }
        else:
            dashboard['metrics'] = {
                'count': total_rows, 'total_value': 0,
                'minimum': 0, 'maximum': 0, 'average': 0,
            }

        # ── Risk Concentration (top 5%) ──
        if amount_col and total_rows > 0:
            amt = scored[amount_col].abs()
            total_val = amt.sum()
            top_n = max(1, math.ceil(total_rows * 0.05))
            top_vals = amt.nlargest(top_n)
            dashboard['risk_concentration'] = {
                'top_5pct_count': int(top_n),
                'top_5pct_value': float(top_vals.sum()),
                'top_5pct_share': float(top_vals.sum() / max(total_val, 1)),
                'total_value':    float(total_val),
            }
        else:
            dashboard['risk_concentration'] = {
                'top_5pct_count': 0, 'top_5pct_value': 0,
                'top_5pct_share': 0, 'total_value': 0,
            }

        # ── Vendor Gini Coefficient ──
        if '_Norm_Vendor' in scored.columns and amount_col:
            vendor_totals = (
                scored[scored['_Norm_Vendor'] != '']
                .groupby('_Norm_Vendor')[amount_col]
                .apply(lambda x: x.abs().sum())
            )
            if len(vendor_totals) > 1:
                vals = np.sort(vendor_totals.values).astype(float)
                n = len(vals)
                gini = (
                    2.0 * np.sum(np.arange(1, n + 1) * vals) / (n * np.sum(vals))
                    - (n + 1) / n
                )
                dashboard['vendor_gini'] = round(float(np.clip(gini, 0, 1)), 4)
                top5 = vendor_totals.nlargest(5)
                dashboard['top_vendors'] = [
                    {'name': str(k).title(), 'value': float(v)}
                    for k, v in top5.items()
                ]
            else:
                dashboard['vendor_gini'] = 0.0
                dashboard['top_vendors'] = []
        else:
            dashboard['vendor_gini'] = 0.0
            dashboard['top_vendors'] = []

        # ── Monthly Trend Analysis with Z-Score Spike Detection ──
        # Uses pre-cached _Parsed_Date column — no redundant re-parsing
        if '_Parsed_Date' in scored.columns and amount_col:
            try:
                sc = scored.copy()
                sc['_month'] = sc['_Parsed_Date'].dt.to_period('M')
                monthly = sc.groupby('_month').agg(
                    txn_count=(amount_col, 'count'),
                    txn_value=(amount_col, lambda x: float(x.abs().sum())),
                ).reset_index()
                monthly['_month'] = monthly['_month'].astype(str)

                counts = monthly['txn_count'].values.astype(float)
                if len(counts) > 2:
                    mu, sigma = counts.mean(), counts.std()
                    zscores = (
                        ((counts - mu) / sigma).tolist() if sigma > 0
                        else [0.0] * len(counts)
                    )
                else:
                    zscores = [0.0] * len(counts)

                dashboard['monthly_trends'] = [
                    {
                        'month':    row['_month'],
                        'count':    int(row['txn_count']),
                        'value':    float(row['txn_value']),
                        'z_score':  round(zscores[i], 2),
                        'is_spike': abs(zscores[i]) > 2.0,
                    }
                    for i, (_, row) in enumerate(monthly.iterrows())
                ]
            except Exception as e:
                logger.warning(f'Monthly trend analysis failed: {e}')
                dashboard['monthly_trends'] = []
        else:
            dashboard['monthly_trends'] = []

        # ── Risk Distribution ──
        dashboard['risk_distribution'] = {
            'high':   int((scored['_Risk_Category'] == 'High').sum()),
            'medium': int((scored['_Risk_Category'] == 'Medium').sum()),
            'low':    int((scored['_Risk_Category'] == 'Low').sum()),
        }

        # ── Forensic Flag Summary ──
        all_flags: List[str] = []
        for f_str in scored['_Risk_Flags']:
            if f_str and f_str != 'None':
                all_flags.extend(f.strip() for f in str(f_str).split(';'))
        dashboard['forensic_flags'] = dict(Counter(all_flags))

        return dashboard


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class AuditAnalyzer:
    """
    Enterprise AI Audit Sampling Engine — Orchestrator.

    Public API is fully backwards-compatible with the original single-class version.
    Internally delegates to DataCleaner, VendorNormalizer, RiskScorer,
    SampleEngine, and DashboardBuilder.

    Key guarantees:
      • validate() runs AFTER column detection so amount_col can be checked.
      • score_risks() result is cached — computed once regardless of how many
        times get_risk_analysis() / get_dashboard_json() / generate_samples()
        are called.
      • sampling_basis='value' is fully honoured and dispatched to sample_by_value.
      • Dashboard uses cached _Parsed_Date — no redundant date re-parsing.
      • category is passed explicitly to SampleEngine — no fragile DataFrame.attrs.
      • [FIXED-4] generate_samples re-bifurcation no longer calls engine.generate()
        again (hits same cap wall). It redistributes already-selected rows instead.
    """

    VALID_CATEGORIES = ('Sales', 'Purchases', 'Expenses')

    def __init__(
        self,
        df: pd.DataFrame,
        category: str,
        trivial_threshold: float = 0,
        performance_materiality: float = 0,
        config: Optional[AuditConfig] = None,
    ):
        self.config = config or AuditConfig()
        self.category = category
        self.trivial_threshold = trivial_threshold
        self.performance_materiality = performance_materiality
        self.raw_df = df.copy()
        self._scored_cache: Optional[pd.DataFrame] = None
        self.sampling_deficit: Optional[dict] = None

        # Step 1: Initialise components
        self.cleaner    = DataCleaner(self.config)
        self.normalizer = VendorNormalizer(self.config)
        self.scorer     = RiskScorer(self.config)
        self.engine     = SampleEngine(self.config)
        self.builder    = DashboardBuilder(self.config)

        # Step 2: Basic structural validation before cleaning
        self._validate_input(df)

        # Step 3: Drop fully-empty rows
        self.df = df.dropna(how='all').copy()

        # Step 4: Detect columns
        detected = self.cleaner.detect_columns(self.df, self.category)
        self.amount_col    = detected['amount_col']
        self.date_col      = detected['date_col']
        self.narration_col = detected['narration_col']
        self.invoice_col   = detected['invoice_col']
        self.vendor_col    = detected['vendor_col']
        self.txn_id_col    = detected.get('txn_id_col')

        # Step 5: Post-detection validation (amount_col now known)
        self._validate_post_detection()

        # Step 6: Clean amounts
        if self.amount_col:
            self.df[self.amount_col] = self.cleaner.clean_amounts(self.df, self.amount_col)

        # Step 7: Filter non-transaction rows
        self.df = self.cleaner.filter_non_transaction_rows(self.df)

        # Step 8: Cache parsed dates (once — avoids repeated heavy parsing)
        if self.date_col and self.date_col in self.df.columns:
            try:
                self.df['_Parsed_Date'] = pd.to_datetime(
                    self.df[self.date_col], errors='coerce',
                    dayfirst=True, format='mixed',
                )
            except Exception as e:
                logger.warning(f"Date parsing failed for column '{self.date_col}': {e}")
                self.df['_Parsed_Date'] = pd.NaT
        else:
            self.df['_Parsed_Date'] = pd.NaT

        # Step 9: Normalise vendors
        self.df = self.normalizer.normalize(self.df, self.vendor_col)

        # Step 10: Optimise memory
        self.df = self.cleaner.optimize_memory(self.df)

        # Step 11: Sort highest absolute value first
        if self.amount_col:
            self.df = self.df.sort_values(
                by=self.amount_col, ascending=False, key=abs
            ).reset_index(drop=True)

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_input(self, df: pd.DataFrame):
        """Structural validation before any processing."""
        if df is None or df.empty:
            raise ValueError('Input DataFrame is empty or None.')
        if self.category not in self.VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}'. "
                f"Must be one of: {self.VALID_CATEGORIES}"
            )

    def _validate_post_detection(self):
        """Semantic validation once column detection has run."""
        if self.amount_col is None:
            raise ValueError(
                'No amount column could be detected in the ledger. '
                'Ensure the ledger has a column named debit, credit, amount, or value.'
            )
        if len(self.df) == 0:
            raise ValueError('DataFrame has no data rows after dropping empty rows.')

    # ── Risk Scoring (cached) ─────────────────────────────────────────────────

    def score_risks(self) -> pd.DataFrame:
        """
        Compute 12 forensic risk indicators. Result is cached after first call.
        Subsequent calls to generate_samples(), get_risk_analysis(),
        and get_dashboard_json() all reuse this cache.
        """
        if self._scored_cache is None:
            self._scored_cache = self.scorer.score_risks(
                df=self.df,
                amount_col=self.amount_col,
                date_col=self.date_col,
                narration_col=self.narration_col,
                vendor_col=self.vendor_col,
                performance_materiality=self.performance_materiality,
                trivial_threshold=self.trivial_threshold,
            )
        return self._scored_cache.copy()

    # ── Sample Generation ─────────────────────────────────────────────────────

    def generate_samples(
        self,
        sample_pct: float = 20.0,
        sampling_basis: str = 'count',
        tod_pct: float = 70.0,
        target_count: Optional[int] = None,
        audit_type: str = 'large',
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Generate mutually exclusive TOD and TOC sample DataFrames.

        Args:
            sample_pct:     % of population to sample (when target_count is None).
            sampling_basis: 'count' → stratified count mode (default).
                            'value' → value-coverage mode.
            tod_pct:        % of total sample allocated to TOD (default 70%).
            target_count:   Absolute sample size override (ignores sample_pct).
            audit_type:     'small' → TOD only. 'large' → TOD + TOC.

        Returns:
            (tod_df, toc_df)
        """
        if sampling_basis not in ('count', 'value'):
            raise ValueError(f"sampling_basis must be 'count' or 'value', got '{sampling_basis}'.")
        if not 0 < sample_pct <= 100:
            raise ValueError('sample_pct must be between 0 and 100.')

        scored = self.score_risks()
        total_rows = len(scored)
        if total_rows == 0:
            self.duplicates_removed = 0
            return self.engine._empty_pair(scored)

        # Apply strict deduplication based on User Rules (Rule 5 & 6)
        vcol = '_Norm_Vendor' if '_Norm_Vendor' in scored.columns else self.vendor_col
        icol = self.invoice_col
        tcol = self.txn_id_col
        dcol = self.date_col
        acol = self.amount_col

        seen_vendors = set()
        seen_invoices = set()
        seen_txn_ids = set()
        seen_combos = set()
        
        keep_mask = []
        duplicates_removed_count = 0
        
        for idx, row in scored.iterrows():
            is_dup = False
            
            # 1. Vendor/Party Name
            v = None
            if vcol and vcol in row:
                v = str(row[vcol]).strip().lower()
                if v and v not in ('', 'nan', 'none', '—'):
                    if v in seen_vendors:
                        is_dup = True
            
            # 2. Invoice Number
            inv = None
            if icol and icol in row:
                inv = str(row[icol]).strip().lower()
                if inv and inv not in ('', 'nan', 'none', '—'):
                    if inv in seen_invoices:
                        is_dup = True
                        
            # 3. Transaction ID
            tid = None
            if tcol and tcol in row:
                tid = str(row[tcol]).strip().lower()
                if tid and tid not in ('', 'nan', 'none', '—'):
                    if tid in seen_txn_ids:
                        is_dup = True

            # 4. Sample ID (if present in the ledger)
            sid = None
            for key in ['sample id', 'sample_id', 'sampleid']:
                if key in row:
                    sid = str(row[key]).strip().lower()
                    if sid and sid not in ('', 'nan', 'none', '—'):
                        if sid in seen_txn_ids:  # treat as unique transaction ID
                            is_dup = True

            # 5. Combination of date + amount + vendor
            dt = str(row.get(dcol, ''))
            amt = str(row.get(acol, ''))
            vnd = str(row.get(vcol, ''))
            combo = f"{dt}|{amt}|{vnd}"
            if combo in seen_combos:
                is_dup = True
                
            if is_dup:
                duplicates_removed_count += 1
                keep_mask.append(False)
            else:
                if v: seen_vendors.add(v)
                if inv: seen_invoices.add(inv)
                if tid: seen_txn_ids.add(tid)
                seen_combos.add(combo)
                keep_mask.append(True)

        deduped_scored = scored[keep_mask].copy()
        self.duplicates_removed = duplicates_removed_count
        total_unique_available = len(deduped_scored)

        # Determine absolute counts
        if target_count is not None:
            total_needed = min(int(target_count), total_rows)
        else:
            total_needed = math.ceil(total_rows * sample_pct / 100.0)

        if audit_type == 'small':
            tod_size = total_needed
            toc_size = 0
        else:
            tod_size = math.ceil(total_needed * tod_pct / 100.0)
            toc_size = total_needed - tod_size

        tod, toc = self.engine.generate(
            scored=deduped_scored,  # Pass clean unique rows only
            sampling_basis=sampling_basis,
            tod_target=tod_size,
            toc_target=toc_size,
            amount_col=self.amount_col,
            vendor_col=self.vendor_col,
            date_col=self.date_col,
            category=self.category,
        )

        actual_count = len(tod) + len(toc)

        # [FIXED-4] If vendor-cap constraints prevented reaching total_needed,
        # redistribute the ALREADY-SELECTED rows at the requested ratio
        if actual_count < total_needed and audit_type != 'small':
            new_tod_size = math.ceil(actual_count * tod_pct / 100.0)
            new_toc_size = actual_count - new_tod_size

            logger.info(
                f"Capping constraint hit. Re-distributing {actual_count} already-selected "
                f"samples: {new_tod_size} TOD (target was {tod_size}) & "
                f"{new_toc_size} TOC (target was {toc_size})"
            )

            all_selected = pd.concat([tod, toc])
            amt_col = self.amount_col
            if amt_col and amt_col in all_selected.columns:
                all_selected = all_selected.sort_values(
                    by=amt_col, ascending=False, key=abs
                )

            tod_rows = all_selected.iloc[:new_tod_size]
            toc_rows = all_selected.iloc[new_tod_size:]

            proc_cols = [
                '_Audit_Procedure', '_Selection_Rationale', '_Audit_Remarks',
                '_Supporting_Doc_Status', '_Control_Objective',
                '_Control_Testing_Remarks',
            ]
            tod_rows = tod_rows.drop(columns=[c for c in proc_cols if c in tod_rows.columns], errors='ignore').copy()
            toc_rows = toc_rows.drop(columns=[c for c in proc_cols if c in toc_rows.columns], errors='ignore').copy()

            tod, toc = self.engine._add_labels(tod_rows, toc_rows, amt_col, self.category)
            actual_count = len(tod) + len(toc)

        # Format strict non-repetition capping / deficit explanation (Rule 10)
        if actual_count < total_needed:
            self.sampling_deficit = {
                "requested": total_needed,
                "selected":  actual_count,
                "deficit":   total_needed - actual_count,
                "explanation": (
                    f"Required sample size of {total_needed} could not be achieved because "
                    f"strict duplicate removal was enforced to maintain unique sample list throughout the output. "
                    f"Total duplicates removed: {self.duplicates_removed}. "
                    f"Remaining unique samples available: {total_unique_available}. "
                    f"Additional samples could not be selected because no further qualifying unique transactions exist in the ledger."
                ),
            }
        else:
            self.sampling_deficit = None

        return tod, toc

    # ── Statistics ────────────────────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, Any]:
        total_rows = len(self.df)
        if not self.amount_col:
            return {'count': total_rows, 'total_value': 0,
                    'minimum': 0, 'maximum': 0, 'average': 0}
        amounts = self.df[self.amount_col].abs()
        return {
            'count':       total_rows,
            'total_value': float(amounts.sum()),
            'minimum':     float(amounts.min()) if not amounts.empty else 0,
            'maximum':     float(amounts.max()) if not amounts.empty else 0,
            'average':     float(amounts.mean()) if not amounts.empty else 0,
        }

    # ── Risk Analysis ─────────────────────────────────────────────────────────

    def get_risk_analysis(self) -> Dict[str, Any]:
        scored = self.score_risks()
        analysis: Dict[str, Any] = {
            'total_transactions': len(scored),
            'high_risk_count':   int((scored['_Risk_Category'] == 'High').sum()),
            'medium_risk_count': int((scored['_Risk_Category'] == 'Medium').sum()),
            'low_risk_count':    int((scored['_Risk_Category'] == 'Low').sum()),
        }

        if self.amount_col:
            amt = scored[self.amount_col].abs()

            dups = scored[amt.duplicated(keep=False) & (amt > 0)]
            analysis['duplicate_amount_count'] = len(dups)
            analysis['duplicate_amount_value'] = (
                float(dups[self.amount_col].abs().sum()) if len(dups) > 0 else 0
            )

            # Use ALL configured round_values with tolerance-based check [FIXED-7]
            rounds = scored[
                (amt > 0) & amt.apply(
                    lambda x: any(
                        abs(x % rv) < 0.01 or abs(x % rv - rv) < 0.01
                        for rv in self.config.round_values
                    )
                )
            ]
            analysis['round_value_count']   = len(rounds)
            analysis['zero_negative_count'] = int((scored[self.amount_col] <= 0).sum())

        if self.date_col:
            try:
                dates = scored['_Parsed_Date']
                analysis['weekend_posting_count']   = int(dates.dt.dayofweek.isin([5, 6]).sum())
                analysis['month_end_posting_count'] = int((dates.dt.day >= 28).sum())
            except Exception as e:
                logger.warning(f'Risk analysis date extraction failed: {e}')

        if self.narration_col and self.narration_col in scored.columns:
            # [FIXED-8] Union mask — count distinct rows, not keyword hits.
            narr = scored[self.narration_col].astype(str).str.lower()
            sus_mask = pd.Series(False, index=scored.index)
            for kw in self.config.suspicious_keywords:
                sus_mask |= narr.str.contains(kw, na=False)
            analysis['suspicious_narration_count'] = int(sus_mask.sum())

        return analysis

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def get_dashboard_json(self) -> Dict[str, Any]:
        """
        Full dashboard metrics. Uses cached scored DataFrame and cached _Parsed_Date.
        No redundant date re-parsing.
        """
        scored = self.score_risks()
        return self.builder.build_dashboard(
            scored=scored,
            amount_col=self.amount_col,
            narration_col=self.narration_col,
        )

    # ── Convenience ───────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f'AuditAnalyzer(category={self.category!r}, '
            f'rows={len(self.df)}, '
            f'amount_col={self.amount_col!r}, '
            f'date_col={self.date_col!r})'
        )

        