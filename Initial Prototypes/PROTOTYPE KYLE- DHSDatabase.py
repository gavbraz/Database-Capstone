"""
Veterans Data Ingestion Pipeline

Transforms raw Excel burial records into a normalized SQLite database with
relational tables for wars, cemeteries, and burial plots.
- Data cleaning and normalization
- Foreign key relationship resolution
- Performance caching
- Validation queries
- Logging and error tracking
"""


import sqlite3
import pandas as pd
from pathlib import Path
import logging
import time

# LOGGING SETUP
# We log errors and important events to a file so that issues
# during large batch imports can be reviewed after execution.
logging.basicConfig(
    filename="import.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# DATA CLEANING
def clean_string(val, title_case=False):
    """
    Standardizes string input from Excel/Pandas.
    - Removes leading/trailing whitespace
    - Handles NaN values safely
    - Optionally converts to title case for consistency
      (used for names, war labels, cemetery names)

    This ensures consistent formatting before inserting into SQLite,
    preventing duplicates caused by casing/spacing differences.
    """
    if pd.notna(val) and val is not None:
        val = str(val).strip()
        return val.title() if title_case else val
    return None


def safe_str(val):
    """
    Converts values to safe stripped strings for database insertion.
    - Prevents crashes from NaN/None values
    - Ensures plot-related fields are always strings or empty strings
    """
    return str(val).strip() if pd.notna(val) and val is not None else ""


# DATABASE LOOKUP / INSERT HELPERS
def get_or_create(cursor, table, name, cache):
    """
    Generic helper for lookup tables (wars, cemeteries).
    - Checks in-memory cache first (performance optimization)
    - If not found, inserts into DB (if not already present)
    - Retrieves and returns the row ID
    """
    if not name:
        return None

    # Fast path: avoid DB call if already cached
    if name in cache:
        return cache[name]

    try:
        cursor.execute(
            f"INSERT OR IGNORE INTO {table}(name) VALUES (?)",
            (name,)
        )
        cursor.execute(
            f"SELECT id FROM {table} WHERE name=?",
            (name,)
        )

        result = cursor.fetchone()

        if result:
            cache[name] = result[0]
            return result[0]

    except Exception as e:
        logging.error(f"Error inserting into {table}: {e}")

    return None


def get_or_create_plot(cursor, plot_key, cache):
    """
    Specialized helper for plots (composite key table).

    Unlike wars/cemeteries, plots are uniquely defined by:
    (section, range, lot, grave, cemetery_id)
    - Uses tuple-based caching
    - Inserts only if unique combination does not exist
    - Retrieves plot ID for foreign key reference
    """
    if plot_key in cache:
        return cache[plot_key]

    try:
        cursor.execute("""
        INSERT OR IGNORE INTO plots (section, range, lot, grave, cemetery_id)
        VALUES (?, ?, ?, ?, ?)
        """, plot_key)

        cursor.execute("""
        SELECT id FROM plots
        WHERE section=? AND range=? AND lot=? AND grave=? AND cemetery_id=?
        """, plot_key)

        result = cursor.fetchone()

        if result:
            cache[plot_key] = result[0]
            return result[0]

    except Exception as e:
        logging.error(f"Plot insert error: {e}")

    return None


# MAIN EXECUTION START
start_time = time.time()

# File paths for dataset and database
excel_path = r"C:\Users\kylej\Desktop\database project\VeteranRecords.xlsx"
db_path = r"C:\Users\kylej\Desktop\database project\veterans.db"

# Load Excel data into pandas DataFrame
df = pd.read_excel(excel_path)

# Normalize column names (removes hidden whitespace issues)
df.columns = df.columns.str.strip()

# Convert NaN values to None so SQLite can store them properly
df = df.where(pd.notna(df), None)

print("Rows:", len(df))
logging.info(f"Loaded {len(df)} rows from Excel")


# DATABASE CONNECTION SETUP
conn = sqlite3.connect(db_path)

# Cursor used for executing SQL commands
cursor = conn.cursor()

# Enforces foreign key constraints in SQLite
cursor.execute("PRAGMA foreign_keys = ON")

print("DB Path:", Path(db_path).resolve())


# DATABASE SCHEMA CREATION
# Creates tables only if they do not already exist.

cursor.executescript("""
CREATE TABLE IF NOT EXISTS cemeteries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS wars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS plots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT,
    range TEXT,
    lot TEXT,
    grave TEXT,
    cemetery_id INTEGER,
    UNIQUE(section, range, lot, grave, cemetery_id),
    FOREIGN KEY (cemetery_id) REFERENCES cemeteries(id)
);

CREATE TABLE IF NOT EXISTS burials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    war_id INTEGER,
    plot_id INTEGER,
    FOREIGN KEY (war_id) REFERENCES wars(id),
    FOREIGN KEY (plot_id) REFERENCES plots(id)
);

-- Indexes improve lookup speed for common queries
CREATE INDEX IF NOT EXISTS idx_burials_name ON burials(name);
CREATE INDEX IF NOT EXISTS idx_wars_name ON wars(name);
CREATE INDEX IF NOT EXISTS idx_cemeteries_name ON cemeteries(name);
""")


# CACHING STRUCTURES (PERFORMANCE OPTIMIZATION)
war_cache = {}
cemetery_cache = {}
plot_cache = {}

invalid_rows = 0


# DATA INGESTION LOOP
# Each row in the Excel file represents one veteran record.
# This loop transforms raw data into structured relational entries.
for i, row in df.iterrows():

    try:
        # NAME PROCESSING
        # Combine first + last name into a single standardized field
        first = clean_string(row.get("First Name"), True)
        last = clean_string(row.get("Last Name"), True)

        name = f"{first or ''} {last or ''}".strip()

        # Skip invalid records with no usable name
        if not name:
            invalid_rows += 1
            logging.warning(f"Row {i} skipped (no name)")
            continue

        # EXTRACT DATA FROM CURRENT RECORD
        war = clean_string(row.get("War"), True)
        cemetery = clean_string(row.get("Cemetery.Cemetery Name"), True)

        section = safe_str(row.get("Section"))
        range_ = safe_str(row.get("Range"))
        lot = safe_str(row.get("Lot Number"))
        grave = safe_str(row.get("Grave Number"))


        # MAP VALUES TO DB IDs
        # Convert human-readable values into database IDs
        war_id = get_or_create(cursor, "wars", war, war_cache)
        cemetery_id = get_or_create(cursor, "cemeteries", cemetery, cemetery_cache)


        # PLOT CREATION
        plot_key = (section, range_, lot, grave, cemetery_id)
        plot_id = get_or_create_plot(cursor, plot_key, plot_cache)


        # FINAL INSERT (BURIAL TABLE)
        cursor.execute("""
        INSERT INTO burials (name, war_id, plot_id)
        VALUES (?, ?, ?)
        """, (name, war_id, plot_id))

    except Exception as e:
        logging.error(f"Row {i} failed: {e}")
        invalid_rows += 1


# FINAL COMMIT
conn.commit()

print("Import complete.")
print("Invalid rows:", invalid_rows)
logging.info(f"Invalid rows: {invalid_rows}")


# VALIDATION QUERIES
def run_queries(cursor):
    """
    Runs verification queries to ensure data integrity.
    - Sample joined output across all tables
    - Aggregation of burials per war
    """

    print("\nSample Data:")
    cursor.execute("""
    SELECT b.name, w.name, c.name
    FROM burials b
    LEFT JOIN wars w ON b.war_id = w.id
    LEFT JOIN plots p ON b.plot_id = p.id
    LEFT JOIN cemeteries c ON p.cemetery_id = c.id
    LIMIT 10
    """)

    for row in cursor.fetchall():
        print(row)

    print("\nBurials per War:")
    cursor.execute("""
    SELECT w.name, COUNT(*)
    FROM burials b
    JOIN wars w ON b.war_id = w.id
    GROUP BY w.name
    """)

    for row in cursor.fetchall():
        print(row)

# Run validation checks
run_queries(cursor)


# CLEANUP
conn.close()

end_time = time.time()

print(f"Execution time: {end_time - start_time:.2f} seconds")
