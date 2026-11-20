from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, RULE_VERSION, Settings
from app.errors import AuditError
from app.modules.appeals.handler import router as appeals
from app.modules.coverage.handler import router as coverage
from app.modules.intake.handler import router as intake
from app.modules.penalties.handler import router as penalties
from app.modules.photos.handler import router as photos
from app.modules.plans.handler import router as plans
from app.modules.revisions.handler import router as revisions
from app.modules.settlement.handler import router as settlement
from app.store import Store
from app.web import router as web


def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(application):
        application.state.store.initialize()
        yield

    app = FastAPI(title='门店陈列审计台', version=RULE_VERSION, redoc_url=None, lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.state.store = Store(app.state.settings.database)
    app.mount('/assets', StaticFiles(directory=ROOT / 'app' / 'static'), name='assets')
    for router in (web, intake, plans, photos, coverage, penalties, settlement, appeals, revisions):
        app.include_router(router)

    @app.exception_handler(AuditError)
    def audit_error(request: Request, error: AuditError):
        return JSONResponse(error.payload(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    def invalid_input(request: Request, error: RequestValidationError):
        fields = ['.'.join(map(str, issue['loc'])) for issue in error.errors()]
        return JSONResponse({'detail': {'code': 'INVALID_INPUT', 'message': '参数无效，请核对输入',
                                        'evidence': fields}}, status_code=422)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'rule_version': RULE_VERSION}

    return app


app = create_app()
