from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.config import Options
from app.pipeline import Audit

router = APIRouter(prefix='/api/intake')


@router.get('')
def inspect(request: Request, options: Annotated[Options, Query()]):
    return Audit(request.app.state.settings, options).intake
