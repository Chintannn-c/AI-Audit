import pandas as pd
import numpy as np
import re
import math
from typing import Dict, Any, Tuple, List
from datetime import datetime
from collections import Counter

class AuditAnalyzer:
    """
    Enterprise AI Audit Sampling Engine.
    Supports dual-mode sampling (count-based / value-based),
    configurable TOD/TOC ratios, and 10 risk indicators.
    """

    def __init__(self, df: pd.DataFrame, category: str,
                 trivial_threshold: float = 0,
                 performance_materiality: float = 0):
        self.raw_df = df.copy()
        self.category = category
        self.trivial_threshold = trivial_threshold
        self.performance_materiality = performance_materiality
        self.original_columns = df.columns.tolist()

        # Clean: drop fully-empty rows
        self.df = df.dropna(how='all').copy()

        # Detect key columns
        self.amount_col = self._detect_amount_column()
        self.date_col = self._detect_date_column()
        self.narration_col = self._detect_narration_column()
        self.invoice_col = self._detect_invoice_column()
        self.vendor_col = self._detect_vendor_column()

        # Configuration for round values
        self.round_values = [1000, 5000, 10000, 50000, 100000, 500000, 1000000]

        # Clean amounts
        self._clean_amounts()

        # Filter non-transaction rows (totals, balances, headers)
        self._filter_non_transaction_rows()

        # Cache pre-parsed dates to avoid repeated heavy parsing
        self._cache_dates()

        # Forensic: Normalize vendor names for entity collapsing
        self._normalize_vendors()

        # Memory optimization: downcast types
        self._optimize_memory()

        # Sort highest value first
        self._sort_by_value()

    def _cache_dates(self):
        """Pre-parse dates once and store in a dedicated column."""
        if not self.date_col:
            self.df['_Parsed_Date'] = pd.NaT
            return
        # Use mixed format and dayfirst=True for Indian accounting standards
        self.df['_Parsed_Date'] = pd.to_datetime(self.df[self.date_col], errors='coerce', dayfirst=True, format='mixed')

    # ──────────────────────────────────────────────
    # COLUMN DETECTION
    # ──────────────────────────────────────────────

    def _detect_amount_column(self) -> str:
        """
        Category-aware column detection:
        - Sales ledger → Credit column (revenue inflows)
        - Purchases / Expenses ledger → Debit column (expenditure outflows)
        Falls back to generic 'amount'/'value' columns if specific debit/credit not found.
        """
        cols_lower = {col: str(col).lower().strip() for col in self.df.columns}

        # Step 1: Category-specific preferred column
        if self.category == 'Sales':
            preferred_keywords = ['credit']
        elif self.category in ('Purchases', 'Expenses'):
            preferred_keywords = ['debit']
        else:
            preferred_keywords = []

        # Try preferred column first
        for col, low in cols_lower.items():
            if any(kw in low for kw in preferred_keywords):
                return col

        # Step 2: Generic amount columns
        generic_keywords = ['amount', 'total', 'value', 'net']
        for col, low in cols_lower.items():
            if any(kw in low for kw in generic_keywords):
                return col

        # Step 3: If no preferred found, try the opposite debit/credit as last named fallback
        for col, low in cols_lower.items():
            if 'credit' in low or 'debit' in low:
                return col

        # Step 4: Largest numeric column by absolute sum
        numeric = self.df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric:
            sums = {c: self.df[c].abs().sum() for c in numeric}
            return max(sums, key=sums.get)

        # Step 5: Try to coerce string columns to numeric
        for col in self.df.columns:
            try:
                s = self.df[col].astype(str).str.replace(r'[^\d.\-]', '', regex=True)
                nums = pd.to_numeric(s, errors='coerce')
                if nums.notnull().sum() > len(self.df) * 0.4:
                    self.df[col] = nums
                    return col
            except Exception:
                continue
        return None

    def _detect_date_column(self) -> str:
        for col in self.df.columns:
            if 'date' in str(col).lower():
                return col
        return None

    def _detect_narration_column(self) -> str:
        for col in self.df.columns:
            low = str(col).lower()
            if any(k in low for k in ['narration', 'particular', 'description', 'remark', 'detail']):
                return col
        return None

    def _detect_invoice_column(self) -> str:
        for col in self.df.columns:
            low = str(col).lower()
            if any(k in low for k in ['invoice', 'inv no', 'bill no', 'vch no', 'voucher']):
                return col
        return None

    def _detect_vendor_column(self) -> str:
        """Detect the vendor/party/customer name column."""
        vendor_keywords = ['party', 'vendor', 'customer', 'supplier', 'name',
                           'ledger', 'account', 'particular', 'narration']
        for col in self.df.columns:
            low = str(col).lower().strip()
            if any(kw in low for kw in vendor_keywords):
                # Ensure it's a text column, not numeric
                if self.df[col].dtype == object or str(self.df[col].dtype) == 'string':
                    return col
        # Fallback: use narration column (Tally exports often use 'Particulars')
        return self.narration_col

    # ──────────────────────────────────────────────
    # FORENSIC VENDOR NORMALIZATION
    # ──────────────────────────────────────────────

    _LEGAL_SUFFIXES = re.compile(
        r'\b(pvt\.?\s*ltd\.?|private\s+limited|limited|ltd\.?|llp|'
        r'inc\.?|incorporated|corp\.?|corporation|co\.?|company|'
        r'enterprises?|traders?|associates?|solutions?|'
        r'industries?|international|india|group|mfg|manufacturing|'
        r'services|logistics|trading|agency|agencies|contractors?|'
        r'developers?|builders?|ventures?|holdings?)\b',
        re.IGNORECASE
    )

    def _normalize_vendors(self):
        """Create a _Norm_Vendor column with normalized, collapsed entity names."""
        vcol = self.vendor_col
        if not vcol or vcol not in self.df.columns:
            self.df['_Norm_Vendor'] = ''
            return

        def _norm(name):
            s = str(name).strip().lower()
            if not s or s in ('nan', 'none', ''):
                return ''
            # Strip legal suffixes
            s = self._LEGAL_SUFFIXES.sub('', s)
            # Remove punctuation and extra whitespace
            s = re.sub(r'[^a-z0-9\s]', '', s)
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        # Vectorized apply
        self.df['_Norm_Vendor'] = self.df[vcol].apply(_norm)

        # Fuzzy collapse: group entities that share first 6 chars and len diff <= 3
        unique_norms = self.df['_Norm_Vendor'].unique()
        canon_map = {}
        sorted_norms = sorted([n for n in unique_norms if n], key=len)
        for norm in sorted_norms:
            matched = False
            for canon in canon_map.values():
                if (norm[:6] == canon[:6] and abs(len(norm) - len(canon)) <= 3
                        and len(norm) >= 4):
                    canon_map[norm] = canon
                    matched = True
                    break
            if not matched:
                canon_map[norm] = norm

        self.df['_Norm_Vendor'] = self.df['_Norm_Vendor'].map(
            lambda x: canon_map.get(x, x))

    # ──────────────────────────────────────────────
    # DATA CLEANING
    # ──────────────────────────────────────────────

    def _clean_amounts(self):
        if not self.amount_col:
            return
        col = self.amount_col
        
        def parse_accounting_num(val):
            s = str(val).strip()
            if not s or s.lower() in ('nan', 'none'):
                return 0.0
            # Handle parentheses (1,234.56) -> -1234.56
            is_neg = False
            if s.startswith('(') and s.endswith(')'):
                is_neg = True
                s = s[1:-1]
            
            # Remove currency, commas, etc.
            s = ''.join(c for c in s if c.isdigit() or c in '.-')
            try:
                num = float(s)
                return -num if is_neg else num
            except Exception:
                return 0.0

        self.df[col] = self.df[col].apply(parse_accounting_num)

    def _filter_non_transaction_rows(self):
        """Remove rows that are sub-totals, headers, or balances using vectorized regex."""
        if self.df.empty:
            return
            
        keywords = ['total', 'balance', 'b/f', 'c/f', 'opening', 'closing',
                     'brought forward', 'carried forward', 'grand total',
                     'sub total', 'sub-total']
        
        # Pre-compile case-insensitive regex pattern
        pattern = '|'.join([re.escape(kw) for kw in keywords])
        
        mask = pd.Series(False, index=self.df.index)
        for col in self.df.select_dtypes(include=['object']).columns:
            # Vectorized str.contains is null-safe with na=False
            mask |= self.df[col].astype(str).str.contains(pattern, case=False, regex=True, na=False)
            
        self.df = self.df[~mask].reset_index(drop=True)

    def _optimize_memory(self):
        """Downcast numeric types and categorize low-cardinality strings to reduce RAM."""
        for col in self.df.select_dtypes(include=['float64']).columns:
            self.df[col] = pd.to_numeric(self.df[col], downcast='float')
        for col in self.df.select_dtypes(include=['int64']).columns:
            self.df[col] = pd.to_numeric(self.df[col], downcast='integer')
        for col in self.df.select_dtypes(include=['object']).columns:
            nunique = self.df[col].nunique()
            if nunique / max(len(self.df), 1) < 0.5:  # Less than 50% unique
                self.df[col] = self.df[col].astype('category')

    def _sort_by_value(self):
        if self.amount_col:
            self.df = self.df.sort_values(
                by=self.amount_col, ascending=False, key=lambda x: x.abs()
            ).reset_index(drop=True)

    # ──────────────────────────────────────────────
    # STATISTICS
    # ──────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, Any]:
        total_rows = len(self.df)
        if not self.amount_col:
            return {"count": total_rows, "total_value": 0, "minimum": 0,
                    "maximum": 0, "average": 0}
        amounts = self.df[self.amount_col].abs()
        return {
            "count": total_rows,
            "total_value": float(amounts.sum()),
            "minimum": float(amounts.min()) if not amounts.empty else 0,
            "maximum": float(amounts.max()) if not amounts.empty else 0,
            "average": float(amounts.mean()) if not amounts.empty else 0,
        }

    # ──────────────────────────────────────────────
    # RISK SCORING (10 Indicators)
    # ──────────────────────────────────────────────

    def score_risks(self) -> pd.DataFrame:
        """Score every transaction across 10 risk indicators."""
        data = self.df.copy()
        data['_Risk_Score'] = 0
        data['_Risk_Flags'] = ''

        if not self.amount_col:
            data['_Risk_Category'] = 'Low'
            return data

        amt = data[self.amount_col].abs()
        avg = amt.mean()
        std = amt.std() if not pd.isna(amt.std()) else 0
        dates = data['_Parsed_Date']

        # Use dictionary for flags to avoid index misalignment issues
        flags_dict = {idx: [] for idx in data.index}

        # 1. High Value (above mean + 2σ)
        threshold = avg + 2 * std
        hv_mask = amt > threshold
        data.loc[hv_mask, '_Risk_Score'] += 15
        for idx in hv_mask[hv_mask].index:
            flags_dict[idx].append('High Value')

        # 2. Above Performance Materiality
        if self.performance_materiality > 0:
            mat_mask = amt >= self.performance_materiality
            data.loc[mat_mask, '_Risk_Score'] += 20
            for idx in mat_mask[mat_mask].index:
                flags_dict[idx].append('Above Materiality')

        # 3. Duplicate Amounts
        dup_mask = amt.duplicated(keep=False) & (amt > 0)
        data.loc[dup_mask, '_Risk_Score'] += 10
        for idx in dup_mask[dup_mask].index:
            flags_dict[idx].append('Duplicate Amount')

        # 4. Round Values (Configurable) — only flag non-zero amounts
        round_mask = (amt > 0) & (amt.apply(lambda x: any(x % rv == 0 for rv in self.round_values)))
        data.loc[round_mask, '_Risk_Score'] += 5
        for idx in round_mask[round_mask].index:
            flags_dict[idx].append('Round Value')

        # 5. Month-end Postings (last 3 days of month)
        if self.date_col:
            month_end = dates.dt.is_month_end | (dates.dt.day >= 28)
            data.loc[month_end, '_Risk_Score'] += 5
            for idx in month_end[month_end].index:
                flags_dict[idx].append('Month-End')

        # 6. Weekend Postings
        if self.date_col:
            weekend = dates.dt.dayofweek.isin([5, 6])
            data.loc[weekend, '_Risk_Score'] += 10
            for idx in weekend[weekend].index:
                flags_dict[idx].append('Weekend Posting')

        # 7. Suspicious Narration
        if self.narration_col:
            suspicious_keywords = ['cash', 'adjustment', 'write off', 'write-off',
                                   'reversal', 'correction', 'void', 'cancel',
                                   'refund', 'suspense', 'miscellaneous', 'illegal']
            narr = data[self.narration_col].astype(str).str.lower()
            for kw in suspicious_keywords:
                sus_mask = narr.str.contains(kw, na=False)
                data.loc[sus_mask, '_Risk_Score'] += 8
                for idx in sus_mask[sus_mask].index:
                    if 'Suspicious Narration' not in flags_dict[idx]:
                        flags_dict[idx].append('Suspicious Narration')

        # 8. Unusual Spikes (>3x average)
        spike = amt > (3 * avg)
        spike_only = spike & ~hv_mask
        data.loc[spike_only, '_Risk_Score'] += 12
        for idx in spike_only[spike_only].index:
            flags_dict[idx].append('Unusual Spike')

        # 9. Zero or Negative Values
        zero_neg = data[self.amount_col] <= 0
        data.loc[zero_neg, '_Risk_Score'] += 5
        for idx in zero_neg[zero_neg].index:
            flags_dict[idx].append('Zero/Negative')

        # 10. Below Trivial Threshold
        if self.trivial_threshold > 0:
            trivial = amt <= self.trivial_threshold
            data.loc[trivial, '_Risk_Score'] -= 10
            for idx in trivial[trivial].index:
                flags_dict[idx].append('Below Trivial')

        # 11. FORENSIC: Split Transaction Detection (Optimized)
        if '_Norm_Vendor' in data.columns and self.date_col:
            temp = data[data['_Norm_Vendor'] != ''].copy()
            temp['_Date_Only'] = dates.dt.date
            # Group by Vendor and Day
            grouped = temp.groupby(['_Norm_Vendor', '_Date_Only'])
            for (vendor, day), grp in grouped:
                if len(grp) >= 3 and amt.loc[grp.index].mean() < avg:
                    data.loc[grp.index, '_Risk_Score'] += 18
                    for idx in grp.index:
                        flags_dict[idx].append('Split Transaction')

        # 12. FORENSIC: Round-Tripping Pattern (O(N) Optimized)
        if '_Norm_Vendor' in data.columns and self.date_col:
            # Group transactions by vendor
            temp = data[data['_Norm_Vendor'] != ''].copy()
            raw_amt = data[self.amount_col]
            
            for vendor, grp in temp.groupby('_Norm_Vendor'):
                if len(grp) < 2: continue
                
                # Sort by date for windowing
                vgrp = grp.sort_values('_Parsed_Date')
                # Sliding window: find pos/neg pairs within 7 days
                pos_idx = vgrp[raw_amt > 0].index
                neg_idx = vgrp[raw_amt < 0].index
                
                if len(pos_idx) > 0 and len(neg_idx) > 0:
                    for p_idx in pos_idx:
                        p_date = dates.loc[p_idx]
                        p_val = abs(raw_amt.loc[p_idx])
                        # Find negative transactions within 7 days
                        mask = (dates.loc[neg_idx] >= p_date - pd.Timedelta(days=7)) & \
                               (dates.loc[neg_idx] <= p_date + pd.Timedelta(days=7))
                        candidates = neg_idx[mask]
                        for c_idx in candidates:
                            c_val = abs(raw_amt.loc[c_idx])
                            if p_val > 0 and abs(p_val - c_val) / p_val < 0.05:
                                data.loc[[p_idx, c_idx], '_Risk_Score'] += 15
                                for idx in [p_idx, c_idx]:
                                    if 'Round-Trip' not in flags_dict[idx]:
                                        flags_dict[idx].append('Round-Trip')

        # Compile flags and categories
        data['_Risk_Flags'] = ['; '.join(flags_dict[idx]) if flags_dict[idx] else 'None' for idx in data.index]
        data['_Risk_Score'] = data['_Risk_Score'].clip(lower=0)
        data.loc[data['_Risk_Score'] >= 30, '_Risk_Category'] = 'High'
        data.loc[(data['_Risk_Score'] >= 15) & (data['_Risk_Score'] < 30), '_Risk_Category'] = 'Medium'
        data['_Risk_Category'] = data.get('_Risk_Category', pd.Series('Low', index=data.index)).fillna('Low')

        return data

    # ──────────────────────────────────────────────
    # SAMPLE GENERATION (Dual Mode)
    # ──────────────────────────────────────────────

    def generate_samples(self, sample_pct: float = 20.0,
                         sampling_basis: str = 'count',
                         tod_pct: float = 70.0
                         ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Generate TOD and TOC samples.

        Args:
            sample_pct: Percentage of total to select (combined TOD+TOC)
            sampling_basis: 'count' or 'value'
            tod_pct: Percentage of total samples allocated to TOD (default 70%)

        Returns:
            (tod_df, toc_df) — mutually exclusive DataFrames
        """
        scored = self.score_risks()
        total_rows = len(scored)

        if total_rows == 0:
            empty = pd.DataFrame(columns=scored.columns)
            return empty, empty

        if sampling_basis == 'value':
            return self._sample_by_value(scored, sample_pct, tod_pct)
        else:
            return self._sample_by_count(scored, sample_pct, tod_pct)

    def _unique_vendor_select(self, data: pd.DataFrame, n: int,
                              strategy: str = 'highest',
                              strict_unique: bool = False) -> pd.DataFrame:
        """
        Select n rows prioritizing unique vendors/parties.
        Uses _Norm_Vendor (forensic-normalized) for entity deduplication.

        Args:
            strict_unique: If True, NEVER include duplicate vendors —
                           returns fewer rows than n if unique vendors are exhausted.
                           If False, fills remaining slots with duplicate-vendor rows.
        """
        if n <= 0 or data.empty:
            return data.head(0).copy()

        target = min(n, len(data))
        # Use normalized vendor column for dedup; fall back to raw vendor_col
        use_norm = '_Norm_Vendor' in data.columns
        vcol = '_Norm_Vendor' if use_norm else self.vendor_col
        
        if not vcol or vcol not in data.columns:
            if strategy == 'highest':
                return data.head(target).copy()
            else:
                return data.sample(n=target, random_state=42).copy()

        if strategy == 'highest':
            source = data
        else:
            source = data.sample(frac=1, random_state=42)

        selected = []
        seen_vendors = set()
        deferred = []

        for idx, row in source.iterrows():
            vendor = str(row.get(vcol, '')).strip().lower()
            is_named = vendor and vendor != 'nan' and vendor != ''
            
            if is_named and vendor in seen_vendors:
                deferred.append(idx)
            else:
                if is_named:
                    seen_vendors.add(vendor)
                selected.append(idx)
            
            if len(selected) >= target:
                break
        
        # Only fill from deferred if NOT strict_unique
        if not strict_unique and len(selected) < target and deferred:
            remaining_need = target - len(selected)
            selected.extend(deferred[:remaining_need])

        return data.loc[selected].copy()

    def _sample_by_count(self, scored: pd.DataFrame,
                         sample_pct: float, tod_pct: float
                         ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        SMART OVERLAP COUNT MODE:
        1. Prioritize unique vendors across TOD and TOC.
        2. If target size not met, backfill with repeats (unique transactions).
        """
        total_rows = len(scored)
        target_total = math.ceil(total_rows * sample_pct / 100.0)
        tod_size = math.ceil(target_total * tod_pct / 100.0)
        toc_size = target_total - tod_size

        # Use forensic normalized vendor if available
        vcol = '_Norm_Vendor' if '_Norm_Vendor' in scored.columns else self.vendor_col
        
        # --- Stage 1: Unique Vendor Selection ---
        if vcol and vcol in scored.columns:
            # Best txn per vendor
            vendor_pool = scored.sort_values(by=['_Risk_Score'], ascending=False).groupby(vcol).head(1)
            # Exclude empty / NaN vendor entries properly
            vendor_norm = vendor_pool[vcol].astype(str).str.strip().str.lower()
            vendor_pool = vendor_pool[~vendor_norm.isin(['', 'nan', 'none'])]
            
            # Split this pool 70/30
            pool_tod = vendor_pool.head(tod_size).copy()
            pool_toc = vendor_pool.iloc[tod_size:tod_size+toc_size].copy()
            
            used_indices = set(pool_tod.index) | set(pool_toc.index)
        else:
            pool_tod = scored.head(0).copy()
            pool_toc = scored.head(0).copy()
            used_indices = set()

        # --- Stage 2: Backfill (Safety Valve) ---
        shortfall_tod = tod_size - len(pool_tod)
        shortfall_toc = toc_size - len(pool_toc)
        
        remaining = scored[~scored.index.isin(used_indices)].sort_values(by='_Risk_Score', ascending=False)
        
        if shortfall_tod > 0 and len(remaining) > 0:
            extra_tod = remaining.head(shortfall_tod)
            pool_tod = pd.concat([pool_tod, extra_tod])
            used_indices.update(extra_tod.index)
            remaining = scored[~scored.index.isin(used_indices)].sort_values(by='_Risk_Score', ascending=False)
            print(f"    [COUNT] TOD Backfill: {len(extra_tod)} rows")

        if shortfall_toc > 0 and len(remaining) > 0:
            extra_toc = remaining.head(shortfall_toc)
            pool_toc = pd.concat([pool_toc, extra_toc])
            print(f"    [COUNT] TOC Backfill: {len(extra_toc)} rows")

        tod = pool_tod.copy()
        toc = pool_toc.copy()

        # Labels
        tod['_Audit_Procedure'] = 'Test of Details (TOD)'
        tod['_Selection_Rationale'] = tod.apply(lambda r: self._tod_rationale(r), axis=1)
        tod['_Audit_Remarks'] = ''
        tod['_Supporting_Doc_Status'] = 'Pending'

        toc['_Audit_Procedure'] = 'Test of Controls (TOC)'
        toc['_Control_Objective'] = self._control_objective()
        toc['_Selection_Rationale'] = 'Smart Selection (Prioritized Vendor Diversity)'
        toc['_Control_Testing_Remarks'] = ''
        toc['_Supporting_Doc_Status'] = 'Pending'

        # Cleanup internal columns
        risk_cols = [c for c in tod.columns if c.startswith('_Risk_')]
        tod = tod.drop(columns=risk_cols, errors='ignore')
        toc = toc.drop(columns=risk_cols, errors='ignore')

        return tod, toc

    def _sample_by_count_generic(self, scored: pd.DataFrame, sample_pct: float, tod_pct: float):
        total_samples = math.ceil(len(scored) * sample_pct / 100.0)
        tod_size = math.ceil(total_samples * tod_pct / 100.0)
        tod = scored.head(tod_size).copy()
        toc = scored.iloc[tod_size:total_samples].copy()

        # Add procedure labels
        tod['_Audit_Procedure'] = 'Test of Details (TOD)'
        tod['_Selection_Rationale'] = tod.apply(lambda r: self._tod_rationale(r), axis=1)
        tod['_Audit_Remarks'] = ''
        tod['_Supporting_Doc_Status'] = 'Pending'

        toc['_Audit_Procedure'] = 'Test of Controls (TOC)'
        toc['_Selection_Rationale'] = 'Generic Random Selection'
        toc['_Control_Objective'] = self._control_objective()
        toc['_Control_Testing_Remarks'] = ''
        toc['_Supporting_Doc_Status'] = 'Pending'

        # Cleanup internal columns
        risk_cols = [c for c in tod.columns if c.startswith('_Risk_')]
        tod = tod.drop(columns=risk_cols, errors='ignore')
        toc = toc.drop(columns=risk_cols, errors='ignore')

        return tod, toc

    def _sample_by_value(self, scored: pd.DataFrame,
                         sample_pct: float, tod_pct: float
                         ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Select transactions whose cumulative value ≈ N% of total value."""
        if not self.amount_col:
            return self._sample_by_count(scored, sample_pct, tod_pct)

        total_value = scored[self.amount_col].abs().sum()
        target_value = total_value * sample_pct / 100.0
        tod_target = target_value * tod_pct / 100.0
        toc_target = target_value - tod_target

        print(f"    [VALUE] total_value={total_value:.2f} target={target_value:.2f} tod_target={tod_target:.2f} toc_target={toc_target:.2f}")

        # TOD: Greedily pick highest-value, prioritizing unique vendors
        sorted_data = scored.sort_values(
            by=self.amount_col, ascending=False, key=lambda x: x.abs())

        # Use _Norm_Vendor for forensic-grade entity matching
        norm_col = '_Norm_Vendor' if '_Norm_Vendor' in sorted_data.columns else self.vendor_col
        tod_rows = []
        tod_cumval = 0
        seen_vendors = set()
        deferred = []

        for idx, row in sorted_data.iterrows():
            vendor = str(row.get(norm_col, '')).strip().lower() if norm_col and norm_col in sorted_data.columns else ''
            is_named = vendor and vendor != 'nan' and vendor != ''
            
            if is_named and vendor in seen_vendors:
                deferred.append(idx)
            else:
                if is_named:
                    seen_vendors.add(vendor)
                tod_rows.append(idx)
                tod_cumval += abs(row[self.amount_col])
            
            if tod_cumval >= tod_target:
                break
        
        # Fill from deferred if target not met
        for idx in deferred:
            if tod_cumval >= tod_target:
                break
            tod_rows.append(idx)
            tod_cumval += abs(sorted_data.loc[idx, self.amount_col])

        if not tod_rows:
            tod_rows = [sorted_data.index[0]]
        tod = sorted_data.loc[tod_rows].copy()
        tod_indices = set(tod.index.tolist())

        print(f"    [VALUE] TOD: {len(tod)} rows, cumval={tod_cumval:.2f}")

        # ── ZERO PARTY OVERLAP: Use _Norm_Vendor for forensic entity matching ──
        tod_vendors = set()
        if norm_col and norm_col in tod.columns:
            for v in tod[norm_col].dropna().astype(str):
                v_clean = v.strip().lower()
                if v_clean and v_clean != 'nan':
                    tod_vendors.add(v_clean)
        print(f"    [VALUE] TOD normalized vendors to exclude from TOC: {len(tod_vendors)} — {list(tod_vendors)[:5]}...")

        # TOC: From remaining rows — STRICTLY one per vendor, no party overlap with TOD
        remaining = sorted_data[~sorted_data.index.isin(tod_indices)]
        # Remove any rows whose normalized vendor was already selected in TOD
        if norm_col and norm_col in remaining.columns and tod_vendors:
            remaining = remaining[~remaining[norm_col].astype(str).str.strip().str.lower().isin(tod_vendors)]
        
        toc_rows = []
        toc_cumval = 0
        toc_seen_vendors = set()

        for idx, row in remaining.iterrows():
            vendor = str(row.get(norm_col, '')).strip().lower() if norm_col and norm_col in remaining.columns else ''
            is_named = vendor and vendor != 'nan' and vendor != ''
            
            # Skip if this vendor already in TOC
            if is_named and vendor in toc_seen_vendors:
                continue
            
            if is_named:
                toc_seen_vendors.add(vendor)
            toc_rows.append(idx)
            toc_cumval += abs(row[self.amount_col])
            if toc_cumval >= toc_target:
                break

        toc = sorted_data.loc[toc_rows].copy() if toc_rows else pd.DataFrame(columns=scored.columns)

        print(f"    [VALUE] TOC: {len(toc)} rows, cumval={toc_cumval:.2f}")

        # ── COVERAGE GUARANTEE: Multi-stage backfill ──
        combined_value = tod_cumval + toc_cumval
        if combined_value < target_value:
            all_selected = set(tod.index.tolist()) | set(toc.index.tolist())
            leftover = sorted_data[~sorted_data.index.isin(all_selected)]
            
            if len(leftover) > 0:
                # Stage 1: Try strict unique party backfill
                toc_vendors_set = set()
                if norm_col and norm_col in toc.columns:
                    for v in toc[norm_col].dropna().astype(str):
                        v_clean = v.strip().lower()
                        if v_clean and v_clean != 'nan':
                            toc_vendors_set.add(v_clean)
                all_used = tod_vendors | toc_vendors_set
                
                strict_leftover = leftover
                if norm_col and norm_col in leftover.columns and all_used:
                    strict_leftover = leftover[~leftover[norm_col].astype(str).str.strip().str.lower().isin(all_used)]
                
                # Sort leftover by value desc so we fill the gap fastest
                strict_leftover = strict_leftover.sort_values(by=self.amount_col, ascending=False, key=lambda x: x.abs())
                
                extra_rows = []
                for idx, row in strict_leftover.iterrows():
                    extra_rows.append(idx)
                    combined_value += abs(row[self.amount_col])
                    if combined_value >= target_value:
                        break
                if extra_rows:
                    extra = sorted_data.loc[extra_rows].copy()
                    toc = pd.concat([toc, extra])
                    print(f"    [VALUE] BACKFILL (Stage 1): Added {len(extra)} extra rows to TOC (Strict Party Exclusion)")

                # Stage 2: If still short on value, allow vendor overlap
                if combined_value < target_value:
                    all_selected = set(tod.index.tolist()) | set(toc.index.tolist())
                    leftover = sorted_data[~sorted_data.index.isin(all_selected)]
                    leftover = leftover.sort_values(by=self.amount_col, ascending=False, key=lambda x: x.abs())
                    
                    extra_rows = []
                    for idx, row in leftover.iterrows():
                        extra_rows.append(idx)
                        combined_value += abs(row[self.amount_col])
                        if combined_value >= target_value:
                            break
                    if extra_rows:
                        extra = sorted_data.loc[extra_rows].copy()
                        toc = pd.concat([toc, extra])
                        print(f"    [VALUE] BACKFILL (Stage 2): Added {len(extra)} extra rows to TOC (Relaxed Overlap)")

        print(f"    [VALUE] FINAL: TOD={len(tod)} + TOC={len(toc)} = {len(tod)+len(toc)} rows")

        # Add procedure labels
        tod['_Audit_Procedure'] = 'Test of Details (TOD)'
        tod['_Selection_Rationale'] = tod.apply(
            lambda r: self._tod_rationale(r), axis=1)
        tod['_Audit_Remarks'] = ''
        tod['_Supporting_Doc_Status'] = 'Pending'

        toc['_Audit_Procedure'] = 'Test of Controls (TOC)'
        toc['_Control_Objective'] = self._control_objective()
        toc['_Control_Testing_Remarks'] = ''

        # Remove internal risk columns from output
        risk_cols = [c for c in tod.columns if c.startswith('_Risk_')]
        tod = tod.drop(columns=risk_cols, errors='ignore')
        toc = toc.drop(columns=risk_cols, errors='ignore')

        return tod, toc

    def _stratified_random(self, data: pd.DataFrame, n: int) -> pd.DataFrame:
        """Try month-wise stratified random sampling; fallback to plain random."""
        if self.date_col:
            try:
                dates = pd.to_datetime(data[self.date_col], errors='coerce', dayfirst=True, format='mixed')
                data = data.copy()
                data['_month'] = dates.dt.month
                months = data['_month'].dropna().unique()
                per_month = max(1, n // len(months))
                parts = []
                for m in months:
                    month_data = data[data['_month'] == m]
                    take = min(per_month, len(month_data))
                    if take > 0:
                        parts.append(month_data.sample(n=take, random_state=42))
                result = pd.concat(parts) if parts else pd.DataFrame(columns=data.columns)
                # Fill remaining if needed
                if len(result) < n:
                    leftover = data.drop(result.index)
                    extra = min(n - len(result), len(leftover))
                    if extra > 0:
                        result = pd.concat([result, leftover.sample(n=extra, random_state=42)])
                result = result.head(n)
                if '_month' in result.columns:
                    result = result.drop(columns=['_month'])
                if '_month' in data.columns:
                    data.drop(columns=['_month'], inplace=True, errors='ignore')
                return result
            except Exception:
                pass
        # Plain random fallback
        return data.sample(n=min(n, len(data)), random_state=42)

    def _tod_rationale(self, row) -> str:
        """Generate a human-readable selection rationale for TOD."""
        flags = str(row.get('_Risk_Flags', ''))
        if flags and flags != 'None':
            return f"Selected for substantive testing: {flags}"
        if self.amount_col and row.get(self.amount_col, 0) > 0:
            return "High-value transaction — substantive verification required"
        return "Selected by risk-based sampling algorithm"

    def _control_objective(self) -> str:
        """Return control objective based on audit category."""
        objectives = {
            'Sales': 'Verify authorization, completeness, and accuracy of sales transactions',
            'Expenses': 'Verify approval, classification, and supporting documentation of expenses',
            'Purchases': 'Verify purchase order matching, vendor approval, and receipt confirmation',
        }
        return objectives.get(self.category,
                              'Verify transaction authorization and processing controls')

    # ──────────────────────────────────────────────
    # RISK ANALYSIS SUMMARY
    # ──────────────────────────────────────────────

    def get_risk_analysis(self) -> Dict[str, Any]:
        """Generate risk analysis summary for the Risk Analysis sheet."""
        scored = self.score_risks()
        analysis = {
            'total_transactions': len(scored),
            'high_risk_count': int((scored['_Risk_Category'] == 'High').sum()),
            'medium_risk_count': int((scored['_Risk_Category'] == 'Medium').sum()),
            'low_risk_count': int((scored['_Risk_Category'] == 'Low').sum()),
        }

        if self.amount_col:
            amt = scored[self.amount_col].abs()
            # Duplicate amounts
            dups = scored[amt.duplicated(keep=False) & (amt > 0)]
            analysis['duplicate_amount_count'] = len(dups)
            analysis['duplicate_amount_value'] = float(dups[self.amount_col].abs().sum()) if len(dups) > 0 else 0

            # Round values
            rounds = scored[(amt > 0) & ((amt % 100000 == 0) | (amt % 50000 == 0))]
            analysis['round_value_count'] = len(rounds)

            # Zero/Negative
            analysis['zero_negative_count'] = int((scored[self.amount_col] <= 0).sum())

        if self.date_col:
            try:
                # Reuse cached parsed dates instead of re-parsing
                dates = scored['_Parsed_Date']
                analysis['weekend_posting_count'] = int(dates.dt.dayofweek.isin([5, 6]).sum())
                analysis['month_end_posting_count'] = int((dates.dt.day >= 28).sum())
            except Exception:
                pass

        if self.narration_col:
            narr = scored[self.narration_col].astype(str).str.lower()
            sus_kw = ['cash', 'adjustment', 'write off', 'reversal', 'suspense']
            sus_count = sum(narr.str.contains(kw, na=False).sum() for kw in sus_kw)
            analysis['suspicious_narration_count'] = int(sus_count)

        return analysis

    # ──────────────────────────────────────────────
    # DASHBOARD INSIGHT GENERATOR
    # ──────────────────────────────────────────────

    def get_dashboard_json(self) -> Dict[str, Any]:
        """Generate comprehensive dashboard metrics for the frontend."""
        dashboard: Dict[str, Any] = {}
        scored = self.score_risks()

        # 1. Aggregated Metrics
        stats = self.get_statistics()
        dashboard['metrics'] = stats

        # 2. Risk Concentration — Top 5% by value
        if self.amount_col and len(scored) > 0:
            amt = scored[self.amount_col].abs()
            total_val = amt.sum()
            top_5pct_n = max(1, int(math.ceil(len(scored) * 0.05)))
            top_5pct = amt.nlargest(top_5pct_n)
            dashboard['risk_concentration'] = {
                'top_5pct_count': int(top_5pct_n),
                'top_5pct_value': float(top_5pct.sum()),
                'top_5pct_share': float(top_5pct.sum() / max(total_val, 1)),
                'total_value': float(total_val)
            }
        else:
            dashboard['risk_concentration'] = {
                'top_5pct_count': 0, 'top_5pct_value': 0,
                'top_5pct_share': 0, 'total_value': 0
            }

        # 3. Vendor Gini Coefficient
        if '_Norm_Vendor' in scored.columns and self.amount_col:
            vendor_totals = scored[scored['_Norm_Vendor'] != ''].groupby(
                '_Norm_Vendor')[self.amount_col].apply(lambda x: x.abs().sum())
            if len(vendor_totals) > 1:
                vals = np.sort(vendor_totals.values).astype(float)
                n = len(vals)
                cumvals = np.cumsum(vals)
                gini = (2.0 * np.sum((np.arange(1, n + 1) * vals)) / (n * np.sum(vals))) - (n + 1) / n
                dashboard['vendor_gini'] = round(float(np.clip(gini, 0, 1)), 4)
                # Top 5 vendors by value
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

        # 4. Monthly Trend Analysis + Z-Score Spike Detection
        if self.date_col and self.amount_col:
            try:
                dates = pd.to_datetime(scored[self.date_col], errors='coerce',
                                       dayfirst=True, format='mixed')
                scored_copy = scored.copy()
                scored_copy['_month'] = dates.dt.to_period('M')
                monthly = scored_copy.groupby('_month').agg(
                    txn_count=(self.amount_col, 'count'),
                    txn_value=(self.amount_col, lambda x: float(x.abs().sum()))
                ).reset_index()
                monthly['_month'] = monthly['_month'].astype(str)

                # Z-score on transaction count for spike detection
                counts = monthly['txn_count'].values.astype(float)
                if len(counts) > 2:
                    mu = counts.mean()
                    sigma = counts.std()
                    if sigma > 0:
                        zscores = ((counts - mu) / sigma).tolist()
                    else:
                        zscores = [0.0] * len(counts)
                else:
                    zscores = [0.0] * len(counts)

                trends = []
                for i, row in monthly.iterrows():
                    trends.append({
                        'month': row['_month'],
                        'count': int(row['txn_count']),
                        'value': float(row['txn_value']),
                        'z_score': round(zscores[i], 2),
                        'is_spike': abs(zscores[i]) > 2.0
                    })
                dashboard['monthly_trends'] = trends
            except Exception:
                dashboard['monthly_trends'] = []
        else:
            dashboard['monthly_trends'] = []

        # 5. Risk distribution summary
        dashboard['risk_distribution'] = {
            'high': int((scored['_Risk_Category'] == 'High').sum()),
            'medium': int((scored['_Risk_Category'] == 'Medium').sum()),
            'low': int((scored['_Risk_Category'] == 'Low').sum())
        }

        # 6. Forensic flags summary
        all_flags: List[str] = []
        for f_str in scored['_Risk_Flags']:
            if f_str and f_str != 'None':
                all_flags.extend([f.strip() for f in str(f_str).split(';')])
        flag_counts = dict(Counter(all_flags))
        dashboard['forensic_flags'] = flag_counts

        return dashboard

