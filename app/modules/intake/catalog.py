from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.errors import AuditError
from app.modules.intake.clock import utc_timestamp

CODES = ('MISSING_SKU', 'WRONG_SKU', 'UNDER_FACINGS', 'PRICE_MISMATCH')
Code = Annotated[str, Field(pattern=r'^[A-Z0-9][A-Z0-9_-]{0,31}$')]


class Stratum(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: Code
    title: Annotated[str, Field(min_length=1, max_length=24)]
    weight: Annotated[int, Field(ge=1, le=1000)]


class Campaign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: Code
    version: Annotated[str, Field(min_length=1, max_length=32)]
    title: Annotated[str, Field(min_length=1, max_length=40)]
    seed: Annotated[str, Field(min_length=1, max_length=48)]
    start_utc: Annotated[str, Field(min_length=10, max_length=40)]
    end_utc: Annotated[str, Field(min_length=10, max_length=40)]
    sample_size: Annotated[int, Field(ge=1, le=100)]
    max_photo_skew_min: Annotated[int, Field(ge=1, le=360)]
    groups: Annotated[list[Stratum], Field(min_length=1, max_length=12)]
    penalty_cents: dict[Literal['MISSING_SKU', 'WRONG_SKU', 'UNDER_FACINGS', 'PRICE_MISMATCH'],
                        Annotated[int, Field(gt=0, le=1_000_000)]]

    @model_validator(mode='after')
    def validate_rules(self):
        if utc_timestamp(self.start_utc) >= utc_timestamp(self.end_utc):
            raise ValueError('巡检账期开始须早于结束')
        if len({item.code for item in self.groups}) != len(self.groups) or set(self.penalty_cents) != set(CODES):
            raise ValueError('店组重复或规则缺失')
        return self


def load_campaign(raw):
    try:
        model = Campaign.model_validate_json(raw).model_dump()
    except ValidationError as error:
        raise AuditError('BAD_CAMPAIGN', '巡检册规则无效', evidence=[list(e['loc']) for e in error.errors()]) from error
    for key in ('start_utc', 'end_utc'):
        stamp: datetime = utc_timestamp(model[key])
        model[key] = stamp.isoformat()
    return model
