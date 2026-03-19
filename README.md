# FreightScan AI

Turn any freight contract PDF into a filled Excel spreadsheet — **automatically, locally, and for free.**
No internet connection needed. No API keys. No AI model to download.

---

## What does this do?

You drop in a shipping contract PDF. The app reads every rate table, surcharge, origin/destination arbitrary,
and contract header — then fills them all into your Excel template automatically.

What used to take hours of manual data entry takes **under 5 minutes** on any modern computer.

---

## How it works

FreightScan AI uses pure NLP (natural language processing) — regex patterns and rule-based table parsing.
There is no LLM, no Ollama, no GPU, and no internet required. Everything runs entirely on your machine using
lightweight Python libraries.

---

## Before you start — what you need to install

You only need two things.

---

### 1. Python 3.10 or newer

**Download:** https://www.python.org/downloads/

> **Windows users:** During installation, check the box that says **"Add Python to PATH"**.
> If you miss this, commands like `pip` will not work.

To verify:
```
python --version
```
You should see something like `Python 3.11.4`.

---

### 2. Node.js 18 or newer

Node.js runs the frontend (the browser interface).

**Download:** https://nodejs.org (click the "LTS" version)

To verify:
```
node --version
```
You should see something like `v20.11.0`.

---

## How to set up the project

### Step 1 — Download the project

```bash
git clone <repo-url>
cd hackathon
```

Or download the ZIP from GitHub and extract it somewhere on your computer.

---

### Step 2 — Install Python packages

Open a terminal inside the `backend` folder and run:

```bash
cd backend
pip install -r requirements.txt
```

---

### Step 3 — Install frontend packages

Open a terminal inside the `frontend` folder and run:

```bash
cd frontend
npm install
```

---

## How to run it

You need **two terminals open at the same time** — one for the backend, one for the frontend.

### Terminal 1 — Start the backend

```bash
cd backend
python -m uvicorn main:app --port 8000 --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

To confirm everything is working, open this in your browser:
```
http://localhost:8000/api/health
```
You should see `"status": "ok"` and `"mode": "nlp"`.

---

### Terminal 2 — Start the frontend

```bash
cd frontend
npm run dev
```

You should see:
```
  VITE ready in ...ms
  ➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser. You'll see the FreightScan AI interface.

---

## How to use it

1. **Drag and drop** your freight contract PDF onto the upload area, or click to browse
2. Processing starts automatically — you'll see a progress bar with live stages:
   - **PDF Parse** — pdfplumber reads and structures the tables
   - **NLP Processing** — sections are identified and rate data is extracted using rules
   - **Write Excel** — results are filled into your template
3. When it finishes, click **Download** to get your `.xlsm` Excel file

---

## How long does it take?

| Stage | Time |
|---|---|
| PDF parsing (pdfplumber) | 1–3 seconds |
| NLP extraction (all sections) | under 1 second |
| Excel write | 1–2 seconds |
| **Total for a 100-page contract** | **under 10 seconds** |

Processing time is the same on any computer — there is no AI model running, so RAM and GPU do not affect speed.

---

## Folder structure

```
hackathon/
├── backend/                  ← Python server (FastAPI)
│   ├── main.py               ← App entry point & API routes
│   ├── config.py             ← Settings
│   ├── requirements.txt      ← Python package list
│   ├── extraction/
│   │   └── pdf_extractor.py  ← pdfplumber PDF parser (Docling fallback for scanned PDFs)
│   ├── ai/
│   │   └── ollama_extractor.py ← Pure NLP extraction (regex + rule-based grid parsing)
│   ├── mapping/
│   │   ├── field_mapper.py   ← Maps extracted data to Excel columns
│   │   ├── normalizer.py     ← Port/city name normalization
│   │   └── schema.py         ← Data row definitions
│   └── excel/
│       └── excel_writer.py   ← Writes data into the XLSM template
├── frontend/                 ← React web interface
│   └── src/
│       └── components/
│           └── ProgressPanel.jsx ← Progress bar with live status
├── README.md                 ← This file
└── templates/
    └── ATL0347N25 Template.xlsm ← Excel output template
```

---

## Common problems

**"pip is not recognized"**
Python wasn't added to PATH during installation. Re-install Python and check
"Add Python to PATH" on the first screen.

**"npm is not recognized"**
Node.js isn't installed. Download it from https://nodejs.org.

**Processing finished but the Excel file looks empty or wrong**
The PDF may use an unusual table layout. Check the terminal output for warnings.
Make sure the PDF contains real text (not a scanned image). For scanned PDFs,
install the optional OCR packages listed at the bottom of `requirements.txt`.

**Port 8000 is already in use**
Another program is using that port. Change the backend port:
```bash
python -m uvicorn main:app --port 8001 --reload
```
Then update the frontend proxy in `frontend/vite.config.js` to point to port 8001.

**ModuleNotFoundError on startup**
You haven't installed the Python packages yet. Run `pip install -r requirements.txt`
from inside the `backend` folder.

---

## Optional: scanned PDF support

The app works out of the box for text-based PDFs. If you need to process scanned/image PDFs,
install the optional OCR packages (uncomment the last section of `requirements.txt`):

```
docling>=2.0.0
easyocr>=1.7.0
```

> Note: `docling` installs PyTorch (~1.5 GB) and requires 8 GB RAM minimum.

---

## Important notes

- No Ollama, no GPU, and no internet connection required
- Tested on Windows 10/11 and macOS. Linux should work with the same steps.
- The Excel template (`ATL0347N25 Template.xlsm`) must be present in the `templates/` folder
