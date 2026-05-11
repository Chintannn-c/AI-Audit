import pandas as pd
import numpy as np
import xlsxwriter
import io
from datetime import datetime
from typing import Dict, Any

class AuditReportGenerator:
    """
    Generates a 5-sheet enterprise audit working paper Excel workbook.
    """

    def __init__(self, original_df: pd.DataFrame,
                 tod: pd.DataFrame, toc: pd.DataFrame,
                 stats: Dict[str, Any], category: str,
                 risk_analysis: Dict[str, Any] = None,
                 sampling_config: Dict[str, Any] = None):
        self.original_df = original_df
        self.tod = tod
        self.toc = toc
        self.stats = stats
        self.category = category
        self.risk_analysis = risk_analysis or {}
        self.sampling_config = sampling_config or {}
        self.materiality = {}
        self.risk = {}

    def add_engagement_data(self, materiality: dict, risk: dict):
        self.materiality = materiality
        self.risk = risk

    def generate(self) -> io.BytesIO:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # ── Formats ──
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 16, 'font_color': '#1e293b',
            'bottom': 2, 'bottom_color': '#4F46E5'
        })
        subtitle_fmt = workbook.add_format({
            'bold': True, 'font_size': 12, 'font_color': '#4F46E5',
            'top': 1, 'bottom': 1
        })
        header_fmt = workbook.add_format({
            'bold': True, 'font_color': 'white', 'bg_color': '#4F46E5',
            'border': 1, 'align': 'center', 'valign': 'vcenter',
            'text_wrap': True, 'font_size': 10
        })
        cell_fmt = workbook.add_format({
            'border': 1, 'font_size': 10, 'valign': 'vcenter'
        })
        num_fmt = workbook.add_format({
            'border': 1, 'num_format': '#,##0.00', 'font_size': 10,
            'valign': 'vcenter'
        })
        pct_fmt = workbook.add_format({
            'border': 1, 'num_format': '0.00%', 'font_size': 10,
            'valign': 'vcenter'
        })
        label_fmt = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#f1f5f9',
            'font_size': 10
        })
        value_fmt = workbook.add_format({
            'border': 1, 'font_size': 10, 'bg_color': '#f8fafc'
        })
        value_num_fmt = workbook.add_format({
            'border': 1, 'num_format': '#,##0.00', 'font_size': 10,
            'bg_color': '#f8fafc'
        })
        high_fmt = workbook.add_format({
            'border': 1, 'font_size': 10, 'bg_color': '#fef2f2',
            'font_color': '#dc2626'
        })
        med_fmt = workbook.add_format({
            'border': 1, 'font_size': 10, 'bg_color': '#fffbeb',
            'font_color': '#d97706'
        })
        low_fmt = workbook.add_format({
            'border': 1, 'font_size': 10, 'bg_color': '#f0fdf4',
            'font_color': '#16a34a'
        })

        # ── Sheet 1: Original Ledger ──
        self._write_data_sheet(workbook, 'Original Ledger',
                               self.original_df, header_fmt, cell_fmt, num_fmt)

        # ── Sheet 2: Test of Details ──
        self._write_data_sheet(workbook, 'Test of Details TOD',
                               self.tod, header_fmt, cell_fmt, num_fmt)

        # ── Sheet 3: Test of Controls ──
        self._write_data_sheet(workbook, 'Test of Controls TOC',
                               self.toc, header_fmt, cell_fmt, num_fmt)

        # -- Sheet 4: Sample Summary --
        self._write_summary_sheet(workbook, title_fmt, subtitle_fmt,
                                   label_fmt, value_fmt, value_num_fmt, pct_fmt)

        # -- Sheet 5: Risk Analysis --
        self._write_risk_sheet(workbook, title_fmt, subtitle_fmt,
                                label_fmt, value_fmt, value_num_fmt,
                                high_fmt, med_fmt, low_fmt)

        workbook.close()
        output.seek(0)
        return output

    def _write_data_sheet(self, wb, name, df, h_fmt, c_fmt, n_fmt):
        """Write a DataFrame to a sheet preserving all columns."""
        import datetime as dt
        safe = name[:31]
        ws = wb.add_worksheet(safe)

        if df is None or len(df) == 0:
            ws.write(0, 0, f'No data for {name}')
            return

        # Date format for datetime columns
        date_fmt = wb.add_format({
            'border': 1, 'font_size': 10, 'valign': 'vcenter',
            'num_format': 'dd-mmm-yyyy'
        })

        # Detect which columns are date-type
        date_cols = set()
        for col in df.columns:
            col_lower = str(col).lower()
            if 'date' in col_lower:
                date_cols.add(col)
            elif hasattr(df[col], 'dtype'):
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    date_cols.add(col)

        # Write headers
        for i, col in enumerate(df.columns):
            display_name = str(col).lstrip('_').replace('_', ' ')
            ws.write(0, i, display_name, h_fmt)
            max_len = max(len(display_name),
                          df[col].astype(str).str.len().max() if len(df) > 0 else 0)
            ws.set_column(i, i, min(35, max(12, max_len + 2)))

        # Write data
        for r, row in enumerate(df.values):
            for c, val in enumerate(row):
                col_name = df.columns[c]
                fmt = c_fmt

                # Handle NaN / None
                if val is None:
                    ws.write(r + 1, c, '', c_fmt)
                    continue
                if isinstance(val, float) and pd.isna(val):
                    ws.write(r + 1, c, '', c_fmt)
                    continue
                try:
                    if not isinstance(val, str) and pd.isna(val):
                        ws.write(r + 1, c, '', c_fmt)
                        continue
                except (TypeError, ValueError):
                    pass

                # Date handling
                if col_name in date_cols:
                    try:
                        if isinstance(val, (dt.datetime, dt.date, pd.Timestamp)):
                            ws.write_datetime(r + 1, c, val, date_fmt)
                            continue
                        # Try to parse string/number as date
                        parsed = pd.to_datetime(val, errors='coerce', dayfirst=True)
                        if pd.notna(parsed):
                            ws.write_datetime(r + 1, c, parsed.to_pydatetime(), date_fmt)
                            continue
                    except:
                        pass

                # Numeric handling
                if isinstance(val, (int, float, np.integer, np.floating)):
                    try:
                        ws.write(r + 1, c, val, n_fmt)
                    except:
                        ws.write(r + 1, c, str(val), c_fmt)
                    continue

                # Everything else as string
                try:
                    ws.write(r + 1, c, val, c_fmt)
                except:
                    ws.write(r + 1, c, str(val), c_fmt)

        ws.freeze_panes(1, 0)
        if len(df.columns) > 0:
            ws.autofilter(0, 0, len(df), len(df.columns) - 1)

    def _write_summary_sheet(self, wb, title_fmt, sub_fmt,
                              lbl_fmt, val_fmt, vnum_fmt, pct_fmt):
        ws = wb.add_worksheet('Sample Summary')
        ws.set_column(0, 0, 35)
        ws.set_column(1, 1, 25)
        ws.set_column(2, 2, 25)

        r = 0
        ws.write(r, 0, 'AUDIT SAMPLING SUMMARY', title_fmt)
        ws.write(r, 1, '', title_fmt)
        ws.write(r, 2, '', title_fmt)
        r += 1
        ws.write(r, 0, f'Generated: {datetime.now().strftime("%d-%b-%Y %H:%M")}', val_fmt)
        ws.write(r, 1, f'Category: {self.category}', val_fmt)
        r += 2

        # Engagement Setup
        ws.write(r, 0, 'ENGAGEMENT PARAMETERS', sub_fmt)
        ws.write(r, 1, '', sub_fmt)
        r += 1
        for k, v in self.materiality.items():
            ws.write(r, 0, k.replace('_', ' ').title(), lbl_fmt)
            if isinstance(v, (int, float)):
                ws.write(r, 1, v, vnum_fmt)
            else:
                ws.write(r, 1, str(v), val_fmt)
            r += 1
        r += 1

        # Sampling Configuration
        ws.write(r, 0, 'SAMPLING CONFIGURATION', sub_fmt)
        ws.write(r, 1, '', sub_fmt)
        r += 1
        config_items = [
            ('Sampling Basis', self.sampling_config.get('basis', 'count').title()),
            ('Sample Percentage', f"{self.sampling_config.get('sample_pct', 0)}%"),
            ('TOD Allocation', f"{self.sampling_config.get('tod_pct', 70)}%"),
            ('TOC Allocation', f"{100 - self.sampling_config.get('tod_pct', 70)}%"),
        ]
        for label, value in config_items:
            ws.write(r, 0, label, lbl_fmt)
            ws.write(r, 1, value, val_fmt)
            r += 1
        r += 1

        # Population Stats
        ws.write(r, 0, 'POPULATION STATISTICS', sub_fmt)
        ws.write(r, 1, '', sub_fmt)
        r += 1
        stats_items = [
            ('Total Transactions', self.stats.get('count', 0)),
            ('Total Ledger Value', self.stats.get('total_value', 0)),
            ('Maximum Transaction', self.stats.get('maximum', 0)),
            ('Average Transaction', self.stats.get('average', 0)),
            ('Minimum Transaction', self.stats.get('minimum', 0)),
        ]
        for label, value in stats_items:
            ws.write(r, 0, label, lbl_fmt)
            if isinstance(value, float):
                ws.write(r, 1, value, vnum_fmt)
            else:
                ws.write(r, 1, value, val_fmt)
            r += 1
        r += 1

        # Sample Results
        ws.write(r, 0, 'SAMPLE RESULTS', sub_fmt)
        ws.write(r, 1, 'Count', sub_fmt)
        ws.write(r, 2, 'Value (₹)', sub_fmt)
        r += 1

        tod_value = 0
        toc_value = 0
        # Detect amount column — try exact config match first, then keywords
        amt_col_exact = self.sampling_config.get('amount_col', '')
        amt_cols = []
        if amt_col_exact and amt_col_exact in self.tod.columns:
            amt_cols = [amt_col_exact]
        if not amt_cols:
            # Broaden search: credit/debit used by Sales/Purchases ledgers
            amt_cols = [c for c in self.tod.columns
                        if any(kw in str(c).lower()
                               for kw in ['credit', 'debit', 'amount', 'value', 'total'])]
        if amt_cols:
            ac = amt_cols[0]
            tod_value = float(self.tod[ac].abs().sum()) if len(self.tod) > 0 else 0
            toc_value = float(self.toc[ac].abs().sum()) if len(self.toc) > 0 else 0


        results = [
            ('Test of Details (TOD)', len(self.tod), tod_value),
            ('Test of Controls (TOC)', len(self.toc), toc_value),
            ('Total Selected', len(self.tod) + len(self.toc), tod_value + toc_value),
        ]
        for label, count, value in results:
            ws.write(r, 0, label, lbl_fmt)
            ws.write(r, 1, count, val_fmt)
            ws.write(r, 2, value, vnum_fmt)
            r += 1

        total_count = self.stats.get('count', 1)
        total_val = self.stats.get('total_value', 1)
        r += 1
        ws.write(r, 0, 'Transaction Coverage', lbl_fmt)
        coverage_count = (len(self.tod) + len(self.toc)) / max(total_count, 1)
        ws.write(r, 1, coverage_count, pct_fmt)
        r += 1
        ws.write(r, 0, 'Value Coverage', lbl_fmt)
        coverage_val = (tod_value + toc_value) / max(total_val, 1)
        ws.write(r, 1, coverage_val, pct_fmt)

    def _write_risk_sheet(self, wb, title_fmt, sub_fmt,
                           lbl_fmt, val_fmt, vnum_fmt,
                           high_fmt, med_fmt, low_fmt):
        ws = wb.add_worksheet('Risk Analysis')
        ws.set_column(0, 0, 35)
        ws.set_column(1, 1, 20)
        ws.set_column(2, 2, 20)

        r = 0
        ws.write(r, 0, 'AI RISK ANALYSIS REPORT', title_fmt)
        ws.write(r, 1, '', title_fmt)
        r += 2

        # Risk Distribution
        ws.write(r, 0, 'RISK DISTRIBUTION', sub_fmt)
        ws.write(r, 1, '', sub_fmt)
        r += 1

        ra = self.risk_analysis
        risk_items = [
            ('High Risk Transactions', ra.get('high_risk_count', 0), high_fmt),
            ('Medium Risk Transactions', ra.get('medium_risk_count', 0), med_fmt),
            ('Low Risk Transactions', ra.get('low_risk_count', 0), low_fmt),
            ('Total Transactions', ra.get('total_transactions', 0), val_fmt),
        ]
        for label, value, fmt in risk_items:
            ws.write(r, 0, label, lbl_fmt)
            ws.write(r, 1, value, fmt)
            r += 1
        r += 1

        # Anomaly Detection
        ws.write(r, 0, 'ANOMALY DETECTION', sub_fmt)
        ws.write(r, 1, '', sub_fmt)
        r += 1

        anomalies = [
            ('Duplicate Amount Entries', ra.get('duplicate_amount_count', 0)),
            ('Duplicate Amount Total Value', ra.get('duplicate_amount_value', 0)),
            ('Round Value Entries', ra.get('round_value_count', 0)),
            ('Zero/Negative Entries', ra.get('zero_negative_count', 0)),
            ('Weekend Postings', ra.get('weekend_posting_count', 0)),
            ('Month-End Postings', ra.get('month_end_posting_count', 0)),
            ('Suspicious Narrations', ra.get('suspicious_narration_count', 0)),
        ]
        for label, value in anomalies:
            ws.write(r, 0, label, lbl_fmt)
            if isinstance(value, float):
                ws.write(r, 1, value, vnum_fmt)
            else:
                ws.write(r, 1, value, val_fmt)
            r += 1
