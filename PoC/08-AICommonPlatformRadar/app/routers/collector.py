from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.collector import run_collection


router = APIRouter()


@router.post("/api/collect/run")
async def collect_run(
    lookback_days: int | None = Query(default=None, ge=1, le=31),
    analyze: bool = True,
    db: Session = Depends(get_db),
):
    return await run_collection(db, lookback_days, analyze=analyze)

