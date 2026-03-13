# FreightScan AI

PDF freight contract → Excel, powered by local AI. **No API keys. 100% free.**

---

## Prerequisites

| Tool | Download |
|------|----------|
| Python 3.10+ | https://python.org |
| Node.js 18+ | https://nodejs.org |
| Ollama | https://ollama.com |
| Tesseract OCR *(Windows)* | https://github.com/UB-Mannheim/tesseract/wiki |

Minimum **8 GB free RAM** (the AI model uses ~4.5 GB).

---

## Setup

### 1. Clone

```bash
git clone <repo-url>
cd hackathon
```

### 2. Pull the AI model

```bash
ollama pull mistral:7b
```

~4.4 GB download, done once. Ollama starts automatically on port 11434.

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
OLLAMA_MODEL=mistral:7b
OLLAMA_HOST=http://localhost:11434
```

Start the backend:

```bash
python -m uvicorn main:app --port 8000 --reload
```

Check it's working: open `http://localhost:8000/api/health` — you should see `"ollama_running": true`.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

---

## Usage

1. Drag & drop a freight contract PDF
2. Wait for processing — **a 100-page PDF takes ~5–15 minutes** (runs on CPU, no GPU needed)
3. Download the generated Excel file (`.xlsm`)

---

## Notes

- Ollama must be running before starting the backend
- Do not delete `templates/ATL0347N25 Template.xlsm` — it's required for Excel output
- Tested on Windows; Mac/Linux should work with the same steps
