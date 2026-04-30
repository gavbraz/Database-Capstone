================================================================================
  ALLEGHENY COUNTY VETERANS SERVICES — Team 2's DHS DATABASE and Web GUI PROJECT
  CS Capstone 2026 | Duquesne University
================================================================================

PROJECT OVERVIEW
----------------
This project digitizes and provides a searchable interface for Allegheny County
veteran burial and service records.This is the second part of a two teamed approach 
with the AI scanning team. It itself consists of two parts:

  1. DHSDatabase.py  — ingests records from Excel and/or DHS-formatted PDFs
                       into a local SQLite database (veterans.db)
  2. VeteranRecordsServer.js — a Node.js/Express web server that shares the
                               database through a browser-based search interface


--------------------------------------------------------------------------------
  PART 1: RUNNING DHSDatabase.py (DATABASE INGESTION)
--------------------------------------------------------------------------------

REQUIREMENTS
  - Python 3.10 or later
  - The following Python packages (install once with pip):

      pip install pandas openpyxl pypdf

  - Currently pointing to VeteransRecords.xlsx must be present in the parent directory
    can be adjusted in DHSDatabase.py to accommodate any kissflow excel sheet very well

STEPS

  1. Open a terminal and navigate to the Database-Capstone-main folder:

       cd "Database-Capstone-main"

  2. Run the ingestion script:

       python DHSDatabase.py

     The script will:
       - Drop and recreate veterans.db from scratch (safe to re-run with new records)
       - Read all records from .xlsx
       - Normalize war/era values to standard labels
         (Civil, WW1, WW2, Korea, Vietnam, GWOT, None)
       - Format dates as MM/DD/YYYY
       - Print a summary showing total records and breakdown by war era
       - Print a sample of the first 20 records for verification

  3. Confirm output ends with a line like:

       Total records: 487

DATABASE SCHEMA
  The resulting veterans.db contains one table: veterans

    Column            Source
    ----------------  ----------------------------------------
    id                Auto-generated primary key and effective sequencer
    name              First Name + Last Name (Excel col B + C)
    date_of_birth     Not in Excel; populated from PDF metadata
    date_of_death     Date of Death (Excel col D)
    war               War (Excel col Z), normalized
    branch_of_service Branch (Excel col O)
    burial_location   Cemetery + Section/Range/Lot/Grave (combined)


PDF INGESTION (for scans through team 1's OCR)
  The script also supports ingesting records from PDF metadata prepended by team 1's scans.

  To enable this, uncomment the pdf_dir block near the bottom of DHSDatabase.py
  and set the path to the folder containing the PDF files (e.g., network drive).
  
  Specific fields agreed upon in this custom format.
  PDF metadata fields used: /DHS_VeteranName, /DHS_DateOfBirth, /DHS_DateOfDeath,
  /DHS_War, /DHS_ServiceBranch, /DHS_CemeteryName, /DHS_GraveLocation.


--------------------------------------------------------------------------------
  PART 2: RUNNING THE WEB SERVER
--------------------------------------------------------------------------------

REQUIREMENTS
  - Node.js 18 or later
  - npm packages (install once from inside Database-Capstone-main/):

      npm install

  - veterans.db must exist (run DHSDatabase.py first if uncreated)

STEPS

  1. Navigate to the Database-Capstone-main folder:

       cd "Database-Capstone-main"

  2. Start the server:

       node VeteranRecordsServer.js

  3. Open a browser and go to:

       http://localhost:3000

  The server exposes two JSON API endpoints used by the front end:

    GET /api/search?q=<name>&war=<era>   Search by name, optionally filter by era
    GET /api/veteran/:id                 Fetch a single record by database ID

  The front end is a single HTML file (public/index.html), incorporation with DHS to be done in react.js
  To stop the server, press Ctrl+C in the terminal.


--------------------------------------------------------------------------------
  FILE STRUCTURE (Database-Capstone-main/)
--------------------------------------------------------------------------------

  VeteranRecordsServer.js   Node.js/Express web server
  db.js                     SQLite connection module (used by the server)
  DHSDatabase.py            Python ingestion script
  veterans.db               SQLite database (generated — not committed to git)
  public/
    index.html              Single-page search interface (HTML + JS, no framework)
    style.css               Allegheny County shared stylesheet
  .gitignore                Excludes node_modules/, veterans.db, and WAL files
  package.json              Node.js dependencys


--------------------------------------------------------------------------------
  INITIAL PROTOTYPES (Initial Prototypes/)
--------------------------------------------------------------------------------

Three prototype files were developed before the final implementation:

  PROTOTYPE KYLE- DHSDatabase.py


  PROTOTYPE VINCENT- DHSDatabase.py


  Website Prototype.html
    A standalone HTML mockup of the public-facing search interface. Contains
    hard-coded mock veteran records and client-side JavaScript to simulate
    search and filter functionality without any backend. First mimicked the
    Allegheny County visual design (blue/gold header, war-era filter chips,
    result cards) that was carried forward into the final public/index.html
    and public/style.css.

================================================================================
