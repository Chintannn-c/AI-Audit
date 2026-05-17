import pandas as pd
import numpy as np
from analyzer import AuditAnalyzer
import datetime

def test_sampling_logic():
    # 1. Create Mock Data (100 txns, 12 months, multiple vendors)
    data = []
    vendors = ["Apple", "Microsoft", "Google", "Amazon", "Meta", "Tesla", "Netflix", "Adobe", "Intel", "Nvidia",
               "Oracle", "Salesforce", "Cisco", "IBM", "SAP", "Toyota", "Samsung", "Walmart", "Disney", "Nike"]
    for i in range(1, 101):
        month = (i % 12) + 1
        day = (i % 28) + 1
        date = datetime.date(2023, month, day).strftime("%d/%m/%Y")
        vendor = vendors[i % len(vendors)]
        amount = i * 100 # Incremental amounts to test high-value logic
        data.append({
            "Date": date,
            "Vendor": vendor,
            "Amount": amount,
            "Description": f"Txn {i}"
        })
    
    df = pd.DataFrame(data)
    
    # 2. Initialize Analyzer
    analyzer = AuditAnalyzer(df, "Sales")
    
    print("\n--- Testing Small Audit (TOD Only, 10 samples) ---")
    tod, toc = analyzer.generate_samples(target_count=10, audit_type='small')
    print(f"TOD Count: {len(tod)}, TOC Count: {len(toc)}")
    assert len(tod) == 10
    assert len(toc) == 0
    # Check if TOD has highest values (mostly)
    # Note: stage 1 picks 1 per month first. Since we have 12 months but only 10 samples, it should pick from 10 distinct months.

    print("\n--- Testing Large Audit (TOD+TOC, 20 samples, 70/30 split) ---")
    # 20 samples -> 14 TOD, 6 TOC
    tod, toc = analyzer.generate_samples(target_count=20, audit_type='large', tod_pct=70)
    print(f"TOD Count: {len(tod)}, TOC Count: {len(toc)}")
    assert len(tod) == 14
    assert len(toc) == 6
    
    # Check Row Uniqueness across TOD and TOC (mutually exclusive transaction rows)
    row_intersection = set(tod.index).intersection(set(toc.index))
    print(f"Row Intersection Size: {len(row_intersection)}")
    assert len(row_intersection) == 0
    
    # Check Month Coverage (Parse from Date column since _Month is dropped)
    all_selected = pd.concat([tod, toc])
    selected_months = set(pd.to_datetime(all_selected['Date'], dayfirst=True).dt.month.tolist())
    print(f"Selected Months: {sorted(list(selected_months))}")
    assert len(selected_months) == 12 # All 12 months should be covered
    
    print("\n[SUCCESS] All Sampling Logic Tests Passed!")

if __name__ == "__main__":
    test_sampling_logic()
