from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union

class OptimizeResponse(BaseModel):
    status: str
    message: Optional[str] = None
    objective_value: float
    co2_total: Optional[float] = None
    metrics: Dict[str, Any]
    results_flow: List[Dict[str, Any]]
    node_balance: Optional[List[Dict[str, Any]]] = None
    network_data: Dict[str, Any]

class JobResponse(BaseModel):
    task_id: str
    status: str
    message: str

class JobStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[OptimizeResponse] = None
    error: Optional[str] = None
