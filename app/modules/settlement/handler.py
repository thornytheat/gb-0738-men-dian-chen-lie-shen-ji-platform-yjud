from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from app.config import Options
from app.modules.appeals.service import with_appeals
from app.modules.settlement.service import run_audit
from app.pipeline import Audit

router = APIRouter(prefix='/api/settlement')
RunId = Annotated[str, Path(pattern=r'^[0-9a-f]{64}$')]


@router.get('')
def preview(request: Request, options: Annotated[Options, Query()]):
    return Audit(request.app.state.settings, options).settlement


@router.post('/runs')
def run(request: Request, options: Options):
    snapshot, reused = run_audit(request.app.state.settings, request.app.state.store, options)
    return {'reused': reused, **with_appeals(snapshot)}


@router.get('/runs/{run_id}')
def read_run(request: Request, run_id: RunId):
    return with_appeals(request.app.state.store.get(run_id))
