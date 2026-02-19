"""
Parse-stage data contract definitions.
"""

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PARSE_SCHEMA_VERSION_V1 = "v1"


class ParseContractV1(BaseModel):
    """
    Strict parse output contract.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["v1"] = PARSE_SCHEMA_VERSION_V1
    source_platform: str = Field(min_length=1, max_length=32)
    source_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1200)
    key_points: List[str] = Field(min_length=1, max_length=12)
    keywords: List[str] = Field(min_length=1, max_length=20)
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    language: str = Field(min_length=2, max_length=8)
    confidence_model: float = Field(ge=0.0, le=1.0)

    @field_validator("key_points", "keywords")
    @classmethod
    def _validate_list_text(cls, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            cleaned.append(text)
        if not cleaned:
            raise ValueError("must include at least one non-empty value")
        return cleaned
