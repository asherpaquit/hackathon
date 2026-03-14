# Docling Integration Update

## What Changed (March 2026)

This update replaces the raw-text PDF extraction pipeline with a hybrid
**Docling + rule-based + LLM** pipeline that is significantly faster and more accurate.

---

## New Pipeline Flow

```
PDF
 │
 ▼
Docling (whole-PDF, TableFormer ACCURATE + EasyOCR)
 │   └─ Disk cache keyed by SHA-256 → instant on repeat runs
 │
 ▼
Section splitter (walks Docling elements in reading order)
 │   Sections now carry structured table grids, not just raw text
 │
 ▼
Hybrid extractor (per section, all parallel)
 │
 ├─ [Has Docling grid with recognized headers?]
 │       YES → rule-based extraction (0 LLM calls, ~0ms)
 │       NO  → LLM fallback (receives grid JSON + raw text)
 │
 ▼
Excel writer (unchanged)
```

---

## Files Changed

| File | Change |
|---|---|
| `backend/extraction/pdf_extractor.py` | Full rewrite — Docling whole-PDF + SHA256 cache + pdfplumber fallback |
| `backend/ai/ollama_extractor.py` | Hybrid extractor: `_extract_from_grid()`, `_detect_header_row()`, `_RATE_COL` map |
| `backend/ai/prompts.py` | RATES_PROMPT updated to accept TABLE GRIDS (JSON) as primary input |
| `backend/main.py` | New `DOCLING_PROCESSING` stage in pipeline + `_docling` flag in broadcast |
| `backend/requirements.txt` | Added `docling>=2.0.0`, `easyocr>=1.7.0` |
| `frontend/src/components/ProgressPanel.jsx` | Accurate stage stepper (6 stages), live elapsed timer, real-time ETA |

---

## Speed & Accuracy Improvements

### Accuracy
- **Merged cells**: Docling's TableFormer ACCURATE mode handles merged cells and
  multi-row headers that pdfplumber missed entirely
- **Column alignment**: grids are already structured — LLM no longer guesses column
  boundaries from character positions in raw text
- **OCR**: EasyOCR replaces Tesseract for scanned pages — significantly better
  on low-resolution or skewed freight contract scans

### Speed

| Stage | Before | After (M5 MacBook Pro) |
|---|---|---|
| PDF extraction | ~1 min (pdfplumber) | ~12 min first run / **instant** (cached) |
| Rate extraction | ~2 hrs (100% LLM) | ~15–20 min (~80% rule-based, 20% LLM) |
| **Total** | **~2 hrs** | **~15–30 min** |

Disk cache means any re-processing of the same PDF skips Docling entirely.

---

## Hardware Estimates

### M5 MacBook Pro (recommended for this project)
- Docling (ACCURATE): ~10–15 min first run (Neural Engine + MPS acceleration)
- Rule-based extraction: ~0s
- LLM fallback sections (with `qwen2.5:7b`): ~10–15 min
- **Total: ~20–30 min**

---

### Ryzen 3 3200G + 8 GB RAM ⚠️

**Short answer: this hardware will struggle. Here's why:**

| Issue | Detail |
|---|---|
| **RAM** | Mistral 7B Q4 needs ~4.5 GB. OS needs ~2 GB. Docling needs ~2–3 GB. **Total ~8.5–9.5 GB → OOM crash or extreme swapping** |
| **CPU speed** | No AVX-512, 4 cores @ 3.6 GHz → ~1–3 tokens/sec for 7B models |
| **No GPU acceleration** | Integrated Vega 8 is not supported by Ollama for inference |
| **Docling on CPU** | TableFormer ACCURATE without a neural engine: ~3–5 min per page |

**Estimated time on Ryzen 3 3200G + 8 GB RAM:**

| Scenario | Estimated Time |
|---|---|
| Mistral 7B + Docling ACCURATE | Likely **OOM crash** |
| `llama3.2:3b` + Docling ACCURATE (first run) | ~4–6 hours (Docling alone ~3 hrs) |
| `llama3.2:3b` + Docling ACCURATE (cached) | ~1.5–2.5 hours (LLM is bottleneck) |
| `llama3.2:3b` + pdfplumber fallback (no Docling) | ~45–90 min |

### Recommendations for low-spec hardware

1. **Switch model** — set `OLLAMA_MODEL=llama3.2:3b` in your `.env`. It fits in
   ~2 GB RAM and is 3–4× faster than Mistral 7B on CPU.

2. **Disable Docling ACCURATE, use FAST mode** — edit `pdf_extractor.py` line:
   ```python
   pipeline_options.table_structure_options.mode = TableFormerMode.FAST
   ```
   FAST mode: ~30s per page instead of 3–5 min. Some merged cell accuracy lost.

3. **Or skip Docling entirely** — if Docling is not installed, the pipeline
   automatically falls back to pdfplumber. Install only:
   ```bash
   pip install -r requirements.txt --ignore-requires-python
   # then uninstall docling
   pip uninstall docling easyocr -y
   ```
   The rule-based extractor won't fire (no structured grids), but the LLM still
   gets the pre-filtered text and the parallel processing remains.

4. **Add more RAM** — 16 GB would make Mistral 7B viable and Docling stable.

---

## Frontend Changes

The progress bar now has **6 accurate stages** matching the actual backend pipeline:

```
Upload → PDF Parse → Extracting → AI Analysis → Write Excel → Complete
```

New features:
- **Live elapsed timer** — shows how long the current job has been running
- **Real-time ETA** — estimated time remaining based on elapsed time + current % (updates every second, shown once enough data is available)
- **Engine badge** — shows "Docling" or "pdfplumber" so you know which path ran
- **Total time** — shown in green when the job completes

---

## Installation

```bash
cd backend
pip install docling easyocr
```

First run downloads Docling's TableFormer model weights (~500 MB) and EasyOCR
language models (~100 MB). Subsequent runs use the local cache.

To pre-warm the cache before a demo:
```bash
python -c "from extraction.pdf_extractor import extract_pdf; extract_pdf('path/to/contract.pdf')"
```
