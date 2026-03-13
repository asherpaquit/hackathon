# FreightScan AI

PDF freight contract → Excel in seconds, powered by Claude AI.

## Quick Start

### 1. Add your API key

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 2. Start the server

```bash
# Windows
start.bat

# Or manually:
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Open the app

Visit http://localhost:8000 and drag-drop your PDF.

---

## How It Works

```
PDF Upload
   ↓
pdfplumber (text extraction)
   ↓  if scanned
pytesseract / Claude Vision (OCR)
   ↓
Claude AI (claude-opus-4-6)
   → Extracts: Routes, Rates, Surcharges, Arbitraries
   ↓
Port name normalization
   ↓
openpyxl → Populate XLSM template (VBA preserved)
   ↓
Download Excel
```

## What gets extracted

| Sheet | Fields |
|-------|--------|
| **Rates** | Carrier, Contract ID, Dates, Commodity, Origin, Destination, Service, Scope, 20'/40'/40H/45' rates, AMS, HEA, AGW, RDS |
| **Origin Arbitraries** | Same + AGW columns |
| **Destination Arbitraries** | Carrier, Dates, Destination, Via Port, Service, Rates |

## Development

```bash
# Backend (hot reload)
cd backend
python -m uvicorn main:app --reload --port 8000

# Frontend (hot reload)
cd frontend
npm run dev
```

## Requirements

- Python 3.10+
- Node 18+
- Anthropic API key
- Tesseract OCR (optional, for scanned PDFs): https://github.com/UB-Mannheim/tesseract/wiki
