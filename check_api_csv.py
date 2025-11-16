#!/usr/bin/env python3
import sys
import os
import glob
import pandas as pd

# Check for API CSV in a results directory
results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"

print(f"\n=== Checking for API CSV in: {results_dir} ===\n")

# Find all CSV files
all_csvs = glob.glob(os.path.join(results_dir, "*.csv"))
print(f"All CSV files found ({len(all_csvs)}):")
for csv in sorted(all_csvs):
    basename = os.path.basename(csv)
    size = os.path.getsize(csv)
    print(f"  - {basename} ({size} bytes)")

# Find API requests CSV
api_csvs = [f for f in all_csvs if "api_requests" in os.path.basename(f) and not os.path.basename(f).startswith("old_")]
print(f"\n=== API Requests CSV files: {len(api_csvs)} ===")

if api_csvs:
    for api_csv in api_csvs:
        print(f"\n✓ Found: {os.path.basename(api_csv)}")
        try:
            df = pd.read_csv(api_csv)
            print(f"  Rows: {len(df)}")
            print(f"  Columns: {list(df.columns)}")
            if not df.empty:
                print(f"  First row sample:")
                print(f"    {df.iloc[0].to_dict()}")
                if 'is_error' in df.columns:
                    errors = len(df[df['is_error'] == True])
                    print(f"  Errors: {errors} / {len(df)} requests")
        except Exception as e:
            print(f"  ✗ Error reading CSV: {e}")
else:
    print("✗ No api_requests CSV files found")
    print("\nThis means the original test run did not include API monitoring,")
    print("or the CSV was archived/deleted.")
