import asyncio
import json
import uuid
from pathlib import Path
from typing import Dict

import aiofiles
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings

app = FastAPI(title="FreightScan AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store
jobs: Dict[str, dict] = {}

# WebSocket connections per job
ws_connections: Dict[str, WebSocket] = {}


def make_job(filename: str, filepath: str) -> dict:
    return {
        "job_id": str(uuid.uuid4()),
        "filename": filename,
        "filepath": filepath,
        "status": "UPLOADED",
        "stage_pct": 0,
        "pages_total": 0,
        "pages_done": 0,
        "rows_extracted": 0,
        "error": None,
        "output_path": None,
        "preview_data": [],
    }


async def broadcast(job_id: str, data: dict):
    jobs[job_id].update(data)
    ws = ws_connections.get(job_id)
    if ws:
        try:
            await ws.send_text(json.dumps(jobs[job_id]))
        except Exception:
            pass


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mode": "nlp",
        "ollama_running": False,
        "template_exists": settings.template_path.exists(),
    }


@app.post("/api/upload")
async def upload_pdfs(files: list[UploadFile] = File(...)):
    created = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"{file.filename} is not a PDF")

        job_id = str(uuid.uuid4())
        save_path = settings.upload_dir / f"{job_id}.pdf"

        async with aiofiles.open(save_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        job = make_job(file.filename, str(save_path))
        job["job_id"] = job_id
        jobs[job_id] = job
        created.append({"job_id": job_id, "filename": file.filename})

    return {"jobs": created}


@app.post("/api/process/{job_id}")
async def process_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    if job["status"] not in ("UPLOADED", "ERROR"):
        return {"message": "Already processing or done"}

    asyncio.create_task(run_pipeline(job_id))
    return {"message": "Processing started", "job_id": job_id}


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/api/preview/{job_id}")
def get_preview(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return {"rows": jobs[job_id].get("preview_data", [])}


@app.get("/api/download/{job_id}")
def download_result(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    if job["status"] != "COMPLETE":
        raise HTTPException(400, "Job not complete yet")

    output = job.get("output_path")
    if not output or not Path(output).exists():
        raise HTTPException(404, "Output file not found")

    filename = Path(job["filename"]).stem + "_extracted.xlsm"
    return FileResponse(
        output,
        media_type="application/vnd.ms-excel.sheet.macroenabled.12",
        filename=filename,
    )


@app.websocket("/ws/progress/{job_id}")
async def ws_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    ws_connections[job_id] = websocket

    if job_id in jobs:
        await websocket.send_text(json.dumps(jobs[job_id]))

    try:
        while True:
            await asyncio.sleep(1)
            if job_id in jobs and jobs[job_id]["status"] in ("COMPLETE", "ERROR"):
                await websocket.send_text(json.dumps(jobs[job_id]))
                break
    except WebSocketDisconnect:
        pass
    finally:
        ws_connections.pop(job_id, None)


async def run_pipeline(job_id: str):
    from extraction.pdf_extractor import extract_pdf
    from ai.ollama_extractor import extract_with_ollama
    from excel.excel_writer import write_excel

    job = jobs[job_id]
    filepath = job["filepath"]

    try:
        await broadcast(job_id, {"status": "PDF_PARSING", "stage_pct": 10,
                                  "message": "Parsing PDF structure…"})

        def do_extract():
            return extract_pdf(filepath)

        loop = asyncio.get_running_loop()
        extracted = await loop.run_in_executor(None, do_extract)

        pages_total = extracted.get("pages_total", 0)
        docling_used = extracted.get("_docling", False)
        await broadcast(job_id, {
            "status": "EXTRACTING_TEXT",
            "stage_pct": 35,
            "pages_total": pages_total,
            "pages_done": pages_total,
            "message": f"{'Docling' if docling_used else 'pdfplumber'} extraction complete",
        })

        # ── Extract contract rules (Sections 7-12) via Ollama LLM ──
        rules = {}
        rules_text = extracted.get("rules_text", "")
        if rules_text.strip():
            await broadcast(job_id, {"status": "EXTRACTING_RULES", "stage_pct": 37,
                                      "message": "Extracting contract rules via LLM…"})
            from ai.rules_extractor import extract_rules, check_ollama_available
            if check_ollama_available(settings.ollama_host):
                rules = await loop.run_in_executor(
                    None,
                    lambda: extract_rules(rules_text, settings.ollama_host, settings.ollama_model)
                )
                await broadcast(job_id, {"status": "EXTRACTING_RULES", "stage_pct": 39,
                                          "message": f"Rules extracted: {len(rules.get('scope_dates', {}))} scopes"})

        await broadcast(job_id, {"status": "NLP_PROCESSING", "stage_pct": 40})

        def do_ai():
            return extract_with_ollama(extracted, rules=rules)

        structured = await loop.run_in_executor(None, do_ai)
        rows_count = (
            len(structured.get("rates", []))
            + len(structured.get("origin_arbitraries", []))
            + len(structured.get("destination_arbitraries", []))
        )
        await broadcast(job_id, {
            "status": "NLP_PROCESSING",
            "stage_pct": 70,
            "rows_extracted": rows_count,
        })

        await broadcast(job_id, {"status": "WRITING_EXCEL", "stage_pct": 85})

        output_path = settings.output_dir / f"{job_id}_result.xlsm"

        def do_write():
            write_excel(structured, str(settings.template_path), str(output_path))

        await loop.run_in_executor(None, do_write)

        preview = structured.get("rates", [])[:100]
        await broadcast(job_id, {
            "status": "COMPLETE",
            "stage_pct": 100,
            "output_path": str(output_path),
            "preview_data": preview,
            "rows_extracted": rows_count,
        })

    except Exception as e:
        import traceback
        await broadcast(job_id, {"status": "ERROR", "error": str(e)})
        print(traceback.format_exc())


# Serve built frontend
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
