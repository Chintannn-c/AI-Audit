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

    print("\n--- Testing Value-Based Sampling Fixed (TOD+TOC, 30 samples, 70/30 split) ---")
    # 30 samples -> 21 TOD, 9 TOC
    tod_val, toc_val = analyzer.generate_samples(target_count=30, sampling_basis='value', audit_type='large', tod_pct=70)
    print(f"Value TOD Count: {len(tod_val)}, Value TOC Count: {len(toc_val)}")
    assert len(tod_val) == 21
    assert len(toc_val) == 9
    
    # 1. Check Row Uniqueness across TOD and TOC
    row_intersection_val = set(tod_val.index).intersection(set(toc_val.index))
    print(f"Value Row Intersection Size: {len(row_intersection_val)}")
    assert len(row_intersection_val) == 0
    
    # 2. Check Month Coverage
    all_selected_val = pd.concat([tod_val, toc_val])
    selected_months_val = set(pd.to_datetime(all_selected_val['Date'], dayfirst=True).dt.month.tolist())
    print(f"Value Selected Months: {sorted(list(selected_months_val))}")
    assert len(selected_months_val) == 12 # All 12 months should be covered
    
    # 3. Check No Duplicate Transactions selected
    selected_indices = list(tod_val.index) + list(toc_val.index)
    assert len(set(selected_indices)) == len(selected_indices), "Duplicate transactions found in sample indices!"
    print("Value Unique Selection: Verified (no duplicate indices)")

    # 4. Check Vendor Cap (Cap of 2 is strictly respected since 30 samples < 40 max unique capacity)
    from collections import Counter
    all_selected_vendors = all_selected_val['Vendor'].dropna().str.strip().str.lower().tolist()
    vendor_counts = Counter(all_selected_vendors)
    print(f"Selected Vendor Frequencies: {dict(vendor_counts.most_common(5))}")
    for vendor, count in vendor_counts.items():
        assert count <= 2, f"Vendor '{vendor}' appeared {count} times, which exceeds the cap of 2!"
    print("Value Vendor Cap (cap <= 2): Verified successfully")
    
    print("\n[SUCCESS] All Sampling Logic Tests Passed!")

if __name__ == "__main__":
    test_sampling_logic()
