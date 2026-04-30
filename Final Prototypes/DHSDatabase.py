"""
DHSDatabase.py — Allegheny County Veterans Services
Single-source database creator for veteran burial records.

Schema (6 fields + id):
    name, date_of_birth, date_of_death, war, branch_of_service, burial_location

Ingestion sources:
    - VeteransRecords.xlsx  (batch Excel import)
    - DHS PDF metadata      (single file or directory of scanned pdfs)

Requires: pip install pandas openpyxl pypdf
"""

import sqlite3
import pandas as pd
from pathlib import Path

try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("WARNING: pypdf not installed — PDF ingestion disabled. Run: pip install pypdf")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH   = Path(__file__).parent / "veterans.db"
XLSX_PATH = Path(__file__).parent.parent / "VeteransRecords.xlsx"

# ---------------------------------------------------------------------------
# War normalization
# ---------------------------------------------------------------------------

_WAR_MAP = {
    # Civil War
    "civil": "Civil", "civil war": "Civil",
    # WWI
    "ww1": "WW1", "wwi": "WW1", "world war i": "WW1", "world war 1": "WW1",
    "world war one": "WW1",
    # WWII
    "ww2": "WW2", "wwii": "WW2", "world war ii": "WW2", "world war 2": "WW2",
    "world war two": "WW2", "ww ii": "WW2", "world war 2": "WW2",
    # Korea
    "korea": "Korea", "korean": "Korea", "korean war": "Korea",
    "korean conflict": "Korea", "korea/vietnam": "Korea",
    # Vietnam
    "vietnam": "Vietnam", "vn": "Vietnam", "v.n.": "Vietnam",
    "vietnam war": "Vietnam", "vietnam era": "Vietnam",
    "veitnam": "Vietnam", "viet nam": "Vietnam",
    # GWOT / post-9/11
    "gwot": "GWOT", "global war on terror": "GWOT", "oif": "GWOT",
    "oef": "GWOT", "iraq": "GWOT", "afghanistan": "GWOT",
    "global war on terrorism": "GWOT",
    "desert storm": "GWOT", "gulf": "GWOT", "gulf war": "GWOT",
    "persian gulf": "GWOT", "persian golf": "GWOT", "panama": "GWOT",
    "lebanon": "GWOT",
    # None / peacetime / unknown
    "none": "None", "peacetime": "None", "peace": "None", "peace time": "None",
    "": "None", "served": "None", "nan": "None",
}

def _normalize_war(val) -> str:
    if val is None:
        return "None"
    s = str(val).strip()
    if not s:
        return "None"
    return _WAR_MAP.get(s.lower(), s.title())


# ---------------------------------------------------------------------------
# Connection & schema
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS veterans (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL,
            date_of_birth     TEXT,
            date_of_death     TEXT,
            war               TEXT,
            branch_of_service TEXT,
            burial_location   TEXT,
            source            TEXT    DEFAULT 'unknown'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vet_name ON veterans(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vet_war  ON veterans(war)")
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(val) -> str | None:
    """Strip whitespace; return None for blank/NaN values."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    s = str(val).strip()
    return s or None


def _format_date(val) -> str | None:
    """Convert pandas Timestamp or date string to MM/DD/YYYY."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    try:
        return pd.to_datetime(val).strftime("%m/%d/%Y")
    except Exception:
        return _clean(val)


def _build_burial_location(cemetery=None, section=None, range_=None,
                            lot=None, grave=None) -> str | None:
    parts = []
    if cemetery: parts.append(cemetery)
    if section:  parts.append(f"Sec {section}")
    if range_:   parts.append(f"Rng {range_}")
    if lot:      parts.append(f"Lot {lot}")
    if grave:    parts.append(f"Grave {grave}")
    return ", ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Excel ingestion
# ---------------------------------------------------------------------------

def ingest_xlsx(xlsx_path: Path, conn: sqlite3.Connection) -> tuple[int, int]:
    """
    Read VeteransRecords.xlsx and insert into veterans table.

    Excel columns mapped:
        B  First Name + C Last Name → name
        D  Date of Death            → date_of_death (formatted MM/DD/YYYY)
        F  Cemetery.Cemetery Name   → burial_location (combined with plot coords)
        M  Section                  → burial_location
        N  Range                    → burial_location
        O  Branch                   → branch_of_service
        Q  Grave Number             → burial_location
        R  Lot Number               → burial_location
        Z  War                      → war (normalized)

    date_of_birth is not in the Excel source; stored as NULL.
    Returns (inserted, skipped).
    """
    df = pd.read_excel(xlsx_path)
    df.columns = df.columns.str.strip()
    df = df.where(pd.notna(df), None)

    inserted = 0
    skipped  = 0

    for _, row in df.iterrows():
        first = _clean(row.get("First Name"))
        last  = _clean(row.get("Last Name"))
        name  = f"{first or ''} {last or ''}".strip()
        if not name:
            skipped += 1
            continue

        dod    = _format_date(row.get("Date of Death"))
        war    = _normalize_war(row.get("War"))
        branch = _clean(row.get("Branch"))

        cemetery = _clean(row.get("Cemetery.Cemetery Name"))
        section  = _clean(row.get("Section"))
        range_   = _clean(row.get("Range"))
        lot      = _clean(row.get("Lot Number"))
        grave    = _clean(row.get("Grave Number"))

        burial_location = _build_burial_location(cemetery, section, range_, lot, grave)

        conn.execute("""
            INSERT INTO veterans
                (name, date_of_birth, date_of_death, war, branch_of_service, burial_location, source)
            VALUES (?, NULL, ?, ?, ?, ?, 'xlsx')
        """, (name, dod, war, branch, burial_location))
        inserted += 1

    conn.commit()
    return inserted, skipped


# ---------------------------------------------------------------------------
# PDF metadata ingestion
# ---------------------------------------------------------------------------

def ingest_pdf(pdf_path: Path, conn: sqlite3.Connection) -> bool:
    """
    Reads DHS metadata fields from a single PDF and insert one record.

    DHS metadata fields used:
        /DHS_VeteranName    name
        /DHS_DateOfBirth    date_of_birth
        /DHS_DateOfDeath    date_of_death
        /DHS_War            war
        /DHS_ServiceBranch  branch_of_service
        /DHS_CemeteryName + /DHS_GraveLocation / burial_location

    Returns True if a record was inserted, False if skipped (no name found).
    """
    if not PDF_SUPPORT:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf")

    reader = PdfReader(str(pdf_path))
    meta   = reader.metadata or {}

    def get(key: str) -> str | None:
        return _clean(meta.get(f"/DHS_{key}"))

    name = get("VeteranName")
    if not name:
        return False

    cemetery  = get("CemeteryName")
    grave_loc = get("GraveLocation")
    burial_parts = [p for p in [cemetery, grave_loc] if p]
    burial_location = "; ".join(burial_parts) if burial_parts else None

    conn.execute("""
        INSERT INTO veterans
            (name, date_of_birth, date_of_death, war, branch_of_service, burial_location, source)
        VALUES (?, ?, ?, ?, ?, ?, 'pdf')
    """, (
        name,
        get("DateOfBirth"),
        get("DateOfDeath"),
        _normalize_war(get("War")),
        get("ServiceBranch"),
        burial_location,
    ))
    conn.commit()
    return True


def ingest_pdf_directory(dir_path: Path, conn: sqlite3.Connection) -> tuple[int, int]:
    """
    Batch-process all *.pdf files in dir_path.
    Returns (inserted, failed_or_skipped).
    """
    pdfs     = sorted(Path(dir_path).glob("*.pdf"))
    inserted = 0
    failed   = 0

    for pdf in pdfs:
        try:
            if ingest_pdf(pdf, conn):
                inserted += 1
            else:
                failed += 1
                print(f"  [SKIP] No name found: {pdf.name}")
        except Exception as exc:
            failed += 1
            print(f"  [ERR ] {pdf.name}: {exc}")

    return inserted, failed


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def print_sample(conn: sqlite3.Connection, limit: int = 20) -> None:
    rows = conn.execute("""
        SELECT name, date_of_birth, date_of_death, war, branch_of_service, burial_location
        FROM veterans
        LIMIT ?
    """, (limit,)).fetchall()

    print(f"\n{'Name':<30} {'DOB':<12} {'DOD':<12} {'War':<12} {'Branch':<16} Burial Location")
    print("-" * 110)
    for r in rows:
        print(f"{(r['name'] or ''):<30} {(r['date_of_birth'] or ''):<12} "
              f"{(r['date_of_death'] or ''):<12} {(r['war'] or ''):<12} "
              f"{(r['branch_of_service'] or ''):<16} {r['burial_location'] or ''}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Fresh build — drop and recreate
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Dropped existing: {DB_PATH.name}")

    conn = get_connection()
    init_db(conn)

    # ── XLSX ingestion ──────────────────────────────────────────────────────
    if XLSX_PATH.exists():
        print(f"Ingesting Excel: {XLSX_PATH.name} ...")
        ins, skp = ingest_xlsx(XLSX_PATH, conn)
        print(f"  Inserted : {ins}")
        print(f"  Skipped  : {skp} (blank name rows)")
    else:
        print(f"[WARN] Excel file not found: {XLSX_PATH}")

    # ── PDF ingestion (uncomment when output_cards/ directory is available) ─
    # pdf_dir = Path(__file__).parent.parent / "output_cards"
    # if pdf_dir.exists():
    #     print(f"\nIngesting PDFs from: {pdf_dir} ...")
    #     ins, fail = ingest_pdf_directory(pdf_dir, conn)
    #     print(f"  Inserted         : {ins}")
    #     print(f"  Failed / Skipped : {fail}")

    # ── Verification ────────────────────────────────────────────────────────
    total = conn.execute("SELECT COUNT(*) FROM veterans").fetchone()[0]
    wars  = conn.execute(
        "SELECT war, COUNT(*) AS n FROM veterans GROUP BY war ORDER BY n DESC"
    ).fetchall()

    print(f"\nTotal records: {total}")
    print("Records by war era:")
    for w in wars:
        print(f"  {(w['war'] or 'NULL'):<12}: {w['n']}")

    print_sample(conn, limit=20)
    conn.close()
