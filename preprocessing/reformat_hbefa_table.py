import sys

import pandas as pd
from tqdm import tqdm

# ==========================================
# 1. CONFIGURATION
# ==========================================
input_csv = r"D:\Michael_Thesis\data\hbefa\EFA_HOT_Vehcat_michael_thesis_weighted_v4_2_bus.csv"
output_csv = r"D:\Michael_Thesis\data\hbefa\EFA_HOT_Vehcat_bus_reformat.csv"

# ==========================================
# 2. LOAD DATA
# ==========================================
print(f"Loading raw HBEFA data from {input_csv}...", flush=True)
# Read the raw CSV exported from HBEFA software (comma-separated)
df = pd.read_csv(input_csv, sep=',')

# ==========================================
# 3. TRANSFORMATION RULES
# ==========================================
print("Applying transformation rules...", flush=True)

# Rule A: Insert Gradient into TrafficSit
# Target: 'RUR/MW/80/Freeflow' + '0%' -> 'RUR/MW/80/0%/Freeflow'
def inject_gradient(row):
    ts = str(row['TrafficSit'])
    grad = str(row['Gradient'])

    if pd.isna(row['TrafficSit']):
        return ts

    parts = ts.split('/')
    # Insert gradient strictly before the last element (the traffic state)
    if len(parts) > 1:
        parts.insert(-1, grad)
        return '/'.join(parts)
    return ts

tqdm.pandas(desc="Modifying TrafficSit", file=sys.stdout)
df['TrafficSit'] = df.progress_apply(inject_gradient, axis=1)

# # Rule B: Fill empty AmbientCondPattern with 'ØGermany' to satisfy MATSim parser
# if 'AmbientCondPattern' in df.columns:
#     df['AmbientCondPattern'] = df['AmbientCondPattern'].fillna('ØGermany')
#     df.loc[df['AmbientCondPattern'] == '', 'AmbientCondPattern'] = 'ØGermany'

# ==========================================
# 4. EXPORT DATA
# ==========================================
print(f"Exporting formatted data to {output_csv}...", flush=True)
# MATSim HBEFA parser requires semicolon (;) separator
df.to_csv(output_csv, sep=';', index=False, encoding='utf-8')

print("Pipeline execution completed successfully.", flush=True)