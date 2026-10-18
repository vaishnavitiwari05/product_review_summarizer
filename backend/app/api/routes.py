"""HTTP endpoints. Routes stay thin: validation, calling services, shaping responses."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.services import analysis_service as svc
from app.services import repository as repo
from app.services.cleaning import clean_dataframe
from app.services.ingestion import ingest_bytes, list_products as _summarise
from app.utils import config
from app.utils.database import get_db
from app.utils.errors import DataValidationError
from app.utils.serialization import jsonable

router = APIRouter()
_CHUNK = 1024 * 1024


class AnalyzeRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)


def _read_limited(file: UploadFile) -> bytes:
    limit = config.settings.max_upload_mb * 1024 * 1024
    buf = bytearray()
    while chunk := file.file.read(_CHUNK):
        buf += chunk
        if len(buf) > limit:
            raise DataValidationError(
                "file_too_large", f"The file is larger than the {config.settings.max_upload_mb} MB limit.",
                status_code=413)
    return bytes(buf)


def _ingest_and_store(raw: bytes, filename: str, db: Session) -> dict:
    ing = ingest_bytes(raw, filename)
    raw_counts = {str(k): int(v) for k, v in ing.df.groupby("product_id").size().items()}
    cleaned = clean_dataframe(ing.df)
    up = repo.save_upload(db, filename, ing.report, cleaned.stats, raw_counts, cleaned.df)
    return jsonable({
        "upload_id": up.id, "filename": filename,
        "validation": ing.report.to_dict(), "cleaning": cleaned.stats.to_dict(),
        "uploaded_product_ids": [str(p) for p in cleaned.df["product_id"].unique()],   # products in THIS file
        "products": repo.list_products(db),                                            # every stored product
    })


@router.post("/upload")
def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a CSV: validate, clean, de-duplicate and store its reviews."""
    return _ingest_and_store(_read_limited(file), file.filename or "", db)


@router.post("/sample")
def load_sample(db: Session = Depends(get_db)):
    """Load the bundled demo dataset (so the app works with no external data)."""
    path = Path(config.settings.sample_data_path)
    if not path.exists():
        raise DataValidationError("sample_missing", "The sample dataset file was not found on the server.",
                                  status_code=404)
    return _ingest_and_store(path.read_bytes(), path.name, db)


@router.get("/products")
def products(db: Session = Depends(get_db)):
    return {"products": repo.list_products(db)}


@router.post("/analyze", status_code=202)
def analyze(req: AnalyzeRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Start an analysis run in the background. Poll GET /analyze/{run_id} for progress."""
    if db.get(repo.Product, req.product_id) is None:
        raise DataValidationError("product_not_found", f"Unknown product '{req.product_id}'.", status_code=404)
    svc.preflight()
    existing = repo.active_run(db, req.product_id)
    if existing:                                          # already running: reuse it
        return JSONResponse(repo.run_dict(existing), status_code=202)
    run = repo.create_run(db, svc.new_run_id(), req.product_id)
    background.add_task(svc.run_analysis, run.id, req.product_id)
    return JSONResponse(repo.run_dict(run), status_code=202)


@router.get("/analyze/{run_id}")
def analysis_status(run_id: str, db: Session = Depends(get_db)):
    run = db.get(repo.AnalysisRun, run_id)
    if run is None:
        raise DataValidationError("run_not_found", "Unknown analysis run.", status_code=404)
    return repo.run_dict(run)


@router.get("/results/{product_id}")
def results(product_id: str, db: Session = Depends(get_db)):
    return repo.get_results(db, product_id)
