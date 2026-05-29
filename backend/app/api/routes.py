import logging
import os

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.api.schemas import OptimizeResponse
from app.services.solver_service import run_optimization

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_EXCEL_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}

@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_network(
    file: UploadFile = File(...),
    k_road: float = Form(1.0),
    solve_mode: str = Form("MIP"),
    use_hub_capacity: bool = Form(False),
    use_co2: bool = Form(False),
):
    try:
        if not file.filename or not file.filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail="Please upload an .xlsx Excel file.")

        if file.content_type and file.content_type not in ALLOWED_EXCEL_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Please upload a valid Excel .xlsx file.")

        file_bytes = await file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Excel file is too large. Maximum allowed size is {MAX_UPLOAD_MB} MB.",
            )

        # Run synchronously
        result = run_optimization(
            file_bytes=file_bytes,
            k_road=k_road,
            solve_mode=solve_mode,
            use_hub_capacity=use_hub_capacity,
            use_co2=use_co2,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to run optimization: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run optimization task. Error: {str(e)}"
        )
