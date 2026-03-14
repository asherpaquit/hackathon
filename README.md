# FreightScan AI

Turn any freight contract PDF into a filled Excel spreadsheet — **automatically, locally, and for free.**
No internet connection needed. No API keys. The AI runs entirely on your own computer.

---

## What does this do?

You drop in a shipping contract PDF. The app reads every rate table, surcharge, origin/destination arbitrary,
and contract header — then fills them all into your Excel template automatically.

What used to take hours of manual data entry takes **20–30 minutes** on a modern laptop.

---

## Before you start — what you need to install

You need four things installed on your computer before this app will work.
Install them in order.

---

### 1. Python 3.10 or newer

Python is the programming language the backend runs on.

**Download:** https://www.python.org/downloads/

> **Windows users:** During installation, check the box that says **"Add Python to PATH"**.
> If you miss this, commands like `pip` will not work.

To verify it installed correctly, open a terminal and run:
```
python --version
```
You should see something like `Python 3.11.4`.

---

### 2. Node.js 18 or newer

Node.js runs the frontend (the website you interact with in your browser).

**Download:** https://nodejs.org (click the "LTS" version)

To verify:
```
node --version
```
You should see something like `v20.11.0`.

---

### 3. Ollama

Ollama is the program that runs the AI model on your computer.
Think of it like a local version of ChatGPT that never leaves your machine.

**Download:** https://ollama.com

Install it, then open a terminal and run this to download the AI model:
```
ollama pull mistral:7b
```

This downloads about **4.4 GB** — it only needs to happen once.
After that, Ollama runs silently in the background every time you start your computer.

> **Want better speed?** Use this smaller, faster model instead (still very accurate):
> ```
> ollama pull llama3.2:3b
> ```
> Then set `OLLAMA_MODEL=llama3.2:3b` in your `.env` file (explained below).

---

### 4. Tesseract OCR (Windows only — skip on Mac/Linux)

Tesseract lets the app read PDFs that are scanned images instead of real text.

**Download:** https://github.com/UB-Mannheim/tesseract/wiki

During installation, note the folder it installs to (usually `C:\Program Files\Tesseract-OCR`).
You may need to add that folder to your Windows PATH — search "Environment Variables" in the Start menu if needed.

---

## How to set up the project

### Step 1 — Download the project

If you have Git installed:
```bash
git clone <repo-url>
cd hackathon
```

Or download the ZIP from GitHub and extract it somewhere on your computer.

---

### Step 2 — Install Python packages

Open a terminal **inside the `backend` folder** and run:

```bash
cd backend
pip install -r requirements.txt
```

This installs everything the backend needs, including **Docling** (the PDF table parser)
and **EasyOCR** (for scanned pages).

> **First-time note:** Docling will download its AI model weights (~500 MB) the first time
> you process a PDF. This is a one-time download.

---

### Step 3 — Create your settings file

In the **root of the project** (not inside `backend`), create a file called `.env`.
You can do this in Notepad or any text editor.

Paste this into it:

```
OLLAMA_MODEL=mistral:7b
OLLAMA_HOST=http://localhost:11434
```

Save the file. That's it — these are your configuration settings.

> If you chose `llama3.2:3b` earlier, change `mistral:7b` to `llama3.2:3b` here.

---

### Step 4 — Install frontend packages

Open a terminal **inside the `frontend` folder** and run:

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

You should see output ending with something like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

To check everything is working, open this in your browser:
```
http://localhost:8000/api/health
```
You should see `"ollama_running": true`. If it says `false`, make sure Ollama is running
(open the Ollama app or run `ollama serve` in another terminal).

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
   - **PDF Parse** — Docling reads and structures the tables (first run only; cached after)
   - **Extracting** — sections are identified and separated
   - **AI Analysis** — the AI extracts rate rows (most are handled without AI, using rules)
   - **Write Excel** — results are filled into your template
3. When it finishes, click **Download** to get your `.xlsm` Excel file

---

## How long does it take?

These are estimates for a typical 50–100 page freight contract:

| Computer | First run | Repeat runs (cached) |
|---|---|---|
| M5 MacBook Pro | ~20–30 min | ~15–20 min |
| Modern PC (Intel i7 / Ryzen 7, 16 GB RAM) | ~45–90 min | ~30–60 min |
| Older PC (Ryzen 3, 8 GB RAM) | ~2–4 hours | ~1–2 hours |

**Why is the first run slower?**
The app uses Docling to deeply parse the PDF's table structure the first time.
The result is saved to disk — the next time you process the same PDF, it skips
that step entirely and goes straight to extraction.

**Low-spec computer tips:**
- Use `llama3.2:3b` instead of `mistral:7b` — it's 3× faster and uses half the RAM
- If you only have 8 GB RAM, `mistral:7b` may crash the computer — use `llama3.2:3b`
- Set `OLLAMA_MODEL=llama3.2:3b` in your `.env` file

---

## Folder structure

```
hackathon/
├── backend/                  ← Python server (FastAPI)
│   ├── main.py               ← App entry point & API routes
│   ├── config.py             ← Settings (reads from .env)
│   ├── requirements.txt      ← Python package list
│   ├── extraction/
│   │   └── pdf_extractor.py  ← Docling PDF parser (with pdfplumber fallback)
│   ├── ai/
│   │   ├── ollama_extractor.py ← Hybrid rule-based + LLM extraction
│   │   └── prompts.py          ← Prompt templates for the AI
│   ├── mapping/
│   │   ├── field_mapper.py   ← Maps extracted data to Excel columns
│   │   ├── normalizer.py     ← Port/city name normalization
│   │   └── schema.py         ← Data row definitions
│   └── excel/
│       └── excel_writer.py   ← Writes data into the XLSM template
├── frontend/                 ← React web interface
│   └── src/
│       └── components/
│           └── ProgressPanel.jsx ← Progress bar with live ETA
├── .env                      ← Your settings (you create this)
├── README.md                 ← This file
├── PERFORMANCE_UPDATES.md    ← Speed optimization notes
└── DOCLING_UPDATE.md         ← Docling integration notes
```

---

## Common problems

**"ollama_running: false" in the health check**
Ollama isn't running. Open the Ollama desktop app, or run `ollama serve` in a terminal.

**"pip is not recognized"**
Python wasn't added to PATH during installation. Re-install Python and check
"Add Python to PATH" on the first screen.

**"npm is not recognized"**
Node.js isn't installed. Download it from https://nodejs.org.

**The app crashes or says "out of memory"**
Your computer doesn't have enough RAM for `mistral:7b`. Switch to `llama3.2:3b`:
1. Run `ollama pull llama3.2:3b`
2. Edit `.env` and change `OLLAMA_MODEL=mistral:7b` to `OLLAMA_MODEL=llama3.2:3b`
3. Restart the backend

**Processing finished but the Excel file looks empty or wrong**
- The PDF might use an unusual layout — check the terminal output for warnings

**Port 8000 is already in use**
Another program is using that port. Change the backend port:
```bash
python -m uvicorn main:app --port 8001 --reload
```
Then also update the frontend proxy in `frontend/vite.config.js` to point to port 8001.

---

## Important notes

- Ollama must be running **before** you start the backend
- The `.env` file must be in the **root** folder (same level as `backend/` and `frontend/`), not inside `backend/`
- Tested on Windows 10/11 and macOS. Linux should work with the same steps.
