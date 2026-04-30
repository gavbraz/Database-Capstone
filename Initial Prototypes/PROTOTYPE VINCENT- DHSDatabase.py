import sqlite3
import pandas as pd

#install pandas and openpyxl to access xlsx sheets
df = pd.read_excel("VeteransRecords.xlsx")

df.columns = df.columns.str.lower().str.strip()

conn = sqlite3.connect("veterans.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS burials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    war TEXT,
    section TEXT,
    range TEXT,
    lot TEXT,
    grave TEXT,
    cemetery TEXT
)
""")

for _, row in df.iterrows():
    name = row.get("name")

    if pd.isna(name) or str(name).strip() == "":
        continue

    cursor.execute("""
        INSERT INTO burials (name, war, section, range, lot, grave, cemetery)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        row.get("name"),
        row.get("war"),
        row.get("section"),
        row.get("range"),
        row.get("lot"),
        row.get("grave"),
        row.get("cemetery")
    ))

conn.commit()
conn.close()

print("Records Imported.")

conn = sqlite3.connect("veterans.db")  # your DB filename
cur = conn.cursor()

cur.execute("SELECT * FROM burials LIMIT 20;")
rows = cur.fetchall()

for row in rows:
    print(row)

cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cur.fetchall())

conn.close()