from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import DATASETS, ROOT, RULE_VERSION
from app.reasons import REASONS

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / 'app' / 'templates')
SECTIONS = {'intake': '巡店收件', 'plans': '货架版本', 'photos': '照片证据', 'coverage': '抽样覆盖',
            'penalties': '罚则裁决', 'settlement': '结算勾稽', 'appeals': '异议复核'}


@router.get('/', response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request=request, name='console.html', context={
        'datasets': DATASETS, 'version': RULE_VERSION, 'sections': SECTIONS, 'reasons': REASONS,
    })
