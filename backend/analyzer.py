import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
from datetime import datetime

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

        # Clean amounts
        self._clean_amounts()

        # Filter non-transaction rows (totals, balances, headers)
        self._filter_non_transaction_rows()

        # Memory optimization: downcast types
        self._optimize_memory()

        # Sort highest value first
        self._sort_by_value()

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
            except:
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
            except:
                return 0.0

        self.df[col] = self.df[col].apply(parse_accounting_num)

    def _filter_non_transaction_rows(self):
        """Remove rows that are sub-totals, headers, or balances."""
        keywords = ['total', 'balance', 'b/f', 'c/f', 'opening', 'closing',
                     'brought forward', 'carried forward', 'grand total',
                     'sub total', 'sub-total']
        mask = pd.Series(False, index=self.df.index)
        for col in self.df.select_dtypes(include=['object']).columns:
            col_lower = self.df[col].astype(str).str.lower().str.strip()
            col_mask = col_lower.apply(lambda x: any(kw in x for kw in keywords))
            mask |= col_mask
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

        flags = [[] for _ in range(len(data))]

        # 1. High Value (above mean + 2σ)
        threshold = avg + 2 * std
        hv = amt > threshold
        data.loc[hv, '_Risk_Score'] += 15
        for i in hv[hv].index:
            flags[i].append('High Value')

        # 2. Above Performance Materiality
        if self.performance_materiality > 0:
            above_mat = amt >= self.performance_materiality
            data.loc[above_mat, '_Risk_Score'] += 20
            for i in above_mat[above_mat].index:
                flags[i].append('Above Materiality')

        # 3. Duplicate Amounts
        dup_mask = amt.duplicated(keep=False) & (amt > 0)
        data.loc[dup_mask, '_Risk_Score'] += 10
        for i in dup_mask[dup_mask].index:
            flags[i].append('Duplicate Amount')

        # 4. Round Values (multiples of 10000, 50000, 100000)
        round_mask = (amt > 0) & ((amt % 100000 == 0) | (amt % 50000 == 0) | (amt % 10000 == 0))
        data.loc[round_mask, '_Risk_Score'] += 5
        for i in round_mask[round_mask].index:
            flags[i].append('Round Value')

        # 5. Month-end Postings (last 3 days of month)
        if self.date_col:
            try:
                dates = pd.to_datetime(data[self.date_col], errors='coerce', dayfirst=True, format='mixed')
                month_end = dates.dt.is_month_end | (dates.dt.day >= 28)
                data.loc[month_end, '_Risk_Score'] += 5
                for i in month_end[month_end].index:
                    flags[i].append('Month-End')
            except:
                pass

        # 6. Weekend Postings
        if self.date_col:
            try:
                dates = pd.to_datetime(data[self.date_col], errors='coerce', dayfirst=True, format='mixed')
                weekend = dates.dt.dayofweek.isin([5, 6])
                data.loc[weekend, '_Risk_Score'] += 10
                for i in weekend[weekend].index:
                    flags[i].append('Weekend Posting')
            except:
                pass

        # 7. Suspicious Narration
        if self.narration_col:
            suspicious_keywords = ['cash', 'adjustment', 'write off', 'write-off',
                                   'reversal', 'correction', 'void', 'cancel',
                                   'refund', 'suspense', 'miscellaneous']
            narr = data[self.narration_col].astype(str).str.lower()
            for kw in suspicious_keywords:
                sus_mask = narr.str.contains(kw, na=False)
                data.loc[sus_mask, '_Risk_Score'] += 8
                for i in sus_mask[sus_mask].index:
                    if 'Suspicious Narration' not in flags[i]:
                        flags[i].append('Suspicious Narration')

        # 8. Unusual Spikes (>3x average)
        spike = amt > (3 * avg)
        spike_only = spike & ~hv  # Don't double-count with High Value
        data.loc[spike_only, '_Risk_Score'] += 12
        for i in spike_only[spike_only].index:
            flags[i].append('Unusual Spike')

        # 9. Zero or Negative Values
        zero_neg = data[self.amount_col] <= 0
        data.loc[zero_neg, '_Risk_Score'] += 5
        for i in zero_neg[zero_neg].index:
            flags[i].append('Zero/Negative')

        # 10. Below Trivial Threshold
        if self.trivial_threshold > 0:
            trivial = amt <= self.trivial_threshold
            data.loc[trivial, '_Risk_Score'] -= 10  # Lower priority
            for i in trivial[trivial].index:
                flags[i].append('Below Trivial')

        # Compile flags and categories
        data['_Risk_Flags'] = ['; '.join(f) if f else 'None' for f in flags]
        data['_Risk_Score'] = data['_Risk_Score'].clip(lower=0)
        data.loc[data['_Risk_Score'] >= 30, '_Risk_Category'] = 'High'
        data.loc[(data['_Risk_Score'] >= 15) & (data['_Risk_Score'] < 30), '_Risk_Category'] = 'Medium'
        data['_Risk_Category'] = data.get('_Risk_Category', pd.Series('Low', index=data.index))
        data['_Risk_Category'] = data['_Risk_Category'].fillna('Low')

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

        Args:
            strict_unique: If True, NEVER include duplicate vendors —
                           returns fewer rows than n if unique vendors are exhausted.
                           If False, fills remaining slots with duplicate-vendor rows.
        """
        if n <= 0 or data.empty:
            return data.head(0).copy()

        target = min(n, len(data))
        vcol = self.vendor_col
        
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
        """Select N% of total transaction count with unique vendors."""
        import math
        total_rows = len(scored)
        total_samples = math.ceil(total_rows * sample_pct / 100.0)
        tod_size = math.ceil(total_samples * tod_pct / 100.0)
        toc_size = total_samples - tod_size

        print(f"    [COUNT] total_rows={total_rows} target_samples={total_samples} tod_size={tod_size} toc_size={toc_size}")

        # TOD: Highest value, allows duplicate vendors to fill target
        sort_cols = ['_Risk_Score']
        if self.amount_col:
            sort_cols = [self.amount_col, '_Risk_Score']
        sorted_scored = scored.sort_values(by=sort_cols, ascending=False)
        tod = self._unique_vendor_select(sorted_scored, tod_size, strategy='highest',
                                          strict_unique=False)
        tod_indices = set(tod.index.tolist())

        print(f"    [COUNT] TOD selected: {len(tod)} rows")

        # ── ZERO PARTY OVERLAP: Collect all vendor names already in TOD ──
        tod_vendors = set()
        vcol = self.vendor_col
        if vcol and vcol in tod.columns:
            for v in tod[vcol].dropna().astype(str):
                v_clean = v.strip().lower()
                if v_clean and v_clean != 'nan':
                    tod_vendors.add(v_clean)
        print(f"    [COUNT] TOD vendors to exclude from TOC: {len(tod_vendors)}")

        # TOC: Random from rows NOT in TOD AND whose vendor is NOT in TOD
        remaining = scored[~scored.index.isin(tod_indices)]
        if vcol and vcol in remaining.columns and tod_vendors:
            remaining = remaining[~remaining[vcol].astype(str).str.strip().str.lower().isin(tod_vendors)]
        print(f"    [COUNT] Remaining pool for TOC (after party exclusion): {len(remaining)} rows")

        if len(remaining) > 0 and toc_size > 0:
            toc = self._unique_vendor_select(remaining, toc_size, strategy='random',
                                              strict_unique=False)
        else:
            toc = pd.DataFrame(columns=scored.columns)

        print(f"    [COUNT] TOC selected: {len(toc)} rows")

        # ── COVERAGE GUARANTEE: If combined < target, backfill from unused rows ──
        combined = len(tod) + len(toc)
        if combined < total_samples:
            shortfall = total_samples - combined
            all_selected = set(tod.index.tolist()) | set(toc.index.tolist())
            leftover = scored[~scored.index.isin(all_selected)]
            if len(leftover) > 0:
                extra = leftover.sample(n=min(shortfall, len(leftover)), random_state=42)
                toc = pd.concat([toc, extra])
                print(f"    [COUNT] BACKFILL: Added {len(extra)} extra rows to TOC to guarantee {sample_pct}% coverage")

        print(f"    [COUNT] FINAL: TOD={len(tod)} + TOC={len(toc)} = {len(tod)+len(toc)} / {total_rows} = {(len(tod)+len(toc))/total_rows*100:.1f}%")

        # Add procedure labels
        tod = tod.copy()
        toc = toc.copy()
        
        tod['_Audit_Procedure'] = 'Test of Details (TOD)'
        tod['_Selection_Rationale'] = tod.apply(
            lambda r: self._tod_rationale(r), axis=1)
        tod['_Audit_Remarks'] = ''
        tod['_Supporting_Doc_Status'] = 'Pending'

        toc['_Audit_Procedure'] = 'Test of Controls (TOC)'
        toc['_Selection_Rationale'] = 'Random Basis Selection (Zero Overlap with TOD pool)'
        toc['_Control_Objective'] = self._control_objective()
        toc['_Control_Testing_Remarks'] = ''
        toc['_Supporting_Doc_Status'] = 'Pending'

        # Sort TOD by amount descending
        if self.amount_col:
            tod = tod.sort_values(by=self.amount_col, ascending=False,
                                  key=lambda x: x.abs())

        # Remove internal risk columns from output
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

        vcol = self.vendor_col
        tod_rows = []
        tod_cumval = 0
        seen_vendors = set()
        deferred = []

        for idx, row in sorted_data.iterrows():
            vendor = str(row.get(vcol, '')).strip().lower() if vcol and vcol in sorted_data.columns else ''
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

        # ── ZERO PARTY OVERLAP: Collect all vendor names from TOD ──
        tod_vendors = set()
        if vcol and vcol in tod.columns:
            for v in tod[vcol].dropna().astype(str):
                v_clean = v.strip().lower()
                if v_clean and v_clean != 'nan':
                    tod_vendors.add(v_clean)
        print(f"    [VALUE] TOD vendors to exclude from TOC: {len(tod_vendors)} — {list(tod_vendors)[:5]}...")

        # TOC: From remaining rows — STRICTLY one per vendor, no party overlap with TOD
        remaining = sorted_data[~sorted_data.index.isin(tod_indices)]
        # Remove any rows whose vendor was already selected in TOD
        if vcol and vcol in remaining.columns and tod_vendors:
            remaining = remaining[~remaining[vcol].astype(str).str.strip().str.lower().isin(tod_vendors)]
        
        toc_rows = []
        toc_cumval = 0
        toc_seen_vendors = set()

        for idx, row in remaining.iterrows():
            vendor = str(row.get(vcol, '')).strip().lower() if vcol and vcol in remaining.columns else ''
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

        # ── COVERAGE GUARANTEE: If combined value < target, backfill ──
        combined_value = tod_cumval + toc_cumval
        if combined_value < target_value:
            all_selected = set(tod.index.tolist()) | set(toc.index.tolist())
            leftover = sorted_data[~sorted_data.index.isin(all_selected)]
            # Sort leftover by value desc so we fill the gap fastest
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
                print(f"    [VALUE] BACKFILL: Added {len(extra)} extra rows to guarantee {sample_pct}% value coverage")

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
            except:
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
                dates = pd.to_datetime(scored[self.date_col], errors='coerce', dayfirst=True, format='mixed')
                analysis['weekend_posting_count'] = int(dates.dt.dayofweek.isin([5, 6]).sum())
                analysis['month_end_posting_count'] = int((dates.dt.day >= 28).sum())
            except:
                pass

        if self.narration_col:
            narr = scored[self.narration_col].astype(str).str.lower()
            sus_kw = ['cash', 'adjustment', 'write off', 'reversal', 'suspense']
            sus_count = sum(narr.str.contains(kw, na=False).sum() for kw in sus_kw)
            analysis['suspicious_narration_count'] = int(sus_count)

        return analysis
