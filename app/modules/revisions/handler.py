import base64
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.errors import AuditError
from app.manifest import canonical
from app.modules.revisions.service import apply_revision, build_revert, export_revisions, revision_view

router = APIRouter(prefix='/api/revisions')
RunId = Annotated[str, Path(pattern=r'^[0-9a-f]{64}$')]
Number = Annotated[int, Path(ge=1)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Actor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
RequestId = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{8,64}$')]
Key = Annotated[str, Field(pattern=r'^[A-Z0-9][A-Z0-9_-]{0,31}:[A-Z0-9][A-Z0-9_-]{0,31}$')]


class PhotoInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    photo: Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$')]
    file: Annotated[str, Field(min_length=5, max_length=64)]
    captured: Annotated[str, Field(min_length=10, max_length=40)]
    content_base64: Annotated[str, Field(min_length=8, max_length=180_000)]


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['COMPLETE', 'ITEM']
    sku: Annotated[str | None, Field(min_length=1, max_length=48)] = None
    facings: Annotated[int | None, Field(ge=1, le=999)] = None
    price_cents: Annotated[int | None, Field(ge=1, le=10_000_000)] = None

    @model_validator(mode='after')
    def check_kind(self):
        filled = (self.sku, self.facings, self.price_cents)
        if self.kind == 'COMPLETE' and any(value is not None for value in filled):
            raise ValueError('COMPLETE 行不得携带商品字段')
        if self.kind == 'ITEM' and any(value is None for value in filled):
            raise ValueError('ITEM 行须含商品、排面与价签')
        return self


class RevisionItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: Key
    photo: PhotoInput | None = None
    observations: Annotated[list[ObservationInput], Field(min_length=1, max_length=50)]


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: RequestId
    actor: Actor
    note: Text
    items: Annotated[list[RevisionItem], Field(min_length=1, max_length=12)]


class RevertInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: RequestId
    actor: Actor
    note: Text


@router.get('/{run_id}')
def inspect(request: Request, run_id: RunId):
    return {'run_id': run_id, **revision_view(request.app.state.store.get(run_id))}


@router.post('/{run_id}')
def submit(request: Request, run_id: RunId, form: RevisionInput):
    record, reused = request.app.state.store.append_revision(run_id, form.model_dump(), apply_revision)
    if record['status'] == 'FAILED' and not reused:
        error = record['error']
        raise AuditError(error['code'], error['message'],
                         evidence={'revision': record['revision'], 'detail': error['evidence']})
    return {'revision': record, 'reused': reused}


@router.post('/{run_id}/{number}/revert')
def revert(request: Request, run_id: RunId, number: Number, form: RevertInput):
    record, reused = request.app.state.store.revert_revision(run_id, number, form.model_dump(), build_revert)
    return {'revision': record, 'reused': reused}


@router.get('/{run_id}/export')
def export(request: Request, run_id: RunId):
    snapshot = request.app.state.store.get(run_id)
    return Response(canonical(export_revisions(snapshot)) + '\n', media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="shelf-revision-{run_id[:12]}.json"'})


@router.get('/{run_id}/{number}/photos/{photo_id}')
def photo(request: Request, run_id: RunId, number: Number,
          photo_id: Annotated[str, Path(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$')]):
    payload = request.app.state.store.revision_payload(run_id, number)
    for item in payload['items']:
        submitted = item.get('photo')
        if submitted and submitted['photo'].upper() == photo_id.upper():
            content = base64.b64decode(submitted['content_base64'])
            return Response(content, media_type='image/png',
                            headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
    raise AuditError('PHOTO_NOT_FOUND', '该修订中没有此照片', 404)
