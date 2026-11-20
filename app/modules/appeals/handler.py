from typing import Annotated, Literal

from fastapi import APIRouter, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.manifest import canonical
from app.modules.appeals.service import appeal_balances, export_evidence
from app.modules.appeals.transitions import next_event

router = APIRouter(prefix='/api/appeals')
RunId = Annotated[str, Path(pattern=r'^[0-9a-f]{64}$')]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class AppealInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: Annotated[str, Field(pattern=r'^[A-Z0-9][A-Z0-9_-]{0,31}:[A-Z0-9][A-Z0-9_-]{0,31}$')]
    request_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')]
    expected_version: Annotated[int, Field(ge=0, le=2)]
    action: Literal['OPEN', 'UPHELD', 'WAIVED', 'REDUCED']
    actor: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    note: Text
    evidence_ref: Text
    reduction_cents: Annotated[int | None, Field(ge=0, le=1_000_000)] = None


@router.get('/{run_id}')
def inspect(request: Request, run_id: RunId):
    return appeal_balances(request.app.state.store.get(run_id))


@router.post('/{run_id}/events')
def event(request: Request, run_id: RunId, form: AppealInput):
    result, reused = request.app.state.store.append_event(run_id, form.model_dump(), next_event)
    return {'event': result, 'reused': reused}


@router.get('/{run_id}/export')
def export(request: Request, run_id: RunId):
    snapshot = request.app.state.store.get(run_id)
    return Response(canonical(export_evidence(snapshot)) + '\n', media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="shelf-audit-{run_id[:12]}.json"'})
