# Accuracy Update — LAX0079N25 Format Fixes

**Date:** 2026-03-14
**Target PDF:** LAX0079N25 Contract.pdf (186 pages, OLTK carrier)

---

## Problems Found by Analyzing the Real PDF

After reading the actual contract structure with pdfplumber, three critical bugs were found that caused wrong or missing data in the Excel output.

---

## Fix 1 — `R2/2298` Rate Format (Commodity-Coded Rates)

**File:** `backend/ai/ollama_extractor.py`

**Problem:**
Some rate cells in this PDF use a commodity/rate code format:
```
R2/2298    (means: commodity code R2, rate = $2298)
```
The old regex `[\d,]+` would find the first number — which is `2` — producing a completely wrong rate.

**Fix:**
Updated `_NUMERIC_RE` to skip the `X\d/` prefix and capture only the actual rate:
```python
# Before
_NUMERIC_RE = re.compile(r"[\d,]+(?:\.\d+)?")

# After — handles "R2/2298", "A1/450", plain "360", etc.
_NUMERIC_RE = re.compile(r"(?:[A-Za-z]\d*/)?(\d[\d,]*(?:\.\d+)?)")
```
Also updated all `.group()` calls to `.group(1)` to use the capture group.

---

## Fix 2 — ORIGIN Name Cleaning

**File:** `backend/extraction/pdf_extractor.py`

**Problem:**
The LAX PDF writes origin headers like:
```
ORIGIN : LOS ANGELES, CA, UNITED STATES(CY)
```
The old code captured the full string including the state, country, and service type — so the origin stored was `LOS ANGELES, CA, UNITED STATES(CY)` which didn't match any port in the normalizer.

**Fix:**
Added `_clean_origin_name()` function that strips these suffixes in order:
1. Remove trailing service parens: `(CY)`, `(CY/CY)`, `(CFS)`, `(FCL)`, etc.
2. Remove country name: `, UNITED STATES`, `, CHINA`, `, TAIWAN`, etc.
3. Remove 2-letter state/province code: `, CA`, `, TX`, `, BC`, etc.
4. Take city name before any remaining comma

Result: `LOS ANGELES, CA, UNITED STATES(CY)` → **`LOS ANGELES`**

Applied to both `ORIGIN :` and `ORIGIN VIA :` headers.

---

## Fix 3 — Column Handling for LAX Table Headers

**File:** `backend/ai/ollama_extractor.py`

**Problem:**
LAX rate tables have extra columns not in the old `_RATE_COL` map:
```
Destination | Cntry | Destination Via | Cntry | Term | Type | Cur | 20' | 40' | 40HC | 45' | Direct Call | Note
```
- `Cntry` (country code) — was unrecognised, harmless but noisy
- `Cur` (currency) — was unrecognised
- `Direct Call` — was unrecognised

**Fix:**
- `Cntry` and `Cur` → mapped to `"_ignore"` sentinel, explicitly skipped
- `Direct Call` → mapped to `remarks` (carries the flag through for reference)
- Extractor now checks `if field == "_ignore": continue` before processing

---

## Fix 4 — Port Normalizer Expansion

**File:** `backend/mapping/normalizer.py`

### New port name variants added:
| Raw (from PDF) | Canonical |
|---|---|
| `HAI PHONG` | Haiphong |
| `HAIPHONG CITY` | Haiphong |
| `KAOHSIUNG CITY` | Kaohsiung |
| `KAOHSIUNG PORT` | Kaohsiung |
| `KEELUNG CITY` | Keelung (Chilung) |
| `TAICHUNG CITY` | Taichung |
| `TAICHUNG PORT` | Taichung |
| `TAIPEI CITY` | Taipei |
| `TAOYUAN CITY` | Taoyuan |
| `DALIAN, LIAONING` | Dalian |
| `YANTIAN, GUANGDONG` | Yantian |
| `NANSHA, GUANGDONG` | Guangzhou |
| `TIANJIN XINGANG` | Xingang |
| `ZHOUSHAN` | Ningbo |
| `HUANGPU` | Guangzhou |
| `XINSHA` | Guangzhou |

### Smarter matching logic added to `normalize_port()`:
1. Strip trailing 2-letter country code: `DALIAN CN` → `DALIAN`
2. Strip `CITY`/`PORT`/`TERMINAL` suffix before lookup
3. Apply both strips to province-stripped base name
4. Partial match now sorts keys **longest-first** so `LONG BEACH` matches before `BEACH`

---

## Expected Impact

| Issue | Before | After |
|---|---|---|
| Commodity-rate cells like `R2/2298` | Rate = `2.0` ❌ | Rate = `2298.0` ✓ |
| Origin `LOS ANGELES, CA, UNITED STATES(CY)` | Stored as-is, no port match ❌ | `LOS ANGELES` → `Los Angeles` ✓ |
| `HAI PHONG` port | Falls through to title-case | `Haiphong` ✓ |
| `KAOHSIUNG CITY` port | Falls through to title-case | `Kaohsiung` ✓ |
| `Cntry` / `Cur` columns | Silently ignored | Explicitly ignored (cleaner) |

No performance impact — all fixes are regex/dict lookups with zero added latency.
