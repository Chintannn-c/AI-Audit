import pandas as pd
import datetime

data = []
vendors = ["Apple", "Microsoft", "Google", "Amazon", "Meta", "Tesla", "Netflix", "Adobe", "Intel", "Nvidia"]
for i in range(1, 101):
    month = (i % 12) + 1
    day = (i % 28) + 1
    date = datetime.date(2023, month, day).strftime("%d/%m/%Y")
    vendor = vendors[i % len(vendors)]
    amount = i * 150.0
    data.append({
        "Date": date,
        "Vendor": vendor,
        "Amount": amount,
        "Description": f"Txn {i}"
    })
df = pd.DataFrame(data)
df.to_excel("Sales_Ledger.xlsx", index=False)
print("Sales_Ledger.xlsx created successfully!")
