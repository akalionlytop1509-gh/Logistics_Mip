from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from backend.app.api.schemas import OptimizeResponse
from backend.app.services.solver_service import run_optimization

router = APIRouter()

@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_network(
    file: UploadFile = File(...),
    k_road: float = Form(1.0),
    solve_mode: str = Form("MIP"),
    use_hub_capacity: bool = Form(False),
    use_co2: bool = Form(False),
):
    try:
        file_bytes = await file.read()
        result = run_optimization(
            file_bytes=file_bytes,
            k_road=k_road,
            solve_mode=solve_mode,
            use_hub_capacity=use_hub_capacity,
            use_co2=use_co2,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
