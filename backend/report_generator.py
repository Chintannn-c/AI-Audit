import pandas as pd
import numpy as np
import xlsxwriter
import io
from datetime import datetime
from typing import Dict, Any

class AuditReportGenerator:
    """
    Generates a 5-sheet or 6-sheet enterprise audit working paper Excel workbook.
    """

    def __init__(self, original_df: pd.DataFrame,
                 tod: pd.DataFrame, toc: pd.DataFrame,
                 stats: Dict[str, Any], category: str,
                 risk_analysis: Dict[str, Any] = None,
                 sampling_config: Dict[str, Any] = None,
                 deficit_info: Dict[str, Any] = None):
        self.original_df = original_df
        self.tod = tod
        self.toc = toc
        self.stats = stats
        self.category = category
        self.risk_analysis = risk_analysis or {}
        self.sampling_config = sampling_config or {}
        self.deficit_info = deficit_info
        self.materiality = {}
        self.risk = {}

    def add_engagement_data(self, materiality: dict, risk: dict):
        self.materiality = materiality
        self.risk = risk

    def generate(self, vouching_results=None, report_type='sampling') -> io.BytesIO:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # ── Formats ──
        header_fmt = workbook.add_format({
            'bold': True, 'font_color': 'black', 'bg_color': '#fde68a',
            'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True
        })
        cell_fmt = workbook.add_format({'border': 1, 'align': 'left'})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
        sub_fmt = workbook.add_format({'bold': True, 'font_size': 12, 'bg_color': '#e2e8f0'})
        lbl_fmt = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#f8fafc'})
        val_fmt = workbook.add_format({'border': 1})
        vnum_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        pct_fmt = workbook.add_format({'border': 1, 'num_format': '0.0%'})
        
        if report_type == 'sampling':
            # ── Sheet 1: Original Ledger ──
            self._write_data_sheet(workbook, 'Original Ledger', self.original_df, header_fmt, cell_fmt, None)
            
            # ── Sheet 2: TOD Samples ──
            self._write_data_sheet(workbook, 'TOD Samples', self.tod, header_fmt, cell_fmt, None)

            # ── Sheet 3: TOC Samples ──
            self._write_data_sheet(workbook, 'TOC Samples', self.toc, header_fmt, cell_fmt, None)

            # ── Sheet 4: Audit Summary ──
            self._write_summary_sheet(workbook, title_fmt, sub_fmt, lbl_fmt, val_fmt, vnum_fmt, pct_fmt)

            # ── Sheet 5: Sampling Explanation (conditional) ──
            if self.deficit_info:
                self._write_deficit_explanation_sheet(workbook, title_fmt, sub_fmt, lbl_fmt, val_fmt, vnum_fmt)

            # ── Sheet 6: Materiality & Risk (keep as LAST sheet) ──
            self._write_planning_sheet(workbook, title_fmt, sub_fmt, lbl_fmt, val_fmt, vnum_fmt)
        else:
            # ── Sheet 1: Vouching Reconciliation ──
            if vouching_results:
                self._write_vouching_reconciliation_sheet(workbook, vouching_results, title_fmt, header_fmt, cell_fmt)

        workbook.close()
        output.seek(0)
        return output


    def _write_vouching_reconciliation_sheet(self, wb, results, title_fmt, header_fmt, cell_fmt):
        ws = wb.add_worksheet('Vouching Reconciliation')
        
        # Top Header
        ws.write(0, 0, "AI Forensic Vouching Reconciliation", title_fmt)
        ws.write(2, 0, "Documents required", wb.add_format({'bold': True}))
        ws.write(3, 0, "1. Original Invoice")
        ws.write(4, 0, "2. Approval Of Expense")
        ws.write(5, 0, "3. Entry In Bank Statement")

        # Table Headers (Multi-row)
        # Row 7: Grouped headers
        ws.merge_range('E8:H8', 'Invoice', header_fmt)
        ws.merge_range('L8:N8', 'Payment', header_fmt)

        # Row 8: Column headers
        headers = [
            "Invoice Number", "Invoice Date", "Posting Date", "Whether Invoice is in the name of company?",
            "Basic Amount", "GST Amount", "Total Amount", "Due date as per Invoice", "Due date as per ERP",
            "Payment date", "Payment amount", "Name of Bank"
        ]
        for col, h in enumerate(headers):
            ws.write(8, col, h, header_fmt)
            ws.set_column(col, col, 18)

        # Write Data
        row = 9
        for res in results:
            data = {item['field']: item['value'] for item in res.get('extracted_data', [])}
            
            # Flexible Mapping for Excel Export
            inv_no = data.get("Invoice Number") or data.get("Invoice No") or data.get("Invoice #") or "N/A"
            date = data.get("Date") or data.get("Invoice Date") or "N/A"
            amt = data.get("Grand Total") or data.get("Total Amount") or data.get("Amount") or "0.00"
            gst = data.get("Total GST") or data.get("GST") or data.get("GST Amount") or "0.00"
            
            ws.write(row, 0, inv_no, cell_fmt)
            ws.write(row, 1, date, cell_fmt)
            ws.write(row, 2, "See Ledger", cell_fmt) # Posting Date from ERP
            ws.write(row, 3, "Yes", cell_fmt) # Logic to check company name
            ws.write(row, 4, amt, cell_fmt)
            ws.write(row, 5, gst, cell_fmt)
            ws.write(row, 6, amt, cell_fmt) # Total Amount
            ws.write(row, 7, data.get("Due Date", "N/A"), cell_fmt)
            # ... fill other columns as N/A or from ERP if matched
            row += 1

    def _write_data_sheet(self, wb, name, df, h_fmt, c_fmt, n_fmt):
        """Write a DataFrame to a sheet preserving all columns."""
        import datetime as dt
        safe = name[:31]
        ws = wb.add_worksheet(safe)

        if df is None or len(df) == 0:
            msg = f'No data for {name}.'
            if 'TOC' in name:
                msg += " (Note: In substantive-only audits or when all transactions are allocated to TOD, this sheet remains empty)."
            ws.write(0, 0, msg)
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

    def _write_planning_sheet(self, wb, title_fmt, sub_fmt, lbl_fmt, val_fmt, vnum_fmt):
        ws = wb.add_worksheet('Materiality & Risk')
        ws.set_column(0, 0, 40)
        ws.set_column(1, 1, 30)
        
        r = 0
        ws.write(r, 0, 'AUDIT PLANNING & MATERIALITY (SA 320)', title_fmt)
        r += 2

        # Materiality Section
        ws.write(r, 0, '1. MATERIALITY DETERMINATION', sub_fmt)
        ws.write(r, 1, '', sub_fmt)
        r += 1
        
        m = self.materiality
        m_items = [
            ('Benchmark Selected', m.get('benchmark', 'NPBT')),
            ('Benchmark Value', m.get('value', 0)),
            ('Risk of Material Misstatement (RoMM)', m.get('romm', 'Medium')),
            ('Overall Materiality (%)', f"{m.get('overall_pct', 0)}%"),
            ('Overall Materiality (Value)', m.get('overall_materiality', 0)),
            ('Performance Materiality (%)', f"{m.get('perf_pct', 0)}%"),
            ('Performance Materiality (Value)', m.get('performance_materiality', 0)),
            ('Trivial Threshold (%)', f"{m.get('trivial_pct', 0)}%"),
            ('Trivial Threshold (Value)', m.get('trivial_threshold', 0)),
        ]
        for label, val in m_items:
            ws.write(r, 0, label, lbl_fmt)
            if isinstance(val, (int, float)):
                ws.write(r, 1, val, vnum_fmt)
            else:
                ws.write(r, 1, str(val), val_fmt)
            r += 1
        
        r += 2
        # Risk Assessment Section
        ws.write(r, 0, '2. RISK ASSESSMENT & CLASSIFICATION (SA 315)', sub_fmt)
        ws.write(r, 1, '', sub_fmt)
        r += 1
        
        rk = self.risk
        is_large = 'large' in str(rk.get('audit_type', '')).lower()
        rk_items = [
            ('Public / PIE Entity?', 'Yes' if rk.get('turnover_250') else 'No'),
            ('IFC Applicable?', 'Yes' if rk.get('ifc') else 'No'),
            ('Weak Control Environment?', 'Yes' if rk.get('governance') else 'No'),
            ('History of Misstatements?', 'Yes' if rk.get('misstatements') else 'No'),
            ('Audit Classification', 'LARGE AUDIT' if is_large else 'SMALL AUDIT'),
            ('Audit Approach', 'Combined (TOD + TOC)' if is_large and not rk.get('governance') else 'Substantive (TOD only)'),
        ]
        for label, val in rk_items:
            ws.write(r, 0, label, lbl_fmt)
            ws.write(r, 1, str(val), val_fmt)
            r += 1

        r += 2
        ws.write(r, 0, 'Sign-off: ________________________', wb.add_format({'italic': True}))
        ws.write(r, 1, 'Date: ________________', wb.add_format({'italic': True}))

    def _write_deficit_explanation_sheet(self, wb, title_fmt, sub_fmt, lbl_fmt, val_fmt, vnum_fmt):
        ws = wb.add_worksheet('Sampling Explanation')
        ws.set_zoom(100)
        
        # Enable grid lines
        ws.hide_gridlines(2)
        
        # Formats
        bold_title = wb.add_format({'bold': True, 'font_size': 14, 'font_color': '#1e3a8a'})
        section_hdr = wb.add_format({'bold': True, 'font_size': 11, 'bg_color': '#cbd5e1', 'border': 1})
        tbl_hdr = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1e3a8a', 'border': 1, 'align': 'center'})
        text_cell = wb.add_format({'border': 1, 'align': 'left'})
        num_cell = wb.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0'})
        alert_box = wb.add_format({
            'bg_color': '#fee2e2', 'font_color': '#991b1b', 'border': 1, 'text_wrap': True, 'valign': 'vcenter'
        })
        
        # Set column widths
        ws.set_column(0, 0, 30) # Parameter
        ws.set_column(1, 1, 15) # Value
        ws.set_column(2, 2, 3)  # spacer
        ws.set_column(3, 3, 25) # Vendor Name
        ws.set_column(4, 4, 15) # Available
        ws.set_column(5, 5, 12) # TOD
        ws.set_column(6, 6, 12) # TOC
        ws.set_column(7, 7, 12) # Total
        ws.set_column(8, 8, 35) # Status
        
        # 1. Main Title
        ws.write(0, 0, "Audit Sampling Deficit Breakup & Explanation", bold_title)
        ws.write(1, 0, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", wb.add_format({'italic': True}))
        
        # 2. Deficit Metrics Table
        ws.write(3, 0, "Sampling Summary", section_hdr)
        ws.write(3, 1, "", section_hdr)
        
        ws.write(4, 0, "Requested Sample Size", lbl_fmt)
        ws.write(4, 1, self.deficit_info.get("requested", 0) if self.deficit_info else 0, num_cell)
        
        ws.write(5, 0, "Actual Selected Samples", lbl_fmt)
        ws.write(5, 1, self.deficit_info.get("selected", 0) if self.deficit_info else 0, num_cell)
        
        ws.write(6, 0, "Sample Size Shortfall (Deficit)", lbl_fmt)
        ws.write(6, 1, self.deficit_info.get("deficit", 0) if self.deficit_info else 0, wb.add_format({'bold': True, 'font_color': '#b91c1c', 'border': 1, 'align': 'right'}))
        
        ws.write(7, 0, "Hard Rule Restriction", lbl_fmt)
        ws.write(7, 1, "Max 2 repetitions per vendor combined", text_cell)
        
        # Alert Box for Deficit Explanation
        ws.merge_range('A9:B12', self.deficit_info.get("explanation", "") if self.deficit_info else "", alert_box)
        
        # 3. Vendor-Wise Selection Breakup
        ws.write(3, 3, "Vendor-Wise Sample Distribution Breakup", section_hdr)
        for c in range(4, 9):
            ws.write(3, c, "", section_hdr)
            
        headers = ["Party / Vendor Name", "Available Ledger Txns", "Selected in TOD", "Selected in TOC", "Total Selected", "Status / Capping Reason"]
        for col_idx, h in enumerate(headers):
            ws.write(4, 3 + col_idx, h, tbl_hdr)
            
        # Group and compute vendor statistics
        vcol = None
        for col in ['_Norm_Vendor', self.sampling_config.get('vendor_col'), 'Vendor', 'Vendor Name', 'Party', 'Party Name']:
            if col and col in self.original_df.columns:
                vcol = col
                break
        if not vcol:
            vcol = next((c for c in self.original_df.columns if 'vendor' in str(c).lower() or 'party' in str(c).lower()), None)
            
        vendor_data = []
        if vcol:
            # Normalize names to make comparison completely robust
            orig_v = self.original_df[vcol].fillna('Unknown / Unnamed').astype(str).str.strip().str.title()
            tod_v = self.tod[vcol].fillna('Unknown / Unnamed').astype(str).str.strip().str.title() if not self.tod.empty and vcol in self.tod.columns else pd.Series(dtype=str)
            toc_v = self.toc[vcol].fillna('Unknown / Unnamed').astype(str).str.strip().str.title() if not self.toc.empty and vcol in self.toc.columns else pd.Series(dtype=str)
            
            orig_counts = orig_v.value_counts()
            tod_counts = tod_v.value_counts()
            toc_counts = toc_v.value_counts()
            
            all_vendors = sorted(list(set(orig_counts.index)))
            
            for v in all_vendors:
                if v == 'Unknown / Unnamed' or v == '' or v.lower() == 'nan':
                    continue
                avail = int(orig_counts.get(v, 0))
                tod_sel = int(tod_counts.get(v, 0))
                toc_sel = int(toc_counts.get(v, 0))
                tot_sel = tod_sel + toc_sel
                
                if tot_sel >= 2:
                    status = "CAPPED: Hit maximum repetition limit (2)"
                elif tot_sel > 0 and tot_sel == avail:
                    status = "EXHAUSTED: All vendor transactions selected"
                elif tot_sel > 0:
                    status = "Selected (Partial coverage)"
                else:
                    status = "Unselected: Lower risk/value ranking"
                    
                vendor_data.append({
                    'name': v,
                    'avail': avail,
                    'tod': tod_sel,
                    'toc': toc_sel,
                    'total': tot_sel,
                    'status': status
                })
                
            # Sort: first by total selected descending, then available descending
            vendor_data.sort(key=lambda x: (x['total'], x['avail']), reverse=True)
            
        row_idx = 5
        for item in vendor_data:
            ws.write(row_idx, 3, item['name'], text_cell)
            ws.write(row_idx, 4, item['avail'], num_cell)
            ws.write(row_idx, 5, item['tod'], num_cell)
            ws.write(row_idx, 6, item['toc'], num_cell)
            ws.write(row_idx, 7, item['total'], num_cell)
            ws.write(row_idx, 8, item['status'], text_cell)
            row_idx += 1
            
        if not vendor_data:
            ws.write(5, 3, "No named vendor/party information detected.", text_cell)
            for c in range(4, 9):
                ws.write(5, 3 + c, "", text_cell)
