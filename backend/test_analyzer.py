import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from backend.analyzer import AuditAnalyzer, AuditConfig, DataCleaner, RiskScorer

class TestAuditAnalyzerRefactored(unittest.TestCase):
    
    def setUp(self):
        # Create synthetic high-quality test data
        self.data_dict = {
            'Voucher Date': ['01-01-2026', '15-01-2026', '28-02-2026', '15-03-2026', '29-03-2026', 
                             '15-04-2026', '15-05-2026', '15-06-2026', '15-07-2026', '15-08-2026', 
                             '15-09-2026', '15-10-2026', '15-11-2026', '15-12-2026', '20-12-2026'],
            'Particulars': ['Reliance Industries Ltd', 'Reliance Retail Pvt Ltd', 'Tata Motors Ltd',
                            'Cash Account', 'Adjustment Entry', 'Vendor A', 'Vendor B', 'Vendor C',
                            'Vendor D', 'Vendor E', 'Vendor F', 'Vendor G', 'Vendor H', 'Vendor I', 'Vendor J'],
            'Vch No': ['INV-001', 'INV-002', 'INV-003', 'INV-004', 'INV-005', 'INV-006', 'INV-007', 
                       'INV-008', 'INV-009', 'INV-010', 'INV-011', 'INV-012', 'INV-013', 'INV-014', 'INV-015'],
            'Debit': [150000.0, 5000.0, "(10000.0)", 2000.0, 50000.0, 12000.0, 15000.0, 18000.0,
                      22000.0, 25000.0, 30000.0, 35000.0, 40000.0, 45000.0, 60000.0],
            'Narration': ['Payment received', 'Store purchase', 'Correction of error', 
                           'Cash withdrawal', 'Suspense clear', 'Regular payment', 'Regular payment',
                           'Regular payment', 'Regular payment', 'Regular payment', 'Regular payment',
                           'Regular payment', 'Regular payment', 'Regular payment', 'Regular payment']
        }
        self.df = pd.DataFrame(self.data_dict)

    def test_input_validation(self):
        # Empty DataFrame raises ValueError
        empty_df = pd.DataFrame()
        with self.assertRaises(ValueError):
            AuditAnalyzer(empty_df, 'Sales')

        # Invalid Category raises ValueError
        with self.assertRaises(ValueError):
            AuditAnalyzer(self.df, 'InvalidCategory')

    def test_column_detection_and_cleaning(self):
        analyzer = AuditAnalyzer(self.df, 'Purchases')
        self.assertEqual(analyzer.amount_col, 'Debit')
        self.assertEqual(analyzer.date_col, 'Voucher Date')
        self.assertEqual(analyzer.narration_col, 'Narration')
        self.assertEqual(analyzer.invoice_col, 'Vch No')
        self.assertEqual(analyzer.vendor_col, 'Particulars')

        # Parentheses parsing check (10000.0 in Credit/Debit should be -10000.0)
        self.assertAlmostEqual(analyzer.df.loc[analyzer.df['Vch No'] == 'INV-003', 'Debit'].values[0], -10000.0)

    def test_fuzzy_vendor_collapsing(self):
        analyzer = AuditAnalyzer(self.df, 'Purchases')
        # Reliance Industries Ltd and Reliance Retail Pvt Ltd should NOT collapse
        # since their lengths are too different or tokens are distinct
        norms = analyzer.df['_Norm_Vendor'].tolist()
        reliance_ind = norms[0]
        reliance_ret = norms[1]
        self.assertNotEqual(reliance_ind, reliance_ret)

    def test_risk_scoring(self):
        analyzer = AuditAnalyzer(self.df, 'Purchases')
        scored = analyzer.score_risks()
        
        # Above Materiality flag check (e.g. INV-001 has 150,000 above any typical benchmark)
        high_val_row = scored[scored['Vch No'] == 'INV-001']
        self.assertIn('High Value', high_val_row['_Risk_Flags'].values[0])

        # Suspicious narration flags (INV-004 has cash, INV-005 has suspense)
        cash_row = scored[scored['Vch No'] == 'INV-004']
        self.assertIn('Suspicious Narration', cash_row['_Risk_Flags'].values[0])

    def test_stratified_monthly_sampling(self):
        analyzer = AuditAnalyzer(self.df, 'Purchases')
        # Generate 10 samples
        tod, toc = analyzer.generate_samples(target_count=10, audit_type='large')
        
        # Verify sizes
        self.assertEqual(len(tod) + len(toc), 10)
        
        # Verify deduplication: zero vendor intersection between TOD and TOC
        tod_vendors = set(tod['_Norm_Vendor'].dropna().astype(str).str.strip().str.lower())
        toc_vendors = set(toc['_Norm_Vendor'].dropna().astype(str).str.strip().str.lower())
        overlap = tod_vendors.intersection(toc_vendors)
        # Verify that only blank/empty normalized vendors overlap (if any), otherwise 0
        overlap = {v for v in overlap if v not in ('', 'nan')}
        self.assertEqual(len(overlap), 0)

    def test_configuration_override(self):
        custom_config = AuditConfig(
            round_values=[25000, 50000],
            suspicious_keywords=['reversal', 'store']
        )
        analyzer = AuditAnalyzer(self.df, 'Purchases', config=custom_config)
        scored = analyzer.score_risks()
        
        # INV-002 has 'Store purchase' -> should match reversal/store keyword
        store_row = scored[scored['Vch No'] == 'INV-002']
        self.assertIn('Suspicious Narration', store_row['_Risk_Flags'].values[0])

if __name__ == '__main__':
    unittest.main()
