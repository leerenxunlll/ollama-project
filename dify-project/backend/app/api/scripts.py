"""HTTP endpoints for creating and reading script metadata."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Script
from app.schemas.script import ScriptCreate, ScriptRead

router = APIRouter()


@router.post("/scripts", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
def create_script(
    payload: ScriptCreate,
    db: Session = Depends(get_db),
) -> Script:
    """Create a draft script with metadata only."""
    script = Script(**payload.model_dump())
    db.add(script)
    db.commit()
    db.refresh(script)
    return script


@router.get("/scripts", response_model=list[ScriptRead])
def list_scripts(db: Session = Depends(get_db)) -> list[Script]:
    """List script metadata, newest first."""
    return list(db.scalars(select(Script).order_by(Script.created_at.desc())).all())


@router.get("/scripts/{script_id}", response_model=ScriptRead)
def get_script(script_id: int, db: Session = Depends(get_db)) -> Script:
    """Read script metadata without loading private character information."""
    script = db.get(Script, script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="Script not found")
    return script
