# FreightScan AI — Complete Project Knowledge Base

> Single source of truth. Consolidates README, PROJECT, ROADMAP, all update logs, all source modules, and all architectural decisions.

---

## 1. What the Project Does

FreightScan AI converts freight contract PDFs into populated Excel spreadsheets — **automatically, locally, and for free**.

- **Input:** Any freight contract PDF (text-based or scanned)
- **Output:** `ATL0347N25 Template.xlsm` filled with rates, origin arbitraries, and destination arbitraries — VBA macros preserved
- **No internet.** No API keys. No AI models. Runs 100% offline on any machine.
- **Current engine:** Pure NLP — regex patterns + rule-based grid parsing. No Ollama. No LLM.

What used to take hours of manual data entry now takes **under 10 seconds** on any computer.

---

## 2. Tech Stack

### Backend
| Layer | Technology | Purpose |
|---|---|---|
| Web Framework | FastAPI + Uvicorn | Async HTTP API + WebSocket progress |
| PDF Parsing (primary) | pdfplumber | Fast text and table extraction (<2 sec) |
| PDF Parsing (fallback) | Docling 2.0 + EasyOCR | Scanned/image PDFs only (optional install) |
| Data Extraction | Regex + rule-based grid parser | NLP-first, deterministic, microsecond-speed |
| Excel Output | openpyxl | Write `.xlsm` with VBA macros preserved |
| Data Validation | Pydantic 2.x | Type-safe settings and schemas |
| Async I/O | aiofiles + httpx | Non-blocking file operations |

### Frontend
| Layer | Technology | Purpose |
|---|---|---|
| UI Framework | React + Vite | File upload, progress display, download |
| Real-time | WebSocket | Live progress updates from backend |

---

## 3. Full Architecture & Data Flow

```
┌─────────────┐
│  PDF Upload │  POST /api/upload
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  PDF EXTRACTION (pdf_extractor.py)                      │
│  1. pdfplumber (primary) — text + tables, <2 sec        │
│  2. Docling fallback — only if <100 chars extracted     │
│     └─ SHA-256 cache: instant on repeat runs            │
└──────────────────────────┬──────────────────────────────┘
                           │ structured dict:
                           │ { sections[], surcharge_text, pages_total }
                           ▼
┌─────────────────────────────────────────────────────────┐
│  NLP EXTRACTION (ollama_extractor.py)                   │
│                                                         │
│  Pass 1 — Metadata (regex):                             │
│    contract_id, carrier, effective_date, expiration_date│
│                                                         │
│  Pass 2 — Surcharges (regex):                           │
│    AMS, HEA, AGW, RDS → value/INCLUSIVE/TARIFF          │
│                                                         │
│  Pass 3 — Rate sections (per origin, all parallel):     │
│    ├─ _detect_header_row() → map columns                │
│    ├─ _extract_from_grid() → rule-based (0ms)           │
│    └─ (no LLM fallback — pure NLP)                      │
│                                                         │
│  Pass 4 — Origin/Dest Arbitraries (rule-based):         │
│    Point column → origin_city / destination_city        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  DATA MAPPING & DEDUPLICATION (field_mapper.py)         │
│  • Normalize 300+ port name variants (normalizer.py)    │
│  • Convert dates → Excel serial numbers                 │
│  • Deduplicate by (origin, dest, service, rates)        │
│  • Validate rate bounds, filter empty rows              │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  EXCEL EXPORT (excel_writer.py)                         │
│  Template: ATL0347N25 Template.xlsm (VBA preserved)     │
│  Sheet 1: Rates (columns A–T, 20 fields)                │
│  Sheet 2: Origin Arbitraries (columns A–Q, 17 fields)   │
│  Sheet 3: Destination Arbitraries (columns A–N, 14 flds)│
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
                    GET /api/download
```

---

## 4. Folder Structure

```
hackathon/
├── backend/
│   ├── main.py                  ← FastAPI app, routes, pipeline orchestrator
│   ├── config.py                ← Settings (Pydantic, reads .env)
│   ├── requirements.txt         ← Python dependencies
│   ├── extraction/
│   │   ├── pdf_extractor.py     ← pdfplumber primary + Docling fallback
│   │   └── page_classifier.py   ← Page type detection helpers
│   ├── ai/
│   │   ├── ollama_extractor.py  ← NLP extraction engine (regex + grid parser)
│   │   └── claude_extractor.py  ← (unused legacy file)
│   ├── mapping/
│   │   ├── field_mapper.py      ← Raw dicts → typed dataclasses + dedup
│   │   ├── normalizer.py        ← Port name normalization (300+ variants)
│   │   └── schema.py            ← RateRow, OriginArbitraryRow, DestinationArbitraryRow
│   └── excel/
│       └── excel_writer.py      ← openpyxl writer, VBA-safe .xlsm output
├── frontend/
│   └── src/
│       ├── App.jsx              ← Root component, upload + polling logic
│       └── components/
│           └── ProgressPanel.jsx ← 6-stage progress bar, live ETA, elapsed timer
├── templates/
│   └── ATL0347N25 Template.xlsm ← Excel output template (VBA macros intact)
├── README.md                    ← Setup and run instructions
└── know.md                      ← This file (complete knowledge base)
```

---

## 5. Module-by-Module Breakdown

### `backend/main.py`
FastAPI application and pipeline orchestrator.

**Key routes:**
| Route | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Returns `{"status":"ok","mode":"nlp"}` |
| `/api/upload` | POST | Accepts one or more PDFs, returns `job_id` per file |
| `/api/process/{job_id}` | POST | Starts the pipeline as an async background task |
| `/api/status/{job_id}` | GET | Returns current job dict (status, %, rows found) |
| `/api/preview/{job_id}` | GET | Returns first 100 rate rows for frontend preview |
| `/api/download/{job_id}` | GET | Streams the completed `.xlsm` file |
| `/ws/progress/{job_id}` | WebSocket | Pushes live job state updates to the frontend |

**Pipeline stages broadcast via WebSocket:**
```
UPLOADED → PDF_PARSING (10%) → EXTRACTING_TEXT (35%) →
NLP_PROCESSING (40%→70%) → WRITING_EXCEL (85%) → COMPLETE (100%)
```

**Job state dict:**
```python
{
    "job_id": str,
    "filename": str,
    "status": str,          # one of the stages above
    "stage_pct": int,       # 0–100
    "pages_total": int,
    "pages_done": int,
    "rows_extracted": int,
    "error": str | None,
    "output_path": str | None,
    "preview_data": list,   # first 100 rate rows
}
```

---

### `backend/config.py`
Pydantic settings loaded from `.env` at project root.

```python
class Settings(BaseSettings):
    upload_dir: Path   # where uploaded PDFs are saved
    output_dir: Path   # where .xlsm results are saved
    template_path: Path  # ATL0347N25 Template.xlsm
```

---

### `backend/extraction/pdf_extractor.py`
PDF parsing — primary entry point is `extract_pdf(pdf_path: str) -> dict`.

**What it returns:**
```python
{
    "sections": [
        {
            "origin": str,         # cleaned origin city name
            "via": str,            # via port (if any)
            "scope": str,          # trade lane, e.g. "NORTH AMERICA - ASIA (WB)"
            "raw_text": str,       # all text from this section
            "tables": [            # list of table grids
                [                  # one table = list of rows
                    [cell, cell],  # one row = list of cell strings
                ]
            ],
            "in_arb": None | "origin" | "dest"
        },
        ...
    ],
    "surcharge_text": str,   # text block containing AMS/HEA/AGW/RDS info
    "pages_total": int,
    "_docling": bool,        # True if Docling was used instead of pdfplumber
}
```

**Section detection logic (`_split_sections_from_elements`):**
- Walks all pdfplumber elements in reading order (top-to-bottom, page-by-page)
- Detects `ORIGIN:`, `ORIGIN VIA:` headers via `ORIGIN_HEADER_RE`
- Detects `ARBITRAR` keyword to flag `in_arb = "origin"` or `"dest"`
- Detects trade lane scope headers like `[NORTH AMERICA - ASIA (WB)]`
- Accumulates `current_texts` and `current_tables` until the next ORIGIN header
- Calls `flush_section()` to commit a section when a new ORIGIN is encountered

**Known bug — grouped origins (critical):**
When multiple consecutive `ORIGIN:` headers appear before a shared rate table (e.g., `CHICAGO → VIA LOS ANGELES`, `HALIFAX → VIA HALIFAX`, `HOUSTON → VIA HOUSTON` all before one table), `flush_section()` is called on each new ORIGIN and discards all but the last one. Fix: buffer pending origins and emit one section per origin when the shared table is finally seen.

**Origin name cleaning (`_clean_origin_name`):**
Strips in order:
1. Service type suffix: `(CY)`, `(CY/CY)`, `(CFS)`, `(FCL)`, etc.
2. Country name: `, UNITED STATES`, `, CHINA`, `, TAIWAN`, etc.
3. 2-letter state/province code: `, CA`, `, TX`, `, BC`, etc.
4. Everything after remaining commas

`LOS ANGELES, CA, UNITED STATES(CY)` → **`LOS ANGELES`**

**pdfplumber table strategies (tried in order):**
1. Line-based: `vertical_strategy="lines"`, `horizontal_strategy="lines"` — for grid tables
2. Text-based: `vertical_strategy="text"`, `horizontal_strategy="text"` — for borderless tables
3. Picks the strategy that found the most non-empty cells

**Docling fallback:**
- Used only if pdfplumber extracts fewer than 100 characters from the entire PDF
- SHA-256 cached in `_docling_cache/` — repeat runs skip Docling entirely
- Uses `TableFormerMode.ACCURATE` by default; change to `FAST` on low-spec hardware

---

### `backend/ai/ollama_extractor.py`
NLP extraction engine. Entry point: `extract_with_ollama(extracted: dict) -> dict`.

**Returns:**
```python
{
    "rates": [RateRow, ...],
    "origin_arbitraries": [OriginArbitraryRow, ...],
    "destination_arbitraries": [DestinationArbitraryRow, ...],
}
```

#### NLP Pass 1 — Metadata extraction (regex)

```python
_CONTRACT_ID_EXTRA = re.compile(
    r"(?:CONTRACT\s+(?:NUMBER|NO\.?|#)\s*[:\-]?\s*|REF(?:ERENCE)?\s+NO\.?\s*[:\-]?\s*)([A-Z0-9][\w\-]{3,})",
    re.I,
)
_CARRIER_COLON_RE = re.compile(
    r"(?:CONTRACTED?\s+)?CARRIER\s*[:\-]\s*([A-Za-z][\w\s,\.]+?)(?:\n|,|\.|;|$)",
    re.I,
)
_DATE_PATTERNS = [...]  # effective_date, expiration_date in MM/DD/YYYY and "DD MMM YYYY" formats
```

`_extract_metadata_enhanced(text, existing)` — fills in any missing fields from the section text.

#### NLP Pass 2 — Surcharge extraction (regex)

```python
_SURCHARGE_KW = {
    "ams_china_japan":     re.compile(r"\b(?:AMS|america\s+manifest(?:\s+system)?(?:\s+surcharge)?)\b", re.I),
    "hea_heavy_surcharge": re.compile(r"\b(?:HEA|heavy\s+(?:lift|cargo|equipment|surcharge))\b", re.I),
    "agw":                 re.compile(r"\b(?:AGW|arbitrary\s+gross\s+weight|arbitrary\s+weight)\b", re.I),
    "rds_red_sea":         re.compile(r"\b(?:RDS|red\s+sea(?:\s+surcharge)?|redex)\b", re.I),
}
_SURCHARGE_VAL_RE  = re.compile(
    r"(?:USD?\s*\$?\s*|(?::\s*|=\s*))(\d[\d,]*(?:\.\d+)?)"
    r"|(\d[\d,]*(?:\.\d+)?)\s*(?:USD|per\s+(?:BL|B/L|container|unit))",
    re.I,
)
_INCLUSIVE_RE = re.compile(r"\b(?:INCLUSIVE|INCLUDED|INCL\.?)\b", re.I)
_TARIFF_RE    = re.compile(r"\b(?:AS\s+PER\s+TARIFF|TARIFF|AS\s+PER\s+RATE\s+TARIFF)\b", re.I)
```

`_extract_surcharges_regex(surcharge_text)`:
- Scans each line for each surcharge keyword
- If found: checks same line + next line for value, INCLUSIVE, or TARIFF
- Returns dict, e.g.: `{"ams_china_japan": "INCLUSIVE", "rds_red_sea": 500.0}`

#### NLP Pass 3 — Rate grid extraction (rule-based)

`_detect_header_row(table)`:
- Scans every row of a table for a row where most cells match `_RATE_COL`
- Uses `_normalize_header()` to strip spaces/punctuation before lookup

`_RATE_COL` dictionary — maps normalized column header → field name:
```python
# Destinations
"destination" → "destination_city"
"dest" → "destination_city"
"pod" → "destination_city"
"port of discharge" → "destination_city"
"portname" → "destination_city"
"point" → "destination_city"  # arbitraries
# Via
"via" → "destination_via_city"
"t/s" → "destination_via_city"
# Container sizes
"20'" → "base_rate_20"
"40'" → "base_rate_40"
"40hc" → "base_rate_40h"
"40'hc" → "base_rate_40h"
"45'" → "base_rate_45"
# Surcharges (when in rate table columns)
"ams" → "ams_china_japan"
"hea" → "hea_heavy_surcharge"
"agw" → "agw"
"rds" → "rds_red_sea"
# Ignore entirely
"country" → "_ignore"
"cntry" → "_ignore"
"cur" → "_ignore"
"currency" → "_ignore"
"direct call" → "remarks"
```

`_extract_from_grid(table, header_map)`:
- Iterates data rows below header, maps each cell to its field
- Uses `_NUMERIC_RE` to parse rate values

**Critical fix — commodity-coded rates (`_NUMERIC_RE`):**
```python
# Handles "R2/2298", "A1/450", plain "360"
_NUMERIC_RE = re.compile(r"(?:[A-Za-z]\d*/)?(\d[\d,]*(?:\.\d+)?)")
# All matches use .group(1) — skips the "R2/" prefix
```

**Container codes in PDF cells:**
| Code | Meaning |
|---|---|
| D2 | 20' Dry |
| D4 | 40' Dry |
| D5 | 40'HC |
| D7 | 45'HC |
| R5 | 40' Reefer |
| `R5/675` in a cell | Reefer rate override = $675 |

**Text pre-filtering (`_prefilter_text`):**
Strips blank lines and separator lines (`---`, `===`, `***`) before processing.
Reduces token-equivalent noise by ~30–50%.

**Parallel execution:**
All section tasks run concurrently via `ThreadPoolExecutor`. Since NLP is all CPU-bound regex (microseconds), the thread pool adds concurrency for I/O at the FastAPI layer, not because extraction itself is slow.

---

### `backend/mapping/normalizer.py`
Port name normalization pipeline.

**`normalize_port(name: str) -> str`** — 7-step chain:
1. Direct lookup in `PORT_MAP` (uppercase key → canonical name)
2. Strip trailing 2-letter country code: `DALIAN CN` → `DALIAN`, retry
3. Strip `CITY` / `PORT` / `TERMINAL` suffix, retry
4. Apply both strips simultaneously, retry
5. First word only (before space), retry
6. Partial match — longest key that the input starts with (sorted longest-first to avoid `BEACH` matching before `LONG BEACH`)
7. Title-case fallback (last resort)

**Coverage:** 300+ port name variants mapped to canonical names. Includes:
- North America (all major US/Canada ports)
- China (all major port name variants + province suffixes)
- Taiwan (city vs port vs city-port variants)
- Japan, Korea
- Southeast Asia (Vietnam, Thailand, Malaysia, Indonesia, Philippines, Myanmar, Cambodia)
- South Asia (India, Pakistan, Bangladesh, Sri Lanka)
- Middle East (UAE, Saudi Arabia, Oman, Iran)
- Africa (East/West/South)
- Europe (major hubs)

---

### `backend/mapping/field_mapper.py`
Maps raw extracted dicts to typed dataclasses.

**Key functions:**
- `map_rates(raw_rows, metadata, surcharges)` → `list[RateRow]`
- `map_origin_arbs(raw_rows, metadata)` → `list[OriginArbitraryRow]`
- `map_dest_arbs(raw_rows, metadata)` → `list[DestinationArbitraryRow]`
- `deduplicate(rows)` → removes rows with identical `(origin, dest, service, rates)` tuples
- `validate_rate(field, value)` → returns `None` if value is outside reasonable bounds

**Rate validation bounds:**
```python
RATE_BOUNDS = {
    "base_rate_20":       (50, 25000),
    "base_rate_40":       (50, 35000),
    "base_rate_40h":      (50, 38000),
    "base_rate_45":       (50, 40000),
    "ams_china_japan":    (10, 500),
    "hea_heavy_surcharge": (0, 2000),
    "agw":                (0, 3000),
    "rds_red_sea":        (0, 5000),
}
```

---

### `backend/mapping/schema.py`
Typed dataclasses for extraction output.

**`RateRow`** (Sheet 1 — 20 fields):
```python
carrier, contract_id, effective_date, expiration_date,
commodity, origin_city, origin_via_city, destination_city, destination_via_city,
service, remarks, scope,
base_rate_20, base_rate_40, base_rate_40h, base_rate_45,
ams_china_japan, hea_heavy_surcharge, agw, rds_red_sea
```

**`OriginArbitraryRow`** (Sheet 2 — 17 fields):
```python
carrier, contract_id, effective_date, expiration_date,
commodity, origin_city, origin_via_city,
service, remarks, scope,
base_rate_20, base_rate_40, base_rate_40h, base_rate_45,
agw_20, agw_40, agw_45
```

**`DestinationArbitraryRow`** (Sheet 3 — 14 fields):
```python
carrier, contract_id, effective_date, expiration_date,
commodity, destination_city, destination_via_city,
service, remarks, scope,
base_rate_20, base_rate_40, base_rate_40h, base_rate_45
```

---

### `backend/excel/excel_writer.py`
Writes extraction output into the `.xlsm` Excel template.

**`write_excel(structured, template_path, output_path)`:**
- Loads template with `openpyxl.load_workbook(keep_vba=True)`
- Writes each dataclass field to its column letter per sheet
- Converts date strings to Excel serial numbers (days since 1899-12-30)
- Does NOT overwrite existing VBA macros

**Excel column layout — Sheet 1 (Rates):**
```
A  carrier           B  contract_id        C  effective_date     D  expiration_date
E  commodity         F  origin_city        G  origin_via_city    H  destination_city
I  dest_via_city     J  service            K  remarks            L  scope
M  base_rate_20      N  base_rate_40       O  base_rate_40h      P  base_rate_45
Q  ams_china_japan   R  hea_heavy          S  agw                T  rds_red_sea
```

**Excel column layout — Sheet 2 (Origin Arbitraries):**
```
A–E  same header fields   F  origin_city   G  origin_via_city
H  service   I  remarks   J  scope   K–N  base_rate_20/40/40h/45
O  agw_20   P  agw_40   Q  agw_45
```

**Excel column layout — Sheet 3 (Destination Arbitraries):**
```
A–E  same header fields   F  destination_city   G  destination_via_city
H  service   I  remarks   J  scope   K–N  base_rate_20/40/40h/45
```

---

### `frontend/src/components/ProgressPanel.jsx`
Live progress display.

**6 pipeline stages:**
```
Upload → PDF Parse → Extracting → NLP Processing → Write Excel → Complete
```

**Features:**
- Live elapsed timer (updates every second)
- Real-time ETA (shown once enough data is collected)
- Engine badge — shows "Docling" or "pdfplumber" depending on which path ran
- Total time shown in green when complete
- Error display with raw message if pipeline fails

---

## 6. Excel Template Structure

Template file: `ATL0347N25 Template.xlsm`

Contains VBA macros that must be preserved — this is why `keep_vba=True` is used in openpyxl. Never save this file as `.xlsx` (that strips VBA).

The template has 3 sheets:
- **Sheet 1:** Rate table (trunk rates per origin-destination pair)
- **Sheet 2:** Origin Arbitraries (inland charges at origin)
- **Sheet 3:** Destination Arbitraries (inland charges at destination)

---

## 7. PDF Format Conventions Supported

### Rate table headers the system recognizes:
The `_RATE_COL` dictionary handles all these and more:
- `Destination`, `Dest`, `POD`, `Port of Discharge`, `Point`
- `Via`, `Dest Via`, `T/S`, `Transshipment`
- `20'`, `20' GP`, `20DV`, `TEU`, `20FT`
- `40'`, `40' GP`, `40DV`, `FEU`
- `40HC`, `40'HC`, `40HQ`, `40'HQ`, `HQ`, `HC`
- `45'`, `45HC`
- `Service`, `Term`, `Type`, `Mode`
- `Remarks`, `Note`, `Notes`, `Direct Call`
- `Cntry`, `Country`, `Cur`, `Currency` → ignored (mapped to `_ignore`)

### Rate value formats:
- Plain numbers: `2500`, `2,500`, `2500.00`
- Commodity-coded: `R2/2298` → extracts `2298`
- Special values: `INCLUSIVE`, `INCL.`, `TARIFF`, `AS PER TARIFF` → stored as strings

### Origin header formats:
- `ORIGIN : LOS ANGELES, CA, UNITED STATES(CY)` → cleaned to `LOS ANGELES`
- `ORIGIN VIA : SEATTLE` → stored as via city
- `[NORTH AMERICA - ASIA (WB)]` → stored as scope/trade lane

### Surcharge block formats:
- `AMS : USD 35 per BL` → `{"ams_china_japan": 35.0}`
- `HEA : INCLUSIVE` → `{"hea_heavy_surcharge": "INCLUSIVE"}`
- `RDS AS PER TARIFF` → `{"rds_red_sea": "TARIFF"}`

---

## 8. Performance Profile

| Stage | Time |
|---|---|
| PDF parsing (pdfplumber) | < 2 seconds |
| NLP extraction (all sections) | < 1 second |
| Excel write | 1–2 seconds |
| **Total — 100-page contract** | **under 10 seconds** |

Processing time is hardware-independent. No model runs, no GPU needed, no RAM pressure.

---

## 9. Known Issues & Bugs

| Issue | Location | Severity | Status |
|---|---|---|---|
| **Grouped origins bug** | `pdf_extractor.py` `_split_sections_from_elements()` | Critical | Open |
| Origin arb `RATE APPLICABLE OVER` header not detected | `pdf_extractor.py` | High | Open |
| Per-commodity validity dates not extracted | `pdf_extractor.py` | Medium | Open |
| Port coverage gaps (regional variants) | `normalizer.py` | Low | Ongoing |
| No unit/integration tests | — | Medium | Open |
| Single in-memory job store (no concurrent users) | `main.py` | Low | Open |

### Grouped origins bug (details)
When a PDF has:
```
ORIGIN : CHICAGO → VIA LOS ANGELES
ORIGIN : DALLAS → VIA LOS ANGELES
ORIGIN : HOUSTON → VIA HOUSTON
[shared rate table here]
```
The current code calls `flush_section()` each time a new `ORIGIN:` is seen.
Since there's no content yet (the table comes after all headers), the flush has nothing to write, and each new ORIGIN overwrites `current_origin`. Only the last origin (`HOUSTON`) ends up with a section containing the table.

**Fix (designed, not yet implemented):**
1. Add `pending_origins: list[tuple[str, str]]` buffer
2. When new `ORIGIN:` seen with no content yet → push to `pending_origins` instead of flushing
3. When `flush_section()` is finally called with content → emit one section per pending origin, all sharing the same tables/text

---

## 10. API Reference

### Health check
```
GET /api/health
→ { "status": "ok", "mode": "nlp", "ollama_running": false, "template_exists": true }
```

### Upload PDFs
```
POST /api/upload
Body: multipart/form-data, field name "files", one or more .pdf files
→ { "jobs": [{ "job_id": "uuid", "filename": "contract.pdf" }, ...] }
```

### Start processing
```
POST /api/process/{job_id}
→ { "message": "Processing started", "job_id": "uuid" }
```

### Get job status
```
GET /api/status/{job_id}
→ full job dict (see section 5 main.py)
```

### Preview results
```
GET /api/preview/{job_id}
→ { "rows": [ ...up to 100 RateRow dicts... ] }
```

### Download Excel
```
GET /api/download/{job_id}
→ binary stream, Content-Type: application/vnd.ms-excel.sheet.macroenabled.12
→ filename: {original_name}_extracted.xlsm
```

### WebSocket progress
```
WS /ws/progress/{job_id}
→ pushes full job dict JSON on every state change
→ closes automatically on COMPLETE or ERROR
```

---

## 11. Setup & Run (Quick Reference)

### Requirements
- Python 3.10+
- Node.js 18+
- No Ollama. No GPU. No internet.

### Install
```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### Run
```bash
# Terminal 1
cd backend
python -m uvicorn main:app --port 8000 --reload

# Terminal 2
cd frontend
npm run dev
```

Open **http://localhost:5173**

### Verify backend
```
http://localhost:8000/api/health
→ {"status":"ok","mode":"nlp"}
```

### Optional: scanned PDF support
Install Docling + EasyOCR (adds PyTorch, ~1.5 GB):
```bash
pip install docling easyocr
```
Only needed for scanned/image PDFs. Minimum 8 GB RAM.

---

## 12. Dependency List

### Core (always required)
```
fastapi
uvicorn[standard]
pdfplumber
openpyxl
aiofiles
httpx
pydantic-settings
python-multipart
```

### Optional (scanned PDFs only)
```
docling>=2.0.0
easyocr>=1.7.0
```

---

## 13. Historical Decision Log

| Decision | Reason |
|---|---|
| **Switched from LLM to pure NLP** | NLP (regex) is 1000–10000× faster (microseconds vs 5–120 sec per call), deterministic, works offline without Ollama, and covers 80–95%+ of standard freight PDF layouts |
| **pdfplumber as primary parser** | pdfplumber extracts structured table grids natively in <2 sec; Docling (previous primary) needed 10–30 sec startup and loaded PyTorch unnecessarily for text-based PDFs |
| **Docling retained as fallback** | Docling's TableFormer model handles merged cells and scanned pages that pdfplumber misses entirely |
| **Rule-based grid extraction** | After pdfplumber gives structured grids, regex + `_RATE_COL` mapping handles column detection deterministically without needing an LLM |
| **NLP-first surcharge/metadata** | Surcharges and contract metadata follow fixed patterns; regex extracts them in zero LLM calls |
| **Single ThreadPoolExecutor** | Running all tasks (metadata + surcharges + all rate sections + all arb sections) in one shared pool maximizes CPU utilization |
| **openpyxl with `keep_vba=True`** | The template contains VBA macros that must survive the write; openpyxl in VBA-safe mode preserves them |
| **`.xlsm` output format** | Required to preserve VBA macros; `.xlsx` strips them |
| **Temperature 0.0 (legacy)** | When LLM was used: deterministic output, no sampling randomness, faster inference |
| **In-memory job store** | Simple for hackathon scope; not suitable for concurrent multi-user production |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Trunk rate** | The main ocean freight rate between origin and destination ports |
| **Origin arbitrary** | Inland/port charge applied at the origin before the trunk leg |
| **Destination arbitrary** | Inland/port charge applied at the destination after the trunk leg |
| **AMS** | Advance Manifest Surcharge (China/Japan trade) |
| **HEA** | Heavy Lift / Heavy Equipment surcharge |
| **AGW** | Arbitrary Gross Weight surcharge |
| **RDS** | Red Sea Surcharge |
| **CY/CY** | Container Yard to Container Yard — standard door-to-door service term |
| **CFS** | Container Freight Station — LCL (less-than-container) service |
| **FCL** | Full Container Load |
| **TEU** | Twenty-foot Equivalent Unit (= 20' container) |
| **FEU** | Forty-foot Equivalent Unit (= 40' container) |
| **D2** | Container code: 20' Dry |
| **D4** | Container code: 40' Dry |
| **D5** | Container code: 40'HC |
| **D7** | Container code: 45'HC |
| **R5** | Container code: 40' Reefer |
| **R5/675** | Reefer rate override cell: commodity code R5, rate = $675 |
| **INCLUSIVE** | Surcharge is included in the base rate (no separate charge) |
| **TARIFF** | Surcharge is billed as per the carrier's published tariff |
| **SHA-256 cache** | Docling results cached on disk keyed by PDF hash — skips re-parsing same file |
| **Trade lane** | Overall route grouping, e.g. `NORTH AMERICA - ASIA (WB)` |
| **WB / SB / EB** | Westbound / Southbound / Eastbound — trade direction |
| **OLTK** | Carrier code for Oltek (example carrier in ATL0347N25) |
| **xlsm** | Excel macro-enabled workbook format (.xlsx + VBA) |
| **pdfplumber** | Python library for extracting text and table grids from PDFs |
| **Docling** | IBM's document AI library with TableFormer table structure model |
| **EasyOCR** | OCR library used by Docling for scanned page text recognition |
| **openpyxl** | Python library for reading/writing Excel files |
| **Pydantic** | Python data validation library — used for settings and schemas |
| **Uvicorn** | ASGI server that runs the FastAPI backend |
| **Vite** | Frontend build tool / dev server for the React UI |
