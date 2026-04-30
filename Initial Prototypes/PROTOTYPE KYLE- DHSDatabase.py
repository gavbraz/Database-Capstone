import sqlite3
import pandas as pd
from pathlib import Path

# Load Excel
# ----------
excel_path = r"C:\Users\kylej\Desktop\database project\VeteranRecords.xlsx"
df = pd.read_excel(excel_path)

print("Rows:", len(df))
print("Columns:", df.columns)
print(df.head())

df.columns = df.columns.str.strip() #Remove spaces
df = df.where(pd.notna(df), None)

# Connect to DB (absolute path)
# ----------------------------
db_path = r"C:\Users\kylej\Desktop\database project\veterans.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON")
print("DB Path:", Path(db_path).resolve())

# Create tables
# -------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS cemeteries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS wars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS plots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT,
    range TEXT,
    lot TEXT,
    grave TEXT,
    cemetery_id INTEGER,
    UNIQUE(section, range, lot, grave, cemetery_id),
    FOREIGN KEY (cemetery_id) REFERENCES cemeteries(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS burials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    war_id INTEGER,
    plot_id INTEGER,
    FOREIGN KEY (war_id) REFERENCES wars(id),
    FOREIGN KEY (plot_id) REFERENCES plots(id)
)
""")

# Create indexes
# --------------
cursor.execute("CREATE INDEX IF NOT EXISTS idx_burials_name ON burials(name)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_wars_name ON wars(name)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_cemeteries_name ON cemeteries(name)")

# Helper caches
# -------------
war_cache = {}
cemetery_cache = {}
plot_cache = {}

# Import loop
# -----------
for _, row in df.iterrows():

    #Combine first + last name
    first = row.get("First Name")
    last = row.get("Last Name")
    name = f"{first or ''} {last or ''}".strip()
    if not name:
        continue

    #Map other columns
    war = row.get("War")
    cemetery = row.get("Cemetery.Cemetery Name")
    section = row.get("Section")
    range_ = row.get("Range")
    lot = row.get("Lot Number")
    grave = row.get("Grave Number")

    #Convert to string safely
    war = str(war).strip() if war else None
    cemetery = str(cemetery).strip() if cemetery else None
    section_s = str(section).strip() if section else ""
    range_s = str(range_).strip() if range_ else ""
    lot_s = str(lot).strip() if lot else ""
    grave_s = str(grave).strip() if grave else ""

    # WAR TABLE
    # ---------
    war_id = None
    if war:
        if war not in war_cache:
            cursor.execute("INSERT OR IGNORE INTO wars(name) VALUES (?)", (war,))
            cursor.execute("SELECT id FROM wars WHERE name=?", (war,))
            result = cursor.fetchone()
            if result:
                war_cache[war] = result[0]
        war_id = war_cache.get(war)

    # CEMETERY TABLE
    # --------------
    cemetery_id = None
    if cemetery:
        if cemetery not in cemetery_cache:
            cursor.execute("INSERT OR IGNORE INTO cemeteries(name) VALUES (?)", (cemetery,))
            cursor.execute("SELECT id FROM cemeteries WHERE name=?", (cemetery,))
            result = cursor.fetchone()
            if result:
                cemetery_cache[cemetery] = result[0]
        cemetery_id = cemetery_cache.get(cemetery)

    # PLOT TABLE
    # ----------
    plot_id = None
    plot_key = (section_s, range_s, lot_s, grave_s, cemetery_id)
    if plot_key not in plot_cache:
        cursor.execute("""
        INSERT OR IGNORE INTO plots (section, range, lot, grave, cemetery_id)
        VALUES (?, ?, ?, ?, ?)
        """, plot_key)

        cursor.execute("""
        SELECT id FROM plots
        WHERE section = ? AND range = ? AND lot = ? AND grave = ? AND cemetery_id = ?
        """, plot_key)

        result = cursor.fetchone()
        if result:
            plot_cache[plot_key] = result[0]

    plot_id = plot_cache.get(plot_key)

    # BURIAL TABLE
    # ------------
    cursor.execute("INSERT INTO burials (name, war_id, plot_id) VALUES (?, ?, ?)",
                   (name, war_id, plot_id))

conn.commit() #Save records
print("Records Imported.")

# Test query
# ----------
cursor.execute("""
SELECT b.name, w.name, c.name, p.section, p.range, p.lot, p.grave
FROM burials b
LEFT JOIN wars w ON b.war_id = w.id
LEFT JOIN plots p ON b.plot_id = p.id
LEFT JOIN cemeteries c ON p.cemetery_id = c.id
LIMIT 20
""")
rows = cursor.fetchall()
for row in rows:
    print(row)

#Show tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cursor.fetchall())

conn.close()
