# Future Translation to Production Environment

**Allegheny County Veterans Services CS Capstone 2026, Duquesne University**

This document outlines the steps, decisions, and improvements needed to move the two-team digitization system from its current prototype state into a production environment hosted within the DHS network.

Clean Markdown file formatted from .txt notes using Claude AI. Manually reviewed and edited by Gavin.

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Team One Section Summary](#2-team-one-section-summary)
3. [Team Two Section Summary](#3-team-two-section-summary)
4. [UI Implementation](#4-ui-implementation)
5. [Digital Record Keeping](#5-digital-record-keeping)
6. [Note on Records Saving](#6-note-on-records-saving)
7. [Database Code Improvements](#7-database-code-improvements)
8. [Quality Assurance Testing Metrics](#8-quality-assurance-testing-metrics)
9. [Data Security and Compliance](#9-data-security-and-compliance)
10. [Expanded Form Type Support](#10-expanded-form-type-support)

---

## 1. Pipeline Overview

The Allegheny County Veterans Services digitization effort is structured as a two-team pipeline:

- **Team One (VetScan)** is responsible for physically scanning veteran burial index cards, running OCR extraction, and producing structured per-card PDFs with embedded DHS-standard metadata.
- **Team Two (Database & Web GUI)** ingests those PDFs and the existing Kissflow Excel record set into a searchable SQLite database, and serves results through a browser-based web interface and server.

The handoff point between teams is the `output_cards/` directory produced by VetScan. Each PDF in that directory carries DHS-standard metadata fields that `DHSDatabase.py` reads directly on ingestion. The end goal is a production system hosted within the DHS network that allows Veterans Services staff to search all burial and service records through a unified interface aligned with the Allegheny County visual identity.

---

## 2. Team One Section Summary

The VetScan pipeline handles the physical-to-digital conversion of veteran burial index cards. Full technical documentation is in `DOCUMENTATION Team One Pipeline.md`.

**Scanning and batch preparation:**

- Gather and organize physical cards using dividers or index cards to separate scanning batches.
- Feed each batch through the scanner. Confirm the scan has been uploaded as a unified PDF to the network drive before running the pipeline.
- The pipeline accepts a single input PDF of interleaved card fronts and backs, with optional separator pages from the scanning stage.

**OCR and extraction:**

- VetScan runs on an Intel Core Ultra workstation equipped with an Intel AI Boost NPU and Intel Arc GPU. CPU-only execution is deliberately blocked — early testing produced runtimes of approximately 8 hours, versus the current roughly 42 minutes on hardware-accelerated inference.
- EasyOCR handles printed-text detection on each page. TrOCR (Microsoft's transformer-based handwriting model) is invoked for low-confidence spans to improve cursive recognition accuracy.
- The pipeline extracts veteran name, dates of birth and death, service branch, rank, cemetery name and location, and grave/section information from each card front (Form MAGO-41 / Form 14).

**Outputs:**

- One named PDF per card in `output_cards/`, carrying DHS-standard metadata fields.
- An `audit.csv` summarizing every source page with classification, extracted fields, and review flags.
- An `output_cards/ocr_failed/` directory holding pages that produced no OCR text and need manual rescan.

---

## 3. Team Two Section Summary

The database and web GUI pipeline handles ingestion of records and makes them searchable. Full setup instructions are in `README.txt`.

**Database ingestion (DHSDatabase.py):**

- Reads existing records from the Kissflow-exported Excel file (`VeteransRecords.xlsx`), mapping columns for veteran name, date of death, war era, service branch, and burial location into a normalized SQLite schema.
- Also supports direct ingestion from Team One's output PDFs via DHS-standard PDF metadata fields: `/DHS_VeteranName`, `/DHS_DateOfBirth`, `/DHS_DateOfDeath`, `/DHS_War`, `/DHS_ServiceBranch`, `/DHS_CemeteryName`, `/DHS_GraveLocation`.
- War and era values are normalized to a standard label set: Civil, WW1, WW2, Korea, Vietnam, GWOT, None.
- The script is designed to be re-run safely — it drops and recreates the database from scratch on each execution, making it suitable for use whenever a new batch of PDFs is ready to ingest.

**Web server (VeteranRecordsServer.js):**

- Node.js / Express server exposing two JSON API endpoints:
  - `GET /api/search?q=<name>&war=<era>` — name search with optional war-era filter, returning up to 100 results ordered by name.
  - `GET /api/veteran/:id` — single-record detail by database ID.
- The frontend is a single-page HTML/CSS/JS application styled to approximate the Allegheny County visual identity (blue/gold header, war-era filter chips, result cards).
- Currently runs locally on `http://localhost:3000`. Production deployment requires hosting within the DHS network environment with appropriate access controls.

---

## 4. UI Implementation

The current frontend is a standalone HTML/JS/CSS file suitable for the prototype. The following changes are required before production deployment:

- **DHS stylesheet alignment:** The current `style.css` approximates the Allegheny County look. Full synchronization with the official DHS stylesheet will likely require replacing the custom CSS entirely. This should be coordinated with DHS IT to obtain the current shared stylesheet.
- **React migration:** The broader DHS web application is planned in React.js. The existing API endpoints (`/api/search`, `/api/veteran/:id`) are compatible with a React frontend without modification.
- **Landing page:** The specific landing page destination for the veteran search tool within the DHS portal needs to be determined in coordination with DHS IT.
- **Kissflow coexistence:** If Kissflow continues to be used for incoming record intake in parallel with the new database, the UI must clearly delineate between Kissflow-managed records and historical database records to avoid confusion for clients.
- **Intended document workflow:** Scan using Team One's VetScan tool → save PDF in the appropriate network drive directory → ingest into the database via `DHSDatabase.py` → archive or discard physical record per the records-saving policy below.

---

## 5. Digital Record Keeping

All PDFs produced by VetScan are currently written to a network drive. This is not a permanent solution given the volume of records involved.

- **Permanent storage home:** A storage destination with appropriate redundancy needs to be selected before the scanning project is complete. The database assigns each record an auto-incremented ID that functions as a sequencer — this ID should be preserved as the stable reference linking a database record to its PDF file.
- **Cloud vs. on-premise:** Both options carry tradeoffs. Cloud storage (e.g., Azure Government, AWS GovCloud) offers scalability and built-in redundancy but requires approval under the DHS data-handling agreement. On-premise network-attached storage is consistent with the current data-handling posture but requires manual redundancy planning (RAID, off-site backup). A decision needs to be made in coordination with DHS IT before the full corpus is scanned.
- **Post-ingestion movement:** Once a PDF has been ingested into the database and the record verified, it can be moved from the working network drive to the permanent archive location. This movement should be logged.
- **Recommended structure:** Establish a two-tier directory layout — an active working directory for newly scanned PDFs awaiting ingestion and verification, and a permanent archive directory for verified records. This separates in-progress work from settled records and simplifies backup scope.

---

## 6. Note on Records Saving

- The majority of physical index cards have been evaluated and determined to be shreddable once digitized. Shredding must comply with DHS protocols for sensitive personal information — standard office shredding is not sufficient; cross-cut or micro-cut shredding is required.
- Cards flagged by VetScan as belonging to veterans with exceptional medals are set aside and not shredded. These are designated for a special memorial project coordinated separately from the digitization pipeline.
- Before any physical card is discarded, the corresponding PDF in the network drive must be confirmed to display correctly and be accessible. The `audit.csv` produced by each VetScan run provides a reliable per-card output filename that can be used for verification.
- A formal sign-off checklist for each scanning batch is recommended before shredding authorization is granted.

---

## 7. Database Code Improvements

The current prototype database and server are functional for demonstration but require the following changes before production use:

- **Additional searchable fields:** Search is currently limited to veteran name and war era. Adding search by branch of service, date of death range, burial location (cemetery name), and service number would significantly improve utility for staff.
- **Admin view:** An authenticated admin interface is needed for staff to view unredacted records, correct ingestion errors, and flag records for manual review. This must be separate from the public-facing search and inaccessible without valid credentials.
- **Search result display:** The current results screen has cosmetic issues that need debugging before production deployment.
- **Input validation and rate limiting:** The server currently uses parameterized SQL queries (protected from injection) and the frontend uses an `esc()` function for XSS protection. Both should be reviewed and validated in the production environment. Server-side input length limits and rate limiting should also be added to harden the API.
- **Database migration from SQLite:** SQLite is appropriate for the prototype and low-concurrency use. A production environment with multiple concurrent staff users may require migration to PostgreSQL or another server-grade database. The schema is simple (six data fields plus an auto-increment ID) and migration would be straightforward.
- **API authentication:** The current API endpoints have no authentication. In production, access should be restricted to the DHS internal network at minimum, and optionally protected by token-based authentication tied to the DHS identity provider.

---

## 8. Quality Assurance Testing Metrics

Before production deployment, the following quality assurance checkpoints should be established and tracked per scanning batch:

- **OCR accuracy rate:** The percentage of extracted field values that match a ground-truth set of manually verified records. A target of at least 95% accuracy on veteran name extraction is recommended, given its role as the primary search key.
- **Name review rate:** VetScan's `audit.csv` flags records where the extracted name did not match the common-name database within Levenshtein distance 2 (`name_needs_review = YES`). This rate should be tracked per batch, a rate above 10% suggests re-scanning at higher DPI is warranted.
- **OCR failure rate:** The percentage of pages landing in `output_cards/ocr_failed/`. This should be near zero for well-scanned batches. Consistent failures indicate a scanner calibration issue or physical card degradation that needs to be addressed before continuing.
- **Database ingestion validation:** After each `DHSDatabase.py` run, the total record count and per-war-era breakdown printed by the script should be compared against the source Excel or PDF count to confirm no records were silently dropped.
- **Search latency:** The web server should return search results in under 500ms for queries against the full record set. The current SQLite indexes on `name` and `war` support this for the existing approximately 487 records. Performance should be re-validated after the full scanning corpus is ingested.
- **End-to-end regression test set:** A representative set of test PDFs — covering Civil War through GWOT eras, faded cards, cursive-heavy cards, and cards flagged for exceptional medals — should be maintained and run against the pipeline after any code change to catch regressions before they affect production batches.

---

## 9. Data Security and Compliance

The DHS data-handling agreement places hard requirements on how veteran record data is processed and stored. Any production change must be evaluated against these constraints before it ships.

- **Local processing only:** No card image, extracted text, or metadata may leave the processing workstation during a VetScan run. The pipeline enforces this in code — all inference runs locally and no network calls are made at runtime. This must be preserved in any future change, including crash reporters, diagnostic logging services, or auto-updaters. Any change that introduces a network-bound component requires sign-off from the DHS contact.
- **Network access scope:** The web server must be accessible only within the DHS internal network and must not be exposed to the public internet without additional DHS IT review and approval.
- **Access logging:** Production deployments should log all record access — searches and detail views — with timestamp and user identity, for audit purposes. This is not currently implemented in the prototype.
- **Encryption at rest:** The SQLite database currently has no encryption. In production, the database file should reside on an encrypted volume, or a database engine with native at-rest encryption should be used.
- **Data retention and deletion policy:** A formal retention policy specifying how long records remain in the database and under what conditions they may be corrected or removed needs to be established with DHS legal before launch.
- **Secrets and configuration management:** The production web server should not rely on default local ports or hardcoded file paths. Environment variables or a secrets manager should be used for any configuration that differs between the development and production environments.

---

## 10. Expanded Form Type Support

The current VetScan pipeline is calibrated specifically for Form MAGO-41 / Form 14, the Pennsylvania DHS burial card used from the Civil War era through WWII. Vietnam-era and later records use substantially different formats — full-size personnel records, DD-214 discharge papers — that the current zone map and page classifier are not designed for.

Extending support to these form types is the most impactful capability expansion for long-term completeness of the veterans record index:

- **New zone maps:** Each form type requires a calibrated set of zone coordinates derived from representative scans of that form. `DOCUMENTATION Team One Pipeline.md` (Section 8) documents the exact steps for adding a new form type, including how to measure field bounding boxes as normalized fractions of page dimensions.
- **Classifier retuning:** Full-size Vietnam-era records contain far more printed text than the handwritten index cards, so the word-count thresholds (`BLANK_WORD_THRESHOLD`, `BACK_WORD_MAX`, `FRONT_SCORE_MIN`) will need new values. Multi-page record formats also require changes to the front/back pairing logic — fixed N-page strides or content-based first-page detection rather than the current proximity window.
- **New field parsers:** DD-214 forms include service numbers in a specific format, discharge type fields, decoration records, and dates in formats not covered by the current parsers. These will require new parser functions modeled on the existing name and date parsers.
- **Database schema extension:** The current schema stores six data fields. Richer forms — particularly DD-214s — carry significantly more information, including discharge type, decorations awarded, and next-of-kin contact, that would require schema expansion and corresponding changes to the web UI.
- **Phased rollout:** Given the scope of this work, expanding form support should be phased: validate the new form type against a sample of 20–30 representative scans before committing to a full batch run, then ingest into a staging database for review before merging with the production `veterans.db`.
