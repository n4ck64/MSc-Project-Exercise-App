"""
Imports the CoFID 2021 nutrition dataset (McCance & Widdowson's Composition of
Foods) from the source Excel file into the 'foods' table.

Unlike the exercise CSVs, the CoFID spreadsheet needs two bits of special
handling:
  * the '1.3 Proximates' sheet has a 3-row header, so data starts on row 4
    (skiprows=3), and columns are selected by position rather than by name;
  * cells use sentinel values that are not numbers -- 'Tr' (trace) is treated
    as 0, and 'N' (present but unmeasured) or blanks become NULL.
"""

import numpy as np
import pandas as pd
import psycopg2

PATH = "/Users/nikolaytinev/Downloads/McCance_Widdowsons_Composition_of_Foods_Integrated_Dataset_2021..xlsx"

# Column positions in the '1.3 Proximates' sheet (0-indexed).
POS = {
    "food_code": 0, "food_name": 1, "description": 2, "food_group": 3,
    "kcal": 12, "protein_g": 9, "fat_g": 10, "carb_g": 11,
    "total_sugars_g": 16, "fibre_nsp_g": 24, "fibre_aoac_g": 25,
}
NUMERIC = ["kcal", "protein_g", "fat_g", "carb_g",
           "total_sugars_g", "fibre_nsp_g", "fibre_aoac_g"]


def to_num(series):
    """Resolve CoFID sentinels then coerce to numbers: Tr -> 0, N/blank -> NaN."""
    return pd.to_numeric(series.replace({"Tr": 0, "N": np.nan}), errors="coerce")


# Read the proximates sheet (3-row header -> skiprows=3).
raw = pd.read_excel(PATH, sheet_name="1.3 Proximates", skiprows=3, header=None)

out = pd.DataFrame({
    "food_code": raw[POS["food_code"]].astype(str).str.strip(),
    "food_name": raw[POS["food_name"]].astype(str).str.strip(),
    "description": raw[POS["description"]].astype(str).str.strip(),
    "food_group": raw[POS["food_group"]].astype(str).str.strip(),
})
for col in NUMERIC:
    out[col] = to_num(raw[POS[col]])

# Drop any rows without a food code.
out = out[out["food_code"].str.len() > 0]


def nan_to_none(v):
    # NaN must become SQL NULL; a 'real' column would otherwise store IEEE NaN.
    # (Converting per-column via the DataFrame re-coerces None back to NaN, so
    # this has to happen at tuple-build time.)
    return None if (isinstance(v, float) and pd.isna(v)) else v


conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()

# Reset the table so re-running is idempotent. The surrogate `id` PK means
# CoFID's duplicate food_code (13-669) no longer drops a row on import.
cur.execute("TRUNCATE foods RESTART IDENTITY")

records = [tuple(nan_to_none(v) for v in row)
           for row in out.itertuples(index=False, name=None)]
cur.executemany(
    """
    INSERT INTO foods (food_code, food_name, description, food_group,
                       kcal, protein_g, fat_g, carb_g,
                       total_sugars_g, fibre_nsp_g, fibre_aoac_g)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
    records,
)

conn.commit()
print(f"Foods imported: {cur.rowcount} rows affected ({len(records)} read).")
cur.close()
conn.close()
print("Done.")
