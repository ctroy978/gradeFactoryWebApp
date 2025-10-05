from __future__ import annotations

import os
from pathlib import Path

from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .job_manager import JobManager


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / 'static'

app = FastAPI(title="GradeFactory Web API", version="0.1.0")
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
manager = JobManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

PIN_CODE = os.getenv("GRADEFACTORY_PIN")


def require_pin(x_gradefactory_pin: Optional[str] = Header(default=None)) -> None:
    if not PIN_CODE:
        return
    if x_gradefactory_pin != PIN_CODE:
        raise HTTPException(status_code=401, detail="Invalid or missing access PIN")


def _require_pdfs(files: List[UploadFile]) -> None:
    for upload in files:
        if not upload.filename or not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported for this endpoint.")


def _require_rubric(upload: UploadFile) -> None:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="A rubric file is required.")
    if not (upload.filename.lower().endswith(".pdf") or upload.filename.lower().endswith(".json")):
        raise HTTPException(status_code=400, detail="Rubric must be a PDF or JSON file.")




@app.get("/")
def index() -> FileResponse:
    index_path = STATIC_DIR / 'index.html'
    if not index_path.exists():
        raise HTTPException(status_code=500, detail='UI assets missing')
    return FileResponse(index_path)


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/jobs")
def list_jobs(_: None = Depends(require_pin)) -> List[dict]:
    snapshots: List[dict] = []
    for record in manager.list_jobs():
        snapshot = manager.snapshot(record.job_id)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


@app.get("/jobs/{job_id}")
def get_job(job_id: str, _: None = Depends(require_pin)) -> dict:
    snapshot = manager.snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str, _: None = Depends(require_pin)) -> dict:
    try:
        manager.delete_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"status": "deleted", "id": job_id}


@app.post("/jobs/process")
async def create_processing_job(
    raw_files: List[UploadFile] = File(..., description="Raw PDF essays to process"),
    name_flag: bool = Form(True),
    _: None = Depends(require_pin),
) -> dict:
    if not raw_files:
        raise HTTPException(status_code=400, detail="At least one PDF must be uploaded.")
    _require_pdfs(raw_files)

    job = manager.create_job("process")
    file_payload = [(upload.filename, await upload.read()) for upload in raw_files]
    manager.write_files(job, file_payload, job.paths.raw_input)
    manager.start_processing_job(job.job_id, name_flag=name_flag)

    for upload in raw_files:
        await upload.close()

    snapshot = manager.snapshot(job.job_id)
    if not snapshot:
        raise HTTPException(status_code=500, detail="Failed to create job snapshot.")
    return snapshot


@app.post("/jobs/grade")
async def create_grading_job(
    processed_files: List[UploadFile] = File(..., description="Processed PDF essays ready for grading"),
    rubric: UploadFile = File(..., description="Rubric file (PDF or JSON)"),
    _: None = Depends(require_pin),
) -> dict:
    if not processed_files:
        raise HTTPException(status_code=400, detail="At least one processed PDF must be uploaded.")
    _require_pdfs(processed_files)
    _require_rubric(rubric)

    job = manager.create_job("grade")
    file_payload = [(upload.filename, await upload.read()) for upload in processed_files]
    manager.write_files(job, file_payload, job.paths.processed)

    rubric_bytes = await rubric.read()
    rubric_path = manager.write_rubric(job, rubric.filename, rubric_bytes)
    manager.start_grading_job(job.job_id, rubric_path=rubric_path)

    for upload in processed_files:
        await upload.close()
    await rubric.close()

    snapshot = manager.snapshot(job.job_id)
    if not snapshot:
        raise HTTPException(status_code=500, detail="Failed to create job snapshot.")
    return snapshot


@app.post("/jobs/full")
async def create_full_pipeline_job(
    raw_files: List[UploadFile] = File(..., description="Raw PDF essays to process and grade"),
    rubric: UploadFile = File(..., description="Rubric file (PDF or JSON)"),
    name_flag: bool = Form(True),
    _: None = Depends(require_pin),
) -> dict:
    if not raw_files:
        raise HTTPException(status_code=400, detail="At least one PDF must be uploaded.")
    _require_pdfs(raw_files)
    _require_rubric(rubric)

    job = manager.create_job("full")
    file_payload = [(upload.filename, await upload.read()) for upload in raw_files]
    manager.write_files(job, file_payload, job.paths.raw_input)

    rubric_bytes = await rubric.read()
    rubric_path = manager.write_rubric(job, rubric.filename, rubric_bytes)
    manager.start_full_pipeline(job.job_id, rubric_path=rubric_path, name_flag=name_flag)

    for upload in raw_files:
        await upload.close()
    await rubric.close()

    snapshot = manager.snapshot(job.job_id)
    if not snapshot:
        raise HTTPException(status_code=500, detail="Failed to create job snapshot.")
    return snapshot


@app.get("/jobs/{job_id}/artifacts/{artifact_path:path}")
def download_artifact(job_id: str, artifact_path: str, _: None = Depends(require_pin)):
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    target_path = (job.paths.root / artifact_path).resolve()
    job_root = job.paths.root.resolve()
    if not str(target_path).startswith(str(job_root)):
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(target_path)


@app.on_event("shutdown")
def shutdown_event() -> None:
    manager.shutdown()
