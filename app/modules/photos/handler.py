import re
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from fastapi.responses import Response

from app.config import MAX_PHOTO_BYTES, Options
from app.errors import AuditError
from app.modules.intake.service import PHOTO_FILE, read_limited
from app.modules.intake.values import InvalidRow
from app.modules.photos.fingerprints import png_hash
from app.pipeline import Audit

router = APIRouter(prefix='/api/photos')


@router.get('')
def inspect(request: Request, options: Annotated[Options, Query()]):
    return Audit(request.app.state.settings, options).photos


@router.get('/original/{dataset}/{filename}/{digest}')
def original(request: Request, dataset: Literal['field', 'reference'], filename: str, digest: str):
    if not PHOTO_FILE.fullmatch(filename) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise AuditError('PHOTO_NOT_FOUND', '照片原件编号无效', 404)
    folder = request.app.state.settings.sample_root / dataset / 'photos'
    try:
        raw = read_limited(folder / filename, MAX_PHOTO_BYTES)
        actual = png_hash(raw)
    except (AuditError, InvalidRow) as error:
        raise AuditError('PHOTO_NOT_FOUND', '照片原件无法读取', 404) from error
    if actual != digest:
        raise AuditError('PHOTO_CHANGED', '照片原件与批次摘要不同', 409)
    return Response(raw, media_type='image/png', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
