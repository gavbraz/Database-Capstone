# VetScan — Technical Documentation

**Allegheny County Veteran Burial Records Digitization Pipeline**
Pennsylvania Department of Military and Veterans Affairs (DHS) — Capstone Deliverable

This document is the primary technical reference for the VetScan system. It covers what the program does, how it works internally, what is required to run it, how to operate it, and what to change if the system needs to be extended to record types other than the Allegheny County burial index cards. It is written for two audiences: DHS personnel who will run the system or evaluate it, and any future contributor who needs to extend it.

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Requirements](#2-system-requirements)
3. [Installation](#3-installation)
4. [Running the Pipeline](#4-running-the-pipeline)
5. [Pipeline Architecture](#5-pipeline-architecture)
6. [Output Format](#6-output-format)
7. [Configuration Reference](#7-configuration-reference)
8. [Adding a New Form Type](#8-adding-a-new-form-type)
9. [Module and Function Reference](#9-module-and-function-reference)
10. [Troubleshooting](#10-troubleshooting)
11. [Security and Data Handling](#11-security-and-data-handling)
12. [Performance Notes](#12-performance-notes)
13. [Glossary](#13-glossary)

---

## 1. Overview

VetScan ingests scanned veteran burial index cards (Form MAGO-41 / Form 14, the standardized format used by the Pennsylvania Department of Military and Veterans Affairs from the Civil War era through WWII) and produces structured, searchable output. For each card, the system extracts the veteran's name, dates of birth and death, service branch, rank, cemetery name and location, and grave/section information. Each card is written out as a named PDF, and every record is logged in a single audit CSV that is auditable end-to-end.

The system is fully local. No card image, no extracted text, and no metadata leaves the workstation it runs on. This is a hard requirement of the DHS data-handling agreement under which the project was carried out, and it is enforced in code: any execution path that would route through CPU-only inference (which would have allowed the system to run on commodity hardware without local accelerators) is explicitly blocked.

The system is designed for a specific Intel-based workstation that has an Intel AI Boost NPU and an Intel Arc integrated GPU, but the architecture is straightforward to retarget to other hardware if needed. See the section on hardware routing for what would have to change.

### Inputs and outputs at a glance

- **Input**: a single PDF containing scanned cards (front and back interleaved, with optional separator pages from the scanning stage).
- **Outputs**: one PDF per card in `output_cards/`, one `audit.csv` summarizing every page processed, and one `output_cards/ocr_failed/` directory containing any pages that produced no OCR text and need manual rescan.

---

## 2. System Requirements

### Hardware

The pipeline was developed and tested on an Intel Core Ultra workstation with the following components:

- **CPU**: Intel Core Ultra (any generation with the AI Boost NPU; the test machine uses Meteor Lake / Lunar Lake class silicon).
- **NPU**: Intel AI Boost (the integrated NPU on Core Ultra processors). Used as the primary accelerator for OCR detection.
- **GPU**: Intel Arc (integrated). Used as the fallback accelerator and as the device for the TrOCR handwriting model via Intel Extension for PyTorch (XPU).
- **RAM**: 16 GB minimum, 32 GB recommended. Each page at 300 DPI is roughly 25–35 MB in memory during processing, and the TrOCR model adds another ~1.5 GB resident.
- **Disk**: budget at least 5 GB for the OCR models (downloaded on first run), plus 10–20× the size of the input PDF for output PDFs and intermediate page images.

The pipeline will refuse to run on a system that exposes only a CPU through OpenVINO. This is a deliberate guardrail — early development on a CPU-only test machine produced 6–8 hour runtimes that were not operationally viable.

### Operating system

Tested on Windows 10 and Windows 11. The default `POPPLER_PATH` constant in the source assumes a Windows-style path (`C:/poppler/Library/bin`); on Linux or macOS, set the path explicitly via `--poppler-path` or by editing the constant.

### Software

- **Python**: 3.10 or 3.11. PyTorch and Intel Extension for PyTorch have stable wheels for these versions; 3.12 may work but has not been validated.
- **Conda or Miniconda**: recommended for environment management. The repository includes an `environment.yml`.
- **Poppler**: required by `pdf2image` to rasterize PDF pages. On Windows, the conventional install location is `C:/poppler/Library/bin`. On Linux it is normally already on `PATH`.
- **Intel OpenVINO runtime**: required for NPU and GPU device enumeration.
- **Intel Extension for PyTorch (IPEX)**: required for routing the TrOCR model onto the Arc GPU's XPU device.
- **Intel Arc GPU drivers**: must be current. Older driver versions silently fall back to CPU.

### Python package dependencies

Core OCR and image processing:

- `easyocr` — printed-text detection and recognition
- `transformers`, `torch` — TrOCR model loader and runtime
- `intel-extension-for-pytorch` — Intel XPU backend for PyTorch (optional but recommended)
- `openvino`, `openvino-dev` — NPU/GPU device routing
- `opencv-python` — preprocessing (deskew, contrast)
- `numpy`, `Pillow` — image arrays and conversion

PDF I/O:

- `pdf2image` — rasterize PDF pages to images
- `pypdf` — split source PDF into per-card output PDFs

Text post-processing:

- `jellyfish` — phonetic matching for name correction (optional; the Levenshtein fallback works without it)

The exact pinned versions are in the repository's `environment.yml`.

---

## 3. Installation

### Option A — Run the executable bundle (recommended for DHS operators)

If you are an operator and just want to run the pipeline, use the executable build distributed with the repository. It bundles Python, all dependencies, the OCR models, and the GUI into a single launchable artifact. Setup is:

1. Install the Intel OpenVINO runtime and current Intel Arc GPU drivers.
2. Install Poppler for Windows (place it in `C:/poppler/`).
3. Double-click the `VetScan.exe` (or equivalent) launcher.

The executable is currently in late-stage testing; if it does not detect the NPU or GPU on your specific hardware, fall back to Option B.

### Option B — Run from source (required for development or extension)

```bash
# 1. Clone the repository
git clone https://github.com/LampMountain/DHS_OCR_Burial_Records.git
cd DHS_OCR_Burial_Records

# 2. Create the Conda environment
conda env create -f environment.yml
conda activate vetscan

# 3. Install Intel Extension for PyTorch (XPU build)
#    See https://intel.github.io/intel-extension-for-pytorch/ for the
#    correct wheel for your PyTorch version.
pip install intel-extension-for-pytorch

# 4. Install Poppler (Windows): download from
#    https://github.com/oschwartz10612/poppler-windows/releases and
#    extract to C:/poppler/

# 5. Verify hardware detection
python -c "import openvino as ov; print(ov.Core().available_devices)"
# Expected output should include 'NPU' and/or 'GPU'.
```

On first run, EasyOCR and TrOCR will download their model weights from their respective hubs. Allow up to 2 GB of network transfer. After the first run, the models are cached locally and no network access is required.

### Verification

Run the pipeline against a small test PDF (a few sample cards) to verify the install:

```bash
python process_index_cards.py --input test_cards.pdf --output ./test_out
```

A successful run prints a final summary box showing the device used, page counts, paired/solo card counts, and total runtime.

---

## 4. Running the Pipeline

### Console invocation

```bash
python process_index_cards.py --input <scanned.pdf> [options]
```

#### Required arguments

| Argument          | Description                                                               |
|-------------------|---------------------------------------------------------------------------|
| `--input`, `-i`   | Path to the input PDF containing scanned cards.                           |

#### Optional arguments

| Argument               | Default | Description                                                                                                  |
|------------------------|---------|--------------------------------------------------------------------------------------------------------------|
| `--output`, `-o`       | `<input_dir>/output_cards` | Directory where per-card PDFs and the audit CSV are written.                                                 |
| `--dpi`                | 300     | Target DPI for PDF-to-image rasterization. 300 is correct for the index card set; reducing it loses accuracy. |
| `--blank-threshold`    | 5       | Word count below which a page is classified BLANK.                                                           |
| `--back-word-max`      | 60      | Word count above which a page is no longer eligible to be classified as a card BACK.                         |
| `--max-pair-distance`  | 5       | Maximum number of pages between a FRONT and its candidate BACK during pairing.                               |
| `--no-trocr`           | (off)   | Disable the TrOCR handwriting model. Faster but reduces cursive accuracy substantially.                      |
| `--poppler-path`       | `C:/poppler/Library/bin` | Path to the Poppler `bin` directory if it is not on `PATH`.                                                  |

### GUI invocation

The GUI provides the same functionality through a graphical interface aimed at operators. Launch it from the start menu shortcut (in the executable bundle) or by running the GUI entry script from source. The operator selects an input PDF, an output directory, and runs the pipeline; progress is reported as the pipeline advances through its stages.

### Reading the output

After a run completes, the console prints a summary box similar to:

```
╔═══════════════════════════════════════════════════╗
║              PIPELINE COMPLETE                    ║
╠═══════════════════════════════════════════════════╣
║  Device         : NPU                             ║
║  Source pages   : 1832                            ║
║  FRONTs         : 911                             ║
║  BACKs          : 880                             ║
║  BLANKs         : 41                              ║
║  OCR FAILED     : 0                               ║
║  Paired cards   : 880   (front + back)            ║
║  Solo cards     : 31    (front only)              ║
║  Names → review : 47    <- manual check needed    ║
║  Total time     : 2487.3 s                        ║
║  Avg per page   : 1.4 s                           ║
║  Output dir     : /path/to/output_cards           ║
╚═══════════════════════════════════════════════════╝
```

Two flags are worth attending to in this summary. **OCR FAILED** counts pages that produced no text at all and need to be rescanned manually; the affected page numbers are written to `output_cards/ocr_failed/`. **Names → review** counts records whose extracted veteran name did not match any entry in the common-name database within the configured Levenshtein distance, suggesting either OCR error or an uncommon historical spelling; these are flagged in the audit CSV with `name_needs_review = YES`.

---

## 5. Pipeline Architecture

The pipeline is a single-process, single-file Python program (`process_index_cards.py`) organized as a sequence of stages. Every page passes through the same stages in order; there is no dynamic dispatch between stages and no inter-page parallelism. The cost of this simplicity is single-threaded execution; the benefit is that the program is auditable end-to-end and that failures localize cleanly.

### High-level data flow

```
Input PDF
  │
  ▼
[detect_accelerator]  →  selects NPU or GPU; raises if neither present
  │
  ▼
[init_easyocr]        →  loads EasyOCR detector + recognizer
[init_trocr]          →  loads microsoft/trocr-base-handwritten
  │
  ▼
[ocr_pdf]             →  rasterizes each page (300 DPI), preprocesses,
  │                       runs EasyOCR for span detection and recognition,
  │                       runs TrOCR on low-confidence handwritten spans
  ▼
[classify_page]       →  per page: FRONT / BACK / BLANK / OCR_FAILED
  │                       based on word count, score, and zone-density signals
  ▼
[extract_fields_      →  for FRONT pages only: walks ZONE_MAP, pulls
   from_zones]            spans inside each required zone, parses
  │                       names (with Levenshtein correction), dates
  │                       (with century inference), branch, rank,
  │                       cemetery, grave info
  ▼
[pair_fronts_         →  walks the page sequence and pairs each FRONT
   and_backs]             with the nearest following BACK within
  │                       MAX_PAIR_DISTANCE pages
  ▼
[write_card_pdf]      →  writes one PDF per pair (or per solo FRONT)
                          to output_cards/, named by veteran + date
  │
  ▼
[write_audit_csv]     →  writes audit.csv summarizing every page
```

### Stage detail

#### 5.1 Hardware detection (`detect_accelerator`)

OpenVINO's `Core.available_devices` is queried. If `NPU` is present, the pipeline runs in NPU mode; otherwise if `GPU` is present, it runs in GPU mode. If only `CPU` is present, `RuntimeError` is raised and the pipeline exits. This is deliberate: CPU-only inference produced ~8 hour runtimes during development on the test corpus, and silent fallback to that mode would have been a regression.

#### 5.2 Image preprocessing (`deskew_image`, `enhance_for_ocr`, `preprocess_card_image`)

Each rasterized page goes through:

1. **Deskew** — Hough-line detection identifies dominant horizontal edges (typically the printed form rules on the card). The skew angle is computed and the image is rotated to undo it. The fallback for cards with no clear horizontal edges is a no-op (skew = 0).
2. **Resize** — pages whose long edge exceeds 3000 pixels are downscaled to 3000 (≈300 DPI on a 10" card). This bounds memory and keeps EasyOCR throughput predictable.
3. **CLAHE** — Contrast Limited Adaptive Histogram Equalization, with `clipLimit=2.0` and `tileGridSize=8×8`, lifts the contrast of faded handwriting without blowing out clean printed text.
4. **Sharpening** — a gentle 3×3 Laplacian-style kernel is applied to recover edge definition lost in scanning.

#### 5.3 OCR (`ocr_pdf`, `ocr_page_image`, `enhance_span_with_trocr`)

EasyOCR is run on each preprocessed page image. EasyOCR returns a list of *spans*, each of which is a tuple of `(bounding_box, text, confidence)`. For every span whose confidence is below `LOW_CONF_THRESHOLD` (0.4) and whose text looks like it could be handwritten data (i.e., not a printed form label), the span's image region is cropped and re-recognized by TrOCR. The TrOCR result replaces the EasyOCR result if it scores higher under the field-specific scoring functions (`_score_name_text`, `_score_date_text`).

The reason for span-level rather than zone-level TrOCR is empirical: an earlier version of the pipeline cropped each form zone (the rectangle reserved for "name", "date of birth", etc.) and ran TrOCR on the crop as a whole. TrOCR's autoregressive decoder, when given a region containing more than one text element or a partially blank area, would produce confident but fabricated output. Constraining TrOCR to one tight bounding box per call eliminates the hallucination.

#### 5.4 Page classification (`classify_page`)

Each page is assigned one of four labels:

- **OCR_FAILED** — zero spans detected and zero OCR text. Page is set aside for manual rescan.
- **BLANK** — fewer than `BLANK_WORD_THRESHOLD` (5) words. Likely a separator page, a back of a blank card, or a scanning artifact.
- **BACK** — more than `BLANK_WORD_THRESHOLD` but fewer than `BACK_WORD_MAX` (60) words, and density is concentrated in the lower half (where the back of a card typically has continuation text or a stamp).
- **FRONT** — has structured zone-density signals: text spans concentrated in the standardized field positions for Form MAGO-41. Field score is computed concurrently and stored on the `PageRecord`.

#### 5.5 Field extraction (`extract_fields_from_zones`)

For each FRONT page, the pipeline walks `ZONE_MAP`. For each *required* zone (those listed in `REQUIRED_ZONES`), it collects the spans whose bounding boxes fall inside the zone's normalized rectangle, joins their text, strips printed form labels (using `PRINTED_LABEL_FRAGMENTS`), and parses the result according to the zone's expected content:

- **Names** are tokenized, scrubbed of common OCR artifacts, and matched against a ~700-entry common-name database (split into first names and surnames) using Levenshtein distance. Matches within distance 2 are accepted; misses are flagged with `name_needs_review`.
- **Dates** are matched against several regex patterns and normalized to `mm/dd/yyyy`. Two-digit years are expanded by inferring the likely century from the war field on the same card (a Civil War card with year "65" is 1865, not 1965).
- **Branch** is determined by spatial mark detection in the "SERVED IN" parentheses on the card. A check, X, or any non-empty mark in the Army/Navy/Marine Corps box flags the corresponding branch.
- **Rank** is taken as the printed text in the rank zone, with case-folding to the canonical form.
- **Cemetery name and location** are taken from the cemetery zones with printed-label stripping.
- **Grave section / range** is taken from the grave zone.

#### 5.6 Front/back pairing (`pair_fronts_and_backs`)

The pipeline walks the page sequence in order. Each FRONT is paired with the nearest following BACK within `MAX_PAIR_DISTANCE` pages. FRONTs with no eligible BACK are written out as solo. BLANKs and OCR_FAILEDs are skipped. The pairing logic does not look across pages that are themselves classified as FRONT — i.e., it does not "skip past" another card to find a back.

#### 5.7 Output (`write_card_pdf`, `write_audit_csv`)

For each pair (or solo FRONT), the corresponding pages are extracted from the source PDF using `pypdf` and written as a new PDF in `output_cards/`. The output filename is `<veteran_name>_<date_of_death>.pdf` when both are extractable, with non-filesystem-safe characters scrubbed. The audit CSV is a single file containing one row per source page, including all extracted fields and review flags.

---

## 6. Output Format

### 6.1 Per-card PDFs

Each output PDF is a 1- or 2-page document containing the original scanned image of the card front and (if paired) back. Filenames follow the pattern `<safe_name>_<safe_date>.pdf`, capped at 60 characters, with spaces replaced by underscores and special characters stripped. If the name or date could not be extracted, a placeholder is used.

### 6.2 Audit CSV (`audit.csv`)

The audit CSV is the structured-data product of the pipeline. It contains one row per *source page* (not per card), so blanks, backs, and OCR-failed pages all appear. Columns:

| Column                  | Meaning                                                                              |
|-------------------------|--------------------------------------------------------------------------------------|
| `page_number`           | 1-indexed page number in the source PDF.                                             |
| `page_index`            | 0-indexed page number (for programmatic use).                                        |
| `classification`        | FRONT / BACK / BLANK / UNKNOWN.                                                      |
| `classification_tier`   | Internal tier label used by the classifier (rule that fired).                        |
| `ocr_failed`            | YES / NO.                                                                            |
| `word_count`            | Number of OCR-recognized words on the page.                                          |
| `low_conf_spans`        | Count of EasyOCR spans below `LOW_CONF_THRESHOLD`.                                   |
| `field_score`           | Number of required fields successfully extracted (0–9 for FRONTs, 0 otherwise).      |
| `device_used`           | NPU or GPU (the accelerator that ran OCR for this page).                             |
| `veteran_name`          | Extracted name; empty if not a FRONT or not extractable.                             |
| `name_needs_review`     | YES if the name did not match the common-name database within Levenshtein distance.  |
| `date_of_death`         | Normalized to mm/dd/yyyy.                                                            |
| `date_of_birth`         | Normalized to mm/dd/yyyy.                                                            |
| `service_number`        | Service number if extractable.                                                       |
| `war`                   | War or conflict period (Civil War, WWI, WWII, etc.).                                 |
| `service_branch`        | Army / Navy / Marine Corps / etc.                                                    |
| `organization`          | Unit or organization.                                                                |
| `service_date_from`     | Service start date.                                                                  |
| `service_date_to`       | Service end date.                                                                    |
| `rank`                  | Rank.                                                                                |
| `cemetery_name`         | Cemetery name.                                                                       |
| `cemetery_location`     | City / state.                                                                        |
| `headstone`             | Headstone information.                                                               |
| `grave_location`        | Section, range, grave.                                                               |
| `record_number`         | Card record number (top-right corner of the form).                                   |
| `record_date`           | Date the record was filed.                                                           |
| `pair_page_number`      | The page number this page was paired with (FRONT ↔ BACK).                            |
| `output_filename`       | Path to the per-card PDF written for this record.                                    |
| `raw_text_preview`      | First 200 characters of raw OCR text, for spot-checking.                             |

### 6.3 OCR-failed directory (`output_cards/ocr_failed/`)

Pages where the OCR layer returned no text are extracted from the source PDF and written here as single-page PDFs, named `ocr_failed_p<N>.pdf` where `N` is the source page number. These should be reviewed and rescanned at higher quality if recoverable.

---

## 7. Configuration Reference

Configuration is concentrated at the top of `process_index_cards.py`. Most values are also overridable via CLI flags.

| Constant                | Default | Effect                                                                                          |
|-------------------------|---------|-------------------------------------------------------------------------------------------------|
| `TARGET_DPI`            | 300     | Rasterization DPI. Lowering hurts accuracy; raising past 600 hurts throughput with no gain.     |
| `BLANK_WORD_THRESHOLD`  | 5       | Below this word count, a page is BLANK.                                                         |
| `BACK_WORD_MAX`         | 60      | Above this, a page is too dense to be a card BACK.                                              |
| `MAX_PAIR_DISTANCE`     | 5       | Pages between a FRONT and its candidate BACK during pairing.                                    |
| `FRONT_SCORE_MIN`       | 8       | Minimum field score for a page to be a confident FRONT (out of 9 required zones).               |
| `LOW_CONF_THRESHOLD`    | 0.4     | EasyOCR confidence below which TrOCR is invoked for re-recognition.                             |
| `TROCR_MODEL_NAME`      | `microsoft/trocr-base-handwritten` | Hugging Face identifier for the TrOCR weights.                                                  |
| `POPPLER_PATH`          | `C:/poppler/Library/bin` | Default Poppler `bin` location on Windows.                                                      |

### `ZONE_MAP`

A dictionary mapping zone names to normalized rectangles `(y_start, y_end, x_start, x_end)` as fractions of the card's height and width. The rectangles below are calibrated for Form MAGO-41 / Form 14:

| Zone                | y_start | y_end | x_start | x_end |
|---------------------|---------|-------|---------|-------|
| `record_number`     | 0.00    | 0.10  | 0.60    | 1.00  |
| `name`              | 0.10    | 0.22  | 0.00    | 0.52  |
| `date_of_birth`     | 0.10    | 0.22  | 0.52    | 0.78  |
| `date_of_death`     | 0.10    | 0.22  | 0.78    | 1.00  |
| `veteran_of`        | 0.22    | 0.34  | 0.00    | 0.42  |
| `war`               | 0.22    | 0.34  | 0.42    | 0.62  |
| `served_in`         | 0.22    | 0.38  | 0.52    | 1.00  |
| `service_from`      | 0.34    | 0.42  | 0.00    | 0.22  |
| `service_to`        | 0.38    | 0.46  | 0.00    | 0.22  |
| `organization`      | 0.34    | 0.46  | 0.22    | 0.78  |
| `rank`              | 0.34    | 0.46  | 0.78    | 1.00  |
| `cemetery_name`     | 0.46    | 0.56  | 0.00    | 1.00  |
| `cemetery_location` | 0.54    | 0.64  | 0.00    | 1.00  |
| `grave_section`     | 0.64    | 0.76  | 0.00    | 0.50  |
| `headstone`         | 0.64    | 0.76  | 0.50    | 1.00  |
| `record_date`       | 0.76    | 0.88  | 0.00    | 0.42  |
| `registrar`         | 0.76    | 0.88  | 0.42    | 1.00  |

### `REQUIRED_ZONES`

A set listing which zones contain data the pipeline must extract. For Form MAGO-41:

```
{ name, date_of_birth, date_of_death, war, served_in, rank,
  cemetery_name, cemetery_location, grave_section }
```

Zones in `ZONE_MAP` but not in `REQUIRED_ZONES` are skipped during extraction. This is a performance optimization — zones with text that does not need to be parsed and stored (e.g., the registrar's signature) do not need to consume TrOCR cycles.

### `PRINTED_LABEL_FRAGMENTS`

A set of words that appear as printed form labels (NAME, DATE, BIRTH, ARMY, NAVY, etc.). These are stripped during extraction so that the printed form text does not contaminate the data fields. If you adapt the system to a new form type, add any new label words your form contains.

---

## 8. Adding a New Form Type

The pipeline is form-aware in three places: the zone map, the required-zones set, and the printed-label list. To extend the system to a record type other than the index cards (for example, the Vietnam-through-current-day full-size personnel records), the following steps cover the work in order:

1. **Sample twenty to thirty representative scans of the new form.** They should span the variation you expect to see — different fonts, handwriting styles, different scan qualities. Open them in any image viewer that lets you read off pixel coordinates.

2. **Identify the bounding box for each required field as a fraction of page dimensions.** For each field, measure `(y_start, y_end, x_start, x_end)` as fractions in the range `[0, 1]`. Account for variation across your sample — choose a rectangle slightly larger than the smallest observed instance, but not so large that it overlaps a neighboring field.

3. **Define a new `ZONE_MAP_<formname>` dictionary** with the same shape as the existing `ZONE_MAP`. Each entry is keyed by field name and maps to a four-tuple. Use the existing map as a template.

4. **Define a new `REQUIRED_ZONES_<formname>` set** listing only the fields you actually need to extract. Anything not in this set is skipped.

5. **Update `PRINTED_LABEL_FRAGMENTS`** with any new label words that appear on the form (e.g. "DISCHARGE", "DD214", "HONORABLE", "SEPARATION"). These are filtered during extraction.

6. **Add a form-type CLI flag and dispatch.** Plumb a `--form-type` argument that selects which `ZONE_MAP_*` and `REQUIRED_ZONES_*` to use. This is a small refactor — currently the names are unqualified globals.

7. **Re-tune `classify_page()` if the new form has a different word-count profile** than the index cards. The current classifier is calibrated for short handwritten cards: a Vietnam-era full-size form will have far more printed text and will be classified as something other than a card BACK by default. The thresholds `BLANK_WORD_THRESHOLD`, `BACK_WORD_MAX`, and `FRONT_SCORE_MIN` will likely all need new values.

8. **If the new form has multi-page records, revisit `pair_fronts_and_backs()`.** The current logic pairs adjacent fronts and backs within a small page-distance window. An N-page form will need a different grouping rule — either a fixed N-page stride or a content-based "first page of record" detector.

9. **Add field-specific parsers if needed.** The existing parsers cover names, dates (with century inference), branch, rank, and free-text fields. New field types — service numbers in a particular format, signature blocks, dates in formats other than mm/dd/yyyy — may need new parser functions modeled on the existing ones.

10. **Test on the original sample set** before running on the full corpus.

---

## 9. Module and Function Reference

This section documents the functions a maintainer is most likely to need to read or modify, grouped by stage. All live in `process_index_cards.py`.

### Hardware

- **`detect_accelerator() -> str`** — Returns `"NPU"` or `"GPU"`. Raises `RuntimeError` if neither is available. Called once at pipeline start.

### Preprocessing

- **`deskew_image(img: np.ndarray) -> np.ndarray`** — Hough-line skew correction. Returns the rotated image.
- **`enhance_for_ocr(img: np.ndarray) -> np.ndarray`** — CLAHE contrast + sharpening. Returns the enhanced image.
- **`preprocess_card_image(img: np.ndarray) -> np.ndarray`** — Combines deskew, resize, and enhance into one call.

### OCR

- **`init_easyocr(device: str)`** — Initializes the global EasyOCR reader. Honors the device hint, falls back to CPU for the EasyOCR component if the OpenVINO/PyTorch pairing on the host is unstable.
- **`init_trocr()`** — Loads the TrOCR processor and model. Routes to XPU if Intel Extension for PyTorch is available, otherwise CPU (TrOCR is small enough that CPU is acceptable).
- **`trocr_recognize(crop_img: np.ndarray) -> str`** — Runs TrOCR on a single crop. Returns recognized text or empty string on failure.
- **`ocr_page_image(img: np.ndarray) -> tuple`** — Runs the full OCR stack on one page image. Returns `(text, spans)`.
- **`ocr_pdf(pdf_path: str) -> tuple`** — Top-level OCR over a PDF. Returns `(page_texts, page_spans, original_images)`.

### Classification and extraction

- **`classify_page(record: PageRecord)`** — Sets `record.classification` and `record.classification_tier` based on word count and field-density signals.
- **`extract_fields_from_zones(spans, img_h, img_w, original_img)`** — Walks `ZONE_MAP` and pulls out per-field text. Returns a dict mapping field names to extracted values.
- **`get_spans_in_zone(spans, zone, ...)`** — Filters spans to those inside a normalized rectangle.

### Date and name post-processing

- **`normalize_date(raw, war_str, ...) -> str`** — Parses a raw date string and returns it in `mm/dd/yyyy` form. Uses `infer_century` for two-digit years.
- **`infer_century(two_digit_year, war_str, ...) -> int`** — Returns 1800, 1900, or 2000 based on the war context and the digits.
- **`correct_name(raw_name) -> tuple`** — Returns `(corrected_name, needs_review_bool)`.
- **`fuzzy_match_name(token, max_dist=2) -> str`** — Levenshtein lookup against the common-name database. Returns the best match or the original token.
- **`levenshtein_distance(s1, s2) -> int`** — Standard Levenshtein implementation. Used by `fuzzy_match_name`.

### Branch detection

- **`detect_branch_from_spans(spans, img_height, img_width) -> str`** — Returns `"Army"`, `"Navy"`, `"Marine Corps"`, etc. based on which "SERVED IN" sub-box has a mark.
- **`detect_branch_from_text(text) -> str`** — Fallback that scans free text for branch keywords. Used when the spatial detector finds no mark.

### Pairing and output

- **`pair_fronts_and_backs(records: list) -> list`** — Returns a list of `(front, back_or_None)` tuples.
- **`write_card_pdf(input_pdf, front_rec, back_rec, output_dir, card_num) -> str`** — Writes one output PDF using `pypdf`. Returns the filename written.
- **`write_audit_csv(records, output_path)`** — Writes the audit CSV. See Section 6.2 for the column list.

### Pipeline orchestration

- **`run_pipeline(args: argparse.Namespace)`** — Drives the whole pipeline end-to-end. The `__main__` block calls this.

### Data model

- **`@dataclass PageRecord`** — Holds everything the pipeline knows about one source page: its index, classification, raw OCR text, span list, extracted fields, the device that processed it, the page it was paired with, the output filename, and review flags.

---

## 10. Troubleshooting

### `[FATAL] OpenVINO is not installed`

Install with `pip install openvino openvino-dev`. The pipeline refuses to run without OpenVINO because OpenVINO is the only path to the NPU on this hardware.

### `[FATAL] Neither NPU nor GPU available via OpenVINO`

OpenVINO is installed but cannot see the accelerators. Common causes:

- The Intel Arc GPU drivers are stale. Update them.
- The system is running in a virtual machine that has not been configured to expose the NPU/GPU to the guest.
- The OpenVINO installation does not include the device plugins. Reinstall with `pip install openvino[full]`.

### `pdf2image` or Poppler errors

Confirm Poppler is installed and that `--poppler-path` points at the `bin/` directory containing `pdftoppm.exe` (Windows) or `pdftoppm` (Linux/macOS).

### TrOCR runs on CPU even though IPEX is installed

`torch.xpu.is_available()` returns False on systems where the IPEX wheel does not match the PyTorch version. Confirm that the IPEX wheel you installed corresponds exactly to the PyTorch version in the environment.

### Names are mostly flagged for review

This typically means OCR confidence is uniformly low across the run, which in turn usually means the input was scanned at low DPI or that the cards are unusually faded. Try re-scanning a few representative cards at 400 DPI and re-running.

### "Pipeline complete" but `output_cards/` is empty

Check the audit CSV. If `classification` is `BACK` or `BLANK` for every page, the pipeline has not detected any FRONTs. The most common cause is that the source PDF has the cards in an unexpected orientation; rotate the source PDF 180° and re-run.

### Output filenames have the placeholder name and date

The pipeline could not extract a name or date with high enough confidence to use in the filename. The card itself is still correctly written as a PDF; the placeholder is a naming fallback. Check `audit.csv` to see what was extracted.

### Runtime is much longer than 42 minutes

The pipeline has likely fallen back to CPU for the EasyOCR component. Check the startup logs for the line `[OCR] EasyOCR ready (device target: ...)`. If the target says CPU and you expected NPU or GPU, see the OpenVINO and IPEX troubleshooting items above.

---

## 11. Security and Data Handling

The DHS data-handling agreement under which this project was carried out requires that no card image and no metadata derived from a card image leave the workstation it is processed on. This has several concrete implications for any future change to the pipeline:

- **No external API calls.** Adobe OCR was evaluated as a baseline early in the project and was found unacceptable, but had it been adopted, all OCR would have run on the local machine through the desktop product, not through the Adobe cloud API. The current pipeline uses no network at runtime — model weights are downloaded once and cached locally.
- **No cloud storage.** Output PDFs and the audit CSV must be written to the local filesystem and remain under the operator's control.
- **No remote logging or telemetry.** Diagnostic logs, if added, must write to local files only.
- **Model weights are local after first run.** EasyOCR and TrOCR cache their weights to the user's home directory on first run; subsequent runs need no network.
- **The executable bundle ships the model weights.** This means even the first-run network fetch is eliminated when the executable is used.

If a future change introduces any network-bound component, it requires sign-off from the DHS contact before it ships. This includes seemingly innocuous additions like crash-reporting libraries or auto-updaters.

---

## 12. Performance Notes

### Observed runtime

End-to-end runtime on the test workstation, processing the Civil War – WWII index-card set:

- **Approximately 42 minutes** total wall-clock for the full set, with EasyOCR running on CPU and TrOCR on the Arc GPU's XPU device.
- **Approximately 1.4 seconds per page** averaged across FRONT, BACK, and BLANK pages.

This is down from an initial figure of roughly 8 hours when the early version of the pipeline ran TrOCR on every zone of every page.

### Throughput levers

Three changes during development account for most of the speedup:

1. **Span-level rather than zone-level TrOCR.** TrOCR is invoked only on EasyOCR spans below the confidence threshold, not on every zone of every card. This was the largest single improvement.
2. **Required-zones filtering.** Zones in `ZONE_MAP` but not in `REQUIRED_ZONES` are skipped entirely. On Form MAGO-41, this skips the registrar and a few other low-value zones.
3. **TrOCR on XPU rather than CPU.** Moving TrOCR to the Arc GPU via Intel Extension for PyTorch cut TrOCR call latency by roughly 5×.

### Where future engineering would help most

- **Native NPU OCR.** EasyOCR currently runs on CPU because the OpenVINO conversion of its detector and recognizer is fragile on the test platform's PyTorch build. A clean OpenVINO-IR conversion would let the NPU do the detection pass it was provisioned for. Expected speedup: 2–3×.
- **Page-level batching.** EasyOCR is invoked one page at a time. Batching at the model level (collecting N pages of crops and running them through the recognizer in one call) would reduce per-call overhead, though it complicates the streaming I/O.

### Where it would *not* help

- **Multi-process parallelism.** Tempting, but the GPU is already the bottleneck for TrOCR — running multiple processes that all want the GPU just thrashes it.
- **Lowering DPI.** The pipeline is already at 300 DPI. Going lower noticeably hurts cursive accuracy.

---

## 13. Glossary

- **EasyOCR** — open-source OCR library with separate text-detection and text-recognition models. Used here for printed-text detection on every page.
- **TrOCR** — Microsoft's transformer-based handwritten OCR model. Used here for handwritten-text re-recognition on low-confidence spans.
- **OpenVINO** — Intel's neural-network runtime. Used for device enumeration and (in the future) NPU-routed inference.
- **Intel Extension for PyTorch (IPEX)** — Intel's PyTorch backend that exposes the Arc GPU as the `xpu` device. Used to run TrOCR on the GPU.
- **NPU** — Neural Processing Unit. The dedicated AI accelerator on Intel Core Ultra processors.
- **XPU** — PyTorch's device name for an Intel GPU exposed via IPEX.
- **Span** — one OCR result, consisting of a bounding box, recognized text, and confidence score.
- **Zone** — a named, normalized rectangle on a card corresponding to a known data field (name, date of birth, etc.). Defined in `ZONE_MAP`.
- **FRONT / BACK / BLANK / OCR_FAILED** — the four classifications a page can receive.
- **Form MAGO-41 / Form 14** — the standardized burial card layout used by the Pennsylvania Department of Military and Veterans Affairs from the Civil War era through WWII.
- **Audit CSV** — `audit.csv`, the per-page summary file written at the end of every pipeline run.

---

*Document maintained alongside `process_index_cards.py`. Update both together.*
