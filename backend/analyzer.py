import pandas as pd
import numpy as np
import re
import math
import logging
from typing import Dict, Any, Tuple, List, Optional
from dataclasses import dataclass, field
from collections import Counter

logger = logging.getLogger(__name__)

@dataclass
class AuditConfig:
    """Externalized Configuration for Statutory Audit Engine."""
    round_values: List[float] = field(default_factory=lambda: [1000, 5000, 10000, 50000, 100000, 500000, 1000000])
    suspicious_keywords: List[str] = field(default_factory=lambda: [
        'cash', 'adjustment', 'write off', 'write-off', 'reversal', 
        'correction', 'void', 'cancel', 'refund', 'suspense', 
        'miscellaneous', 'illegal'
    ])
    round_trip_window_days: int = 7
    high_value_sigma_multiplier: float = 2.0
    strata_allocation: Tuple[float, float, float] = (0.60, 0.30, 0.10)
    tod_pct: float = 70.0
    fuzzy_match_threshold: float = 85.0


class DataCleaner:
    """Handles category-aware column detection, amount parsing, row filtering, and memory optimization."""
    def __init__(self, config: AuditConfig):
        self.config = config

    def detect_columns(self, df: pd.DataFrame, category: str) -> Dict[str, Optional[str]]:
        cols_lower = {col: str(col).lower().strip() for col in df.columns}
        
        # 1. Amount Column
        amount_col = None
        preferred_keywords = ['credit'] if category == 'Sales' else ['debit'] if category in ('Purchases', 'Expenses') else []
        for col, low in cols_lower.items():
            if any(kw in low for kw in preferred_keywords):
                amount_col = col
                break
        
        if not amount_col:
            generic_keywords = ['amount', 'total', 'value', 'net']
            for col, low in cols_lower.items():
                if any(kw in low for kw in generic_keywords):
                    amount_col = col
                    break
        
        if not amount_col:
            for col, low in cols_lower.items():
                if 'credit' in low or 'debit' in low:
                    amount_col = col
                    break
        
        if not amount_col:
            numeric = df.select_dtypes(include=[np.number]).columns.tolist()
            if numeric:
                sums = {c: df[c].abs().sum() for c in numeric}
                amount_col = max(sums, key=sums.get)
        
        if not amount_col:
            for col in df.columns:
                try:
                    s = df[col].astype(str).str.replace(r'[^\d.\-]', '', regex=True)
                    nums = pd.to_numeric(s, errors='coerce')
                    if nums.notnull().sum() > len(df) * 0.4:
                        amount_col = col
                        break
                except Exception:
                    continue

        # 2. Date Column
        date_col = next((c for c in df.columns if 'date' in str(c).lower()), None)
        
        # 3. Narration Column (Prioritize strong matches to prevent particulars conflicts)
        narration_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['narration', 'description', 'remark'])), None)
        if not narration_col:
            narration_col = next((c for c in df.columns if any(k in str(c).lower() for k in ['particular', 'detail'])), None)
        
        # 4. Invoice Column (Exclude date_col and any column with 'date' in the name)
        invoice_col = next((c for c in df.columns if c != date_col and 'date' not in str(c).lower() and any(k in str(c).lower() for k in ['invoice', 'inv no', 'bill no', 'vch no', 'voucher'])), None)
        
        # 5. Vendor/Party Column
        vendor_col = None
        vendor_keywords = ['party', 'vendor', 'customer', 'supplier', 'name', 'ledger', 'account', 'particular', 'narration']
        for col in df.columns:
            low = str(col).lower().strip()
            if any(kw in low for kw in vendor_keywords):
                if df[col].dtype == object or str(df[col].dtype) == 'string':
                    vendor_col = col
                    break
        if not vendor_col:
            vendor_col = narration_col

        return {
            'amount_col': amount_col,
            'date_col': date_col,
            'narration_col': narration_col,
            'invoice_col': invoice_col,
            'vendor_col': vendor_col
        }

    def clean_amounts(self, df: pd.DataFrame, amount_col: str) -> pd.Series:
        def parse_accounting_num(val):
            s = str(val).strip()
            if not s or s.lower() in ('nan', 'none'):
                return 0.0
            is_neg = False
            if s.startswith('(') and s.endswith(')'):
                is_neg = True
                s = s[1:-1]
            s = ''.join(c for c in s if c.isdigit() or c in '.-')
            try:
                num = float(s)
                return -num if is_neg else num
            except Exception:
                return 0.0
        return df[amount_col].apply(parse_accounting_num)

    def filter_non_transaction_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        keywords = ['total', 'balance', 'b/f', 'c/f', 'opening', 'closing',
                    'brought forward', 'carried forward', 'grand total',
                    'sub total', 'sub-total']
        pattern = '|'.join([re.escape(kw) for kw in keywords])
        mask = pd.Series(False, index=df.index)
        for col in df.select_dtypes(include=['object']).columns:
            mask |= df[col].astype(str).str.contains(pattern, case=False, regex=True, na=False)
        return df[~mask].reset_index(drop=True)

    def optimize_memory(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in df.select_dtypes(include=['float64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='float')
        for col in df.select_dtypes(include=['int64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='integer')
        for col in df.select_dtypes(include=['object']).columns:
            nunique = df[col].nunique()
            if nunique / max(len(df), 1) < 0.5:
                df[col] = df[col].astype('category')
        return df


class VendorNormalizer:
    """Performs forensic entity collapsing via resilient string matching with jellyfish/rapidfuzz fallback."""
    _LEGAL_SUFFIXES = re.compile(
        r'\b(pvt\.?\s*ltd\.?|private\s+limited|limited|ltd\.?|llp|'
        r'inc\.?|incorporated|corp\.?|corporation|co\.?|company|'
        r'enterprises?|traders?|associates?|solutions?|'
        r'industries?|international|india|group|mfg|manufacturing|'
        r'services|logistics|trading|agency|agencies|contractors?|'
        r'developers?|builders?|ventures?|holdings?)\b',
        re.IGNORECASE
    )

    def __init__(self, config: AuditConfig):
        self.config = config

    def normalize(self, df: pd.DataFrame, vendor_col: Optional[str]) -> pd.DataFrame:
        df = df.copy()
        if not vendor_col or vendor_col not in df.columns:
            df['_Norm_Vendor'] = ''
            return df

        def _norm(name):
            s = str(name).strip().lower()
            if not s or s in ('nan', 'none', ''):
                return ''
            s = self._LEGAL_SUFFIXES.sub('', s)
            s = re.sub(r'[^a-z0-9\s]', '', s)
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        df['_Norm_Vendor'] = df[vendor_col].apply(_norm)
        unique_norms = [n for n in df['_Norm_Vendor'].unique() if n]
        if not unique_norms:
            return df

        try:
            import importlib
            fuzz = importlib.import_module("rapidfuzz.fuzz")
            def is_match(a, b):
                # Ensure short distinct suffix terms do not collide (e.g. Vendor A vs Vendor B)
                words_a = a.split()
                words_b = b.split()
                if words_a and words_b and words_a[-1] != words_b[-1]:
                    if len(words_a[-1]) == 1 or len(words_b[-1]) == 1:
                        return False
                return fuzz.token_set_ratio(a, b) >= self.config.fuzzy_match_threshold
        except ImportError:
            import difflib
            def is_match(a, b):
                words_a = a.split()
                words_b = b.split()
                if words_a and words_b and words_a[-1] != words_b[-1]:
                    if len(words_a[-1]) == 1 or len(words_b[-1]) == 1:
                        return False
                return difflib.SequenceMatcher(None, a, b).ratio() * 100 >= self.config.fuzzy_match_threshold

        canon_map = {}
        sorted_norms = sorted(unique_norms, key=len)
        for norm in sorted_norms:
            matched = False
            for canon in canon_map.values():
                if is_match(norm, canon):
                    canon_map[norm] = canon
                    matched = True
                    break
            if not matched:
                canon_map[norm] = norm

        df['_Norm_Vendor'] = df['_Norm_Vendor'].map(lambda x: canon_map.get(x, x))
        return df


class RiskScorer:
    """Executes O(N) vectorized forensic patterns and computes 12 risk indicators."""
    def __init__(self, config: AuditConfig):
        self.config = config

    def score_risks(self, df: pd.DataFrame, category: str, amount_col: Optional[str],
                    date_col: Optional[str], narration_col: Optional[str],
                    vendor_col: Optional[str], performance_materiality: float,
                    trivial_threshold: float) -> pd.DataFrame:
        data = df.copy()
        data['_Risk_Score'] = 0
        data['_Risk_Flags'] = ''
        
        if not amount_col:
            data['_Risk_Category'] = 'Low'
            return data

        amt = data[amount_col].abs()
        avg = amt.mean() if not amt.empty else 0
        std = amt.std() if not pd.isna(amt.std()) else 0
        dates = data['_Parsed_Date']

        flags_dict = {idx: [] for idx in data.index}

        # 1. High Value
        threshold = avg + self.config.high_value_sigma_multiplier * std
        hv_mask = amt > threshold
        data.loc[hv_mask, '_Risk_Score'] += 15
        for idx in hv_mask[hv_mask].index:
            flags_dict[idx].append('High Value')

        # 2. Above Performance Materiality
        if performance_materiality > 0:
            mat_mask = amt >= performance_materiality
            data.loc[mat_mask, '_Risk_Score'] += 20
            for idx in mat_mask[mat_mask].index:
                flags_dict[idx].append('Above Materiality')

        # 3. Duplicate Amounts
        dup_mask = amt.duplicated(keep=False) & (amt > 0)
        data.loc[dup_mask, '_Risk_Score'] += 10
        for idx in dup_mask[dup_mask].index:
            flags_dict[idx].append('Duplicate Amount')

        # 4. Round Values
        round_mask = (amt > 0) & (amt.apply(lambda x: any(x % rv == 0 for rv in self.config.round_values)))
        data.loc[round_mask, '_Risk_Score'] += 5
        for idx in round_mask[round_mask].index:
            flags_dict[idx].append('Round Value')

        # 5. Month-end Postings
        if date_col:
            month_end = dates.dt.is_month_end | (dates.dt.day >= 28)
            data.loc[month_end, '_Risk_Score'] += 5
            for idx in month_end[month_end].index:
                flags_dict[idx].append('Month-End')

        # 6. Weekend Postings
        if date_col:
            weekend = dates.dt.dayofweek.isin([5, 6])
            data.loc[weekend, '_Risk_Score'] += 10
            for idx in weekend[weekend].index:
                flags_dict[idx].append('Weekend Posting')

        # 7. Suspicious Narration
        if narration_col:
            narr = data[narration_col].astype(str).str.lower()
            for kw in self.config.suspicious_keywords:
                sus_mask = narr.str.contains(kw, na=False)
                data.loc[sus_mask, '_Risk_Score'] += 8
                for idx in sus_mask[sus_mask].index:
                    if 'Suspicious Narration' not in flags_dict[idx]:
                        flags_dict[idx].append('Suspicious Narration')

        # 8. Unusual Spikes
        spike = amt > (3 * avg)
        spike_only = spike & ~hv_mask
        data.loc[spike_only, '_Risk_Score'] += 12
        for idx in spike_only[spike_only].index:
            flags_dict[idx].append('Unusual Spike')

        # 9. Zero or Negative Values
        zero_neg = data[amount_col] <= 0
        data.loc[zero_neg, '_Risk_Score'] += 5
        for idx in zero_neg[zero_neg].index:
            flags_dict[idx].append('Zero/Negative')

        # 10. Below Trivial Threshold
        if trivial_threshold > 0:
            trivial = amt <= trivial_threshold
            data.loc[trivial, '_Risk_Score'] -= 10
            for idx in trivial[trivial].index:
                flags_dict[idx].append('Below Trivial')

        # 11. FORENSIC: Split Transaction Detection
        if '_Norm_Vendor' in data.columns and date_col:
            temp = data[data['_Norm_Vendor'] != ''].copy()
            temp['_Date_Only'] = dates.dt.date
            grouped = temp.groupby(['_Norm_Vendor', '_Date_Only'])
            for (vendor, day), grp in grouped:
                if len(grp) >= 3 and amt.loc[grp.index].mean() < avg:
                    data.loc[grp.index, '_Risk_Score'] += 18
                    for idx in grp.index:
                        flags_dict[idx].append('Split Transaction')

        # 12. FORENSIC: Round-Tripping Pattern (O(N) Vectorized merge-based self-join)
        if vendor_col and '_Norm_Vendor' in data.columns and date_col:
            pos = data[data[amount_col] > 0][['_Norm_Vendor', '_Parsed_Date', amount_col]].copy()
            neg = data[data[amount_col] < 0][['_Norm_Vendor', '_Parsed_Date', amount_col]].copy()
            
            if not pos.empty and not neg.empty:
                merged = pos.reset_index().merge(neg.reset_index(), on='_Norm_Vendor', suffixes=('_p', '_n'))
                merged['_Val_P'] = merged[f'{amount_col}_p'].abs()
                merged['_Val_N'] = merged[f'{amount_col}_n'].abs()
                val_close = (merged['_Val_P'] - merged['_Val_N']).abs() / merged['_Val_P'] < 0.05
                days_diff = (merged['_Parsed_Date_p'] - merged['_Parsed_Date_n']).abs().dt.days
                time_close = days_diff <= self.config.round_trip_window_days
                
                round_trip_pairs = merged[val_close & time_close]
                if not round_trip_pairs.empty:
                    rt_indices = set(round_trip_pairs['index_p']).union(set(round_trip_pairs['index_n']))
                    data.loc[list(rt_indices), '_Risk_Score'] += 15
                    for idx in rt_indices:
                        if 'Round-Trip' not in flags_dict[idx]:
                            flags_dict[idx].append('Round-Trip')

        data['_Risk_Flags'] = ['; '.join(flags_dict[idx]) if flags_dict[idx] else 'None' for idx in data.index]
        data['_Risk_Score'] = data['_Risk_Score'].clip(lower=0)
        data.loc[data['_Risk_Score'] >= 30, '_Risk_Category'] = 'High'
        data.loc[(data['_Risk_Score'] >= 15) & (data['_Risk_Score'] < 30), '_Risk_Category'] = 'Medium'
        data['_Risk_Category'] = data.get('_Risk_Category', pd.Series('Low', index=data.index)).fillna('Low')
        
        return data


class SampleEngine:
    """Enforces stratified monthly sampling, vendor-party uniqueness, and backfill fallbacks."""
    def __init__(self, config: AuditConfig):
        self.config = config

    def sample_stratified(self, scored: pd.DataFrame, tod_target: int, toc_target: int,
                          amount_col: str, vendor_col: Optional[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        data = scored.copy()
        
        if '_Parsed_Date' not in data.columns:
            data['_Parsed_Date'] = pd.to_datetime(data[self.date_col], errors='coerce', dayfirst=True, format='mixed') if self.date_col else pd.NaT
            
        data['_Month'] = data['_Parsed_Date'].dt.month
        months = sorted(data['_Month'].dropna().unique())
        
        vcol = '_Norm_Vendor' if '_Norm_Vendor' in data.columns else vendor_col
        amt_col = amount_col or (data.select_dtypes(include=[np.number]).columns[0] if not data.select_dtypes(include=[np.number]).columns.empty else None)
        
        if not amt_col:
            empty = pd.DataFrame(columns=scored.columns)
            return empty, empty

        # --- Strata Division (Value Buckets) ---
        data = data.sort_values(by=amt_col, ascending=False, key=lambda x: x.abs())
        n = len(data)
        high_strata = data.iloc[:max(1, int(n * 0.1))]
        mid_strata = data.iloc[max(1, int(n * 0.1)):max(2, int(n * 0.4))]
        low_strata = data.iloc[max(2, int(n * 0.4)):]

        tod_indices = []
        toc_indices = []
        seen_vendors = set()

        def is_vendor_used(row):
            if not vcol or vcol not in row: return False
            v = str(row[vcol]).strip().lower()
            return v in seen_vendors if (v and v not in ('nan', 'none', '')) else False

        def mark_vendor_used(row):
            if not vcol or vcol not in row: return
            v = str(row[vcol]).strip().lower()
            if v and v not in ('nan', 'none', ''):
                seen_vendors.add(v)

        # --- Stage 1: Monthly Random Selection (reserving High Value exclusively for Stratified Stage) ---
        for m in months:
            if len(tod_indices) >= tod_target: break
            month_data = data[data['_Month'] == m].sample(frac=1, random_state=42)
            for idx, row in month_data.iterrows():
                if not is_vendor_used(row):
                    tod_indices.append(idx)
                    mark_vendor_used(row)
                    break
        
        # --- Stage 2: Stratified Filling for TOD ---
        alloc_high, alloc_mid, alloc_low = self.config.strata_allocation
        strata_map = [
            (high_strata, alloc_high),
            (mid_strata, alloc_mid),
            (low_strata, alloc_low)
        ]
        
        for strata_df, alloc in strata_map:
            strata_target = int(tod_target * alloc)
            strata_current = len([i for i in tod_indices if i in strata_df.index])
            
            remaining_in_strata = strata_df[~strata_df.index.isin(tod_indices)]
            for idx, row in remaining_in_strata.iterrows():
                if strata_current >= strata_target or len(tod_indices) >= tod_target:
                    break
                if not is_vendor_used(row):
                    tod_indices.append(idx)
                    mark_vendor_used(row)
                    strata_current += 1

        # Fallback if allocations couldn't be met due to vendor dedupe
        if len(tod_indices) < tod_target:
            remaining = data[~data.index.isin(tod_indices)].sort_values(by=amt_col, ascending=False, key=lambda x: x.abs())
            for idx, row in remaining.iterrows():
                if len(tod_indices) >= tod_target: break
                if not is_vendor_used(row):
                    tod_indices.append(idx)
                    mark_vendor_used(row)

        # CRITICAL FALLBACK FOR TOD: Allow duplicate vendors if target count is otherwise unreachable
        if len(tod_indices) < tod_target:
            remaining = data[~data.index.isin(tod_indices)].sort_values(by=amt_col, ascending=False, key=lambda x: x.abs())
            for idx, row in remaining.iterrows():
                if len(tod_indices) >= tod_target: break
                tod_indices.append(idx)

        # --- Stage 3: Monthly Random Selection for TOC ---
        if toc_target > 0:
            for m in months:
                if len(toc_indices) >= toc_target: break
                month_data = data[(data['_Month'] == m) & (~data.index.isin(tod_indices))].sample(frac=1, random_state=42)
                for idx, row in month_data.iterrows():
                    if not is_vendor_used(row):
                        toc_indices.append(idx)
                        mark_vendor_used(row)
                        break

        # --- Stage 4: Fill TOC to target (Random overall) ---
        if toc_target > 0 and len(toc_indices) < toc_target:
            remaining_toc = data[~data.index.isin(tod_indices) & ~data.index.isin(toc_indices)].sample(frac=1, random_state=42)
            for idx, row in remaining_toc.iterrows():
                if len(toc_indices) >= toc_target: break
                if not is_vendor_used(row):
                    toc_indices.append(idx)
                    mark_vendor_used(row)

        # CRITICAL FALLBACK FOR TOC: Allow duplicates to reach target count
        if toc_target > 0 and len(toc_indices) < toc_target:
            remaining_toc = data[~data.index.isin(tod_indices) & ~data.index.isin(toc_indices)].sample(frac=1, random_state=42)
            for idx, row in remaining_toc.iterrows():
                if len(toc_indices) >= toc_target: break
                toc_indices.append(idx)

        # Prepare final DataFrames
        tod = data.loc[tod_indices].copy()
        toc = data.loc[toc_indices].copy()

        if amt_col:
            if not tod.empty:
                tod = tod.sort_values(by=amt_col, ascending=False, key=lambda x: x.abs())
            if not toc.empty:
                toc = toc.sort_values(by=amt_col, ascending=False, key=lambda x: x.abs())

        tod['_Audit_Procedure'] = 'Test of Details (TOD)'
        tod['_Selection_Rationale'] = tod.apply(lambda r: self._tod_rationale(r, amt_col), axis=1)
        tod['_Audit_Remarks'] = ''
        tod['_Supporting_Doc_Status'] = 'Pending'

        toc['_Audit_Procedure'] = 'Test of Controls (TOC)'
        toc['_Control_Objective'] = self._control_objective(scored.attrs.get('category', 'Sales'))
        toc['_Selection_Rationale'] = 'Random Selection (Month-wise Stratified)'
        toc['_Control_Testing_Remarks'] = ''
        toc['_Supporting_Doc_Status'] = 'Pending'

        internal_cols = [c for c in tod.columns if c.startswith('_Risk_') or c in ['_Month']]
        tod = tod.drop(columns=internal_cols, errors='ignore')
        toc = toc.drop(columns=internal_cols, errors='ignore')

        return tod, toc

    def _tod_rationale(self, row, amt_col) -> str:
        flags = str(row.get('_Risk_Flags', ''))
        if flags and flags != 'None':
            return f"Selected for substantive testing: {flags}"
        if amt_col and row.get(amt_col, 0) > 0:
            return "High-value transaction — substantive verification required"
        return "Selected by risk-based sampling algorithm"

    def _control_objective(self, category: str) -> str:
        objectives = {
            'Sales': 'Verify authorization, completeness, and accuracy of sales transactions',
            'Expenses': 'Verify approval, classification, and supporting documentation of expenses',
            'Purchases': 'Verify purchase order matching, vendor approval, and receipt confirmation',
        }
        return objectives.get(category, 'Verify transaction authorization and processing controls')


class DashboardBuilder:
    """Builds highly diagnostic metrics and monthly trend Z-Score spike flags for the client UI."""
    def __init__(self, config: AuditConfig):
        self.config = config

    def build_dashboard(self, scored: pd.DataFrame, amount_col: Optional[str],
                        date_col: Optional[str], narration_col: Optional[str]) -> Dict[str, Any]:
        dashboard = {}
        total_rows = len(scored)
        
        # Statistics
        if amount_col:
            amounts = scored[amount_col].abs()
            stats = {
                "count": total_rows,
                "total_value": float(amounts.sum()),
                "minimum": float(amounts.min()) if not amounts.empty else 0,
                "maximum": float(amounts.max()) if not amounts.empty else 0,
                "average": float(amounts.mean()) if not amounts.empty else 0,
            }
        else:
            stats = {"count": total_rows, "total_value": 0, "minimum": 0, "maximum": 0, "average": 0}
        dashboard['metrics'] = stats

        # Risk Concentration
        if amount_col and total_rows > 0:
            amt = scored[amount_col].abs()
            total_val = amt.sum()
            top_5pct_n = max(1, int(math.ceil(total_rows * 0.05)))
            top_5pct = amt.nlargest(top_5pct_n)
            dashboard['risk_concentration'] = {
                'top_5pct_count': int(top_5pct_n),
                'top_5pct_value': float(top_5pct.sum()),
                'top_5pct_share': float(top_5pct.sum() / max(total_val, 1)),
                'total_value': float(total_val)
            }
        else:
            dashboard['risk_concentration'] = {'top_5pct_count': 0, 'top_5pct_value': 0, 'top_5pct_share': 0, 'total_value': 0}

        # Gini Coefficient
        if '_Norm_Vendor' in scored.columns and amount_col:
            vendor_totals = scored[scored['_Norm_Vendor'] != ''].groupby('_Norm_Vendor')[amount_col].apply(lambda x: x.abs().sum())
            if len(vendor_totals) > 1:
                vals = np.sort(vendor_totals.values).astype(float)
                n = len(vals)
                gini = (2.0 * np.sum((np.arange(1, n + 1) * vals)) / (n * np.sum(vals))) - (n + 1) / n
                dashboard['vendor_gini'] = round(float(np.clip(gini, 0, 1)), 4)
                top5 = vendor_totals.nlargest(5)
                dashboard['top_vendors'] = [{'name': str(k).title(), 'value': float(v)} for k, v in top5.items()]
            else:
                dashboard['vendor_gini'] = 0.0
                dashboard['top_vendors'] = []
        else:
            dashboard['vendor_gini'] = 0.0
            dashboard['top_vendors'] = []

        # Monthly Trend Analysis
        if date_col and amount_col:
            try:
                dates = pd.to_datetime(scored[date_col], errors='coerce', dayfirst=True, format='mixed')
                scored_copy = scored.copy()
                scored_copy['_month'] = dates.dt.to_period('M')
                monthly = scored_copy.groupby('_month').agg(
                    txn_count=(amount_col, 'count'),
                    txn_value=(amount_col, lambda x: float(x.abs().sum()))
                ).reset_index()
                monthly['_month'] = monthly['_month'].astype(str)

                counts = monthly['txn_count'].values.astype(float)
                if len(counts) > 2:
                    mu = counts.mean()
                    sigma = counts.std()
                    zscores = (((counts - mu) / sigma).tolist()) if sigma > 0 else [0.0] * len(counts)
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
            except Exception as e:
                logger.warning(f"Dashboard trends generation failed: {e}")
                dashboard['monthly_trends'] = []
        else:
            dashboard['monthly_trends'] = []

        # Risk distribution
        dashboard['risk_distribution'] = {
            'high': int((scored['_Risk_Category'] == 'High').sum()),
            'medium': int((scored['_Risk_Category'] == 'Medium').sum()),
            'low': int((scored['_Risk_Category'] == 'Low').sum())
        }

        # Forensic flags
        all_flags = []
        for f_str in scored['_Risk_Flags']:
            if f_str and f_str != 'None':
                all_flags.extend([f.strip() for f in str(f_str).split(';')])
        dashboard['forensic_flags'] = dict(Counter(all_flags))

        return dashboard


class AuditAnalyzer:
    """
    Enterprise AI Audit Sampling Engine.
    Refactored orchestrator keeping public API fully backwards-compatible.
    """
    def __init__(self, df: pd.DataFrame, category: str,
                 trivial_threshold: float = 0,
                 performance_materiality: float = 0,
                 config: Optional[AuditConfig] = None):
        self.config = config or AuditConfig()
        self.category = category
        self.trivial_threshold = trivial_threshold
        self.performance_materiality = performance_materiality
        self.raw_df = df.copy()
        
        # 1. Clean & Validate Input
        self.validate(df)
        self.df = df.dropna(how='all').copy()
        
        # Components
        self.cleaner = DataCleaner(self.config)
        self.normalizer = VendorNormalizer(self.config)
        self.scorer = RiskScorer(self.config)
        self.engine = SampleEngine(self.config)
        self.builder = DashboardBuilder(self.config)
        
        # Detect Columns
        detected = self.cleaner.detect_columns(self.df, self.category)
        self.amount_col = detected['amount_col']
        self.date_col = detected['date_col']
        self.narration_col = detected['narration_col']
        self.invoice_col = detected['invoice_col']
        self.vendor_col = detected['vendor_col']
        
        # Clean amounts
        if self.amount_col:
            self.df[self.amount_col] = self.cleaner.clean_amounts(self.df, self.amount_col)
        self.df = self.cleaner.filter_non_transaction_rows(self.df)
        
        # Cache pre-parsed dates
        if self.date_col:
            self.df['_Parsed_Date'] = pd.to_datetime(self.df[self.date_col], errors='coerce', dayfirst=True, format='mixed')
        else:
            self.df['_Parsed_Date'] = pd.NaT
            
        # Normalize Vendors
        self.df = self.normalizer.normalize(self.df, self.vendor_col)
        
        # Optimize Memory
        self.df = self.cleaner.optimize_memory(self.df)
        
        # Sort by Value
        if self.amount_col:
            self.df = self.df.sort_values(
                by=self.amount_col, ascending=False, key=lambda x: x.abs()
            ).reset_index(drop=True)
            
        self.df.attrs['category'] = self.category
        self._scored_cache = None

    def validate(self, df: pd.DataFrame):
        """Input validator running at the entry point."""
        if df.empty:
            raise ValueError("DataFrame is empty after cleaning.")
        if self.category not in ('Sales', 'Purchases', 'Expenses'):
            raise ValueError(f"Unknown category: {self.category}")

    def score_risks(self) -> pd.DataFrame:
        """Cached wrapper for computing the 12 forensic risk indicators."""
        if self._scored_cache is None:
            self._scored_cache = self.scorer.score_risks(
                self.df, self.category, self.amount_col, self.date_col,
                self.narration_col, self.vendor_col, self.performance_materiality,
                self.trivial_threshold
            )
        return self._scored_cache.copy()

    def generate_samples(self, sample_pct: float = 20.0,
                          sampling_basis: str = 'count',
                          tod_pct: float = 70.0,
                          target_count: Optional[int] = None,
                          audit_type: str = 'large'
                          ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        scored = self.score_risks()
        total_rows = len(scored)
        if total_rows == 0:
            empty = pd.DataFrame(columns=scored.columns)
            return empty, empty

        if target_count is not None:
            total_needed = min(target_count, total_rows)
        else:
            total_needed = math.ceil(total_rows * sample_pct / 100.0)

        if audit_type == 'small':
            tod_size = total_needed
            toc_size = 0
        else:
            tod_size = math.ceil(total_needed * tod_pct / 100.0)
            toc_size = total_needed - tod_size

        return self.engine.sample_stratified(scored, tod_size, toc_size, self.amount_col, self.vendor_col)

    def get_statistics(self) -> Dict[str, Any]:
        total_rows = len(self.df)
        if not self.amount_col:
            return {"count": total_rows, "total_value": 0, "minimum": 0, "maximum": 0, "average": 0}
        amounts = self.df[self.amount_col].abs()
        return {
            "count": total_rows,
            "total_value": float(amounts.sum()),
            "minimum": float(amounts.min()) if not amounts.empty else 0,
            "maximum": float(amounts.max()) if not amounts.empty else 0,
            "average": float(amounts.mean()) if not amounts.empty else 0,
        }

    def get_risk_analysis(self) -> Dict[str, Any]:
        scored = self.score_risks()
        analysis = {
            'total_transactions': len(scored),
            'high_risk_count': int((scored['_Risk_Category'] == 'High').sum()),
            'medium_risk_count': int((scored['_Risk_Category'] == 'Medium').sum()),
            'low_risk_count': int((scored['_Risk_Category'] == 'Low').sum()),
        }

        if self.amount_col:
            amt = scored[self.amount_col].abs()
            dups = scored[amt.duplicated(keep=False) & (amt > 0)]
            analysis['duplicate_amount_count'] = len(dups)
            analysis['duplicate_amount_value'] = float(dups[self.amount_col].abs().sum()) if len(dups) > 0 else 0

            rounds = scored[(amt > 0) & (amt.apply(lambda x: any(x % rv == 0 for rv in self.config.round_values[:4])))]
            analysis['round_value_count'] = len(rounds)
            analysis['zero_negative_count'] = int((scored[self.amount_col] <= 0).sum())

        if self.date_col:
            try:
                dates = scored['_Parsed_Date']
                analysis['weekend_posting_count'] = int(dates.dt.dayofweek.isin([5, 6]).sum())
                analysis['month_end_posting_count'] = int((dates.dt.day >= 28).sum())
            except Exception as e:
                logger.warning(f"Risk analysis dates extraction failed: {e}")

        if self.narration_col:
            narr = scored[self.narration_col].astype(str).str.lower()
            sus_count = sum(narr.str.contains(kw, na=False).sum() for kw in self.config.suspicious_keywords[:5])
            analysis['suspicious_narration_count'] = int(sus_count)

        return analysis

    def get_dashboard_json(self) -> Dict[str, Any]:
        scored = self.score_risks()
        return self.builder.build_dashboard(scored, self.amount_col, self.date_col, self.narration_col)
