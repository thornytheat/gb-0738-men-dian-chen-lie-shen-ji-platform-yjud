import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {'field': '十一月 · 巡店原件', 'reference': '十一月 · 核验副本'}
RULE_VERSION = '2026.11-r1'
TABLES = ('stores', 'slots', 'visits', 'plans', 'aliases', 'photos', 'observations')
MAX_TABLE_BYTES = 512_000
MAX_PHOTO_BYTES = 128_000
MAX_PHOTOS = 256


class Settings:
    def __init__(self, sample_root=None, database=None):
        self.sample_root = Path(sample_root or os.getenv('SHELF_SAMPLE_ROOT', ROOT / 'sample_data'))
        self.database = Path(database or os.getenv('SHELF_DB_PATH', ROOT / 'data' / 'audits.sqlite3'))


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: Literal['field', 'reference'] = 'field'
    sample_size: Annotated[int | None, Field(ge=1, le=100)] = None
