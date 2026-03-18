# FreightScan AI — Project Overview

> **Hackathon Project** | Built for speed, accuracy, and reliability
> **Status:** Active development — targeting win

---

## What It Does

FreightScan AI converts freight contract PDFs into structured Excel files — automatically.

A freight operations team typically spends **hours manually copying** shipping rates, surcharges, and arbitrary charges from 50–200 page PDF contracts into Excel. FreightScan AI does it in **under 5 minutes**, 100% locally, with no internet or API keys required.

**Input:** Any freight contract PDF (text-based or scanned)
**Output:** Populated Excel workbook (`ATL0347N25.xlsm`) with rates, origin arbitraries, and destination arbitraries — VBA macros preserved

---

## Core Features

| Feature | Description |
|---|---|
| Drag-and-drop upload | Simple browser UI, no setup needed per run |
| Real-time progress | 6-stage progress bar with live ETA |
| Hybrid PDF extraction | pdfplumber (fast) → Docling (fallback for scanned PDFs) |
| Rule-based + LLM extraction | 80–95% of data extracted without any LLM call |
| Port normalization | 300+ port name variants mapped to canonical names |
| Surcharge detection | AMS, HEA, AGW, RDS auto-extracted |
| Arbitrary charges | Origin and destination arbitraries per contract |
| Excel export | openpyxl writes into existing `.xlsm` template, VBA intact |
| Deduplication | Duplicate rows removed before export |
| Fully local | Runs on Ollama — no cloud, no data leaves the machine |

---

## Tech Stack

### Backend
| Layer | Technology | Purpose |
|---|---|---|
| Web Framework | FastAPI + Uvicorn | Async HTTP API + WebSocket progress |
| PDF Parsing (primary) | pdfplumber | Fast text and table extraction (<2 sec) |
| PDF Parsing (fallback) | Docling 2.0 + EasyOCR | Scanned/image PDFs, cached by SHA-256 |
| AI Inference | Ollama (local) | Runs LLMs 100% offline |
| LLM Options | Mistral 7B, Qwen 2.5 7B/3B, Llama 3.2 3B | Configurable via `.env` |
| Excel Output | openpyxl | Write `.xlsm` with VBA macros preserved |
| Data Validation | Pydantic 2.x | Type-safe settings and schemas |
| Async I/O | aiofiles + httpx | Non-blocking file and HTTP operations |

### Frontend
| Layer | Technology | Purpose |
|---|---|---|
| UI Framework | React + Vite | File upload, progress display, download |
| Real-time | WebSocket | Live progress updates from backend |

### Config
```
OLLAMA_MODEL=mistral:7b         # or qwen2.5:7b, qwen2.5:3b, llama3.2:3b
OLLAMA_HOST=http://localhost:11434
LOW_MEMORY_MODE=false           # true → 2 workers, smaller context (8GB RAM)
```

---

## Architecture & Data Flow

```
┌─────────────┐
│  PDF Upload │  POST /api/upload
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  PDF EXTRACTION                                         │
│  1. pdfplumber (primary) — text + tables, <2 sec       │
│  2. Docling fallback — if <100 chars extracted from PDF │
│     └─ EasyOCR for scanned images                      │
│     └─ SHA-256 cache (skip on repeat runs)             │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  STRUCTURED EXTRACTION (Hybrid Rule-Based + LLM)        │
│                                                         │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │   Metadata   │  │Surcharges│  │  Rate Sections   │  │
│  │  (1 LLM call)│  │(1 LLM   │  │  per origin:     │  │
│  │              │  │ call)    │  │  ├─ Rule-based   │  │
│  └──────────────┘  └──────────┘  │    (80–95%)      │  │
│                                  │  └─ LLM fallback │  │
│  ┌────────────────┐              │    (5–20%)        │  │
│  │ Origin Arbs    │              └──────────────────┘  │
│  │ Dest Arbs      │                                     │
│  └────────────────┘                                     │
│                                                         │
│  All tasks run in parallel (ThreadPoolExecutor)         │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  DATA MAPPING & DEDUPLICATION                           │
│  • Normalize 300+ port name variants                    │
│  • Convert dates → Excel serial numbers                 │
│  • Deduplicate by (origin, dest, service, rates)        │
│  • Filter empty/invalid rows                            │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  EXCEL EXPORT                                           │
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

## Module Breakdown

### `backend/extraction/pdf_extractor.py`
- pdfplumber extraction with dual table strategies (line-based + text-based fallback)
- Docling integration with `TableFormerMode.ACCURATE/FAST`
- Section detection by regex: `ORIGIN:`, `ORIGIN VIA:`, `ARBITRAR`, surcharge keywords
- Origin name cleaning: strips service types `(CY)`, country names, state codes
- SHA-256 Docling cache at `_docling_cache/`

### `backend/ai/ollama_extractor.py`
- Rule-based header detection via `_RATE_COL` dictionary (fuzzy, strips punctuation/spaces)
- Grid extraction with `_NUMERIC_RE` regex — handles commodity codes like `R2/2298`
- LLM fallback via Ollama REST API using persistent `httpx.Client`
- Text pre-filtering removes blanks and separator lines (~30–50% token reduction)
- `ThreadPoolExecutor` parallelizes all extraction tasks simultaneously

### `backend/mapping/normalizer.py`
- 196 hardcoded port name → canonical name mappings
- 7-step normalization pipeline (direct → strip country → strip suffix → first word → partial match → title-case fallback)

### `backend/mapping/field_mapper.py`
- Maps raw extracted dicts to `RateRow`, `OriginArbitraryRow`, `DestinationArbitraryRow` dataclasses
- Applies deduplication and field validation

### `backend/excel/excel_writer.py`
- Loads `.xlsm` template with `keep_vba=True`
- Maps dataclass fields to column letters per sheet
- Converts date strings to Excel serial numbers

### `backend/ai/prompts.py`
- System prompt: strict JSON-only extraction
- Per-task prompts: metadata, rates, surcharges, origin arbs, dest arbs

---

## Performance Profile

| Stage | Typical Time | Notes |
|---|---|---|
| PDF parsing (pdfplumber) | <2 sec | Text-based PDFs |
| PDF parsing (Docling) | 10–30 sec | First run; cached after |
| Metadata extraction | ~5 sec | 1 LLM call |
| Surcharge extraction | ~10 sec | 1 LLM call |
| Rate sections | ~20–60 sec | 80% rule-based, 20% LLM, parallel |
| Origin/Dest arbs | ~10–20 sec | Mostly rule-based |
| Excel write | ~2 sec | Fast openpyxl |
| **Total (typical 100-page PDF)** | **~1–3 min** | Parallel execution |

---

## Excel Output Schema

### Sheet 1: Rates (A–T)
```
A  carrier          B  contract_id       C  effective_date    D  expiration_date
E  commodity        F  origin_city       G  origin_via_city   H  destination_city
I  dest_via_city    J  service           K  remarks           L  scope
M  base_rate_20     N  base_rate_40      O  base_rate_40h     P  base_rate_45
Q  ams_china_japan  R  hea_heavy         S  agw               T  rds_red_sea
```

### Sheet 2: Origin Arbitraries (A–Q)
```
A–E  (same header fields)   F  origin_city   G  origin_via_city
H  service   I  remarks   J  scope   K–N  base_rate_20/40/40h/45
O  agw_20   P  agw_40   Q  agw_45
```

### Sheet 3: Destination Arbitraries (A–N)
```
A–E  (same header fields)   F  destination_city   G  destination_via_city
H  service   I  remarks   J  scope   K–N  base_rate_20/40/40h/45
```

---

## Known Limitations

| Area | Current State |
|---|---|
| Port coverage | ~196 ports; regional variants may be missed |
| Currency | USD only; no multi-currency |
| Rate validation | No range/outlier checks |
| Error recovery | One bad section can interrupt extraction |
| Test coverage | No unit or integration tests |
| Concurrent users | Single in-memory job store |

---

## Quick Start

```bash
# 1. Install Ollama and pull a model
ollama pull mistral:7b

# 2. Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# 3. Frontend
cd frontend
npm install && npm run dev

# 4. Open browser
# http://localhost:5173
```

Configure `.env` at project root:
```
OLLAMA_MODEL=mistral:7b
OLLAMA_HOST=http://localhost:11434
LOW_MEMORY_MODE=false
```
