"""Strict extraction schema. Every field carries value, confidence and provenance (page + text span)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

EXTRACTION_FIELDS = [
    "well_id", "field", "date", "document_type", "intervention_type", "problem_reported", "reason_for_intervention", "equipment", "pump_type", "work_performed",
    "contractor", "duration", "cost", "currency", "oil_before", "oil_after", "water_before", "water_after", "water_cut_before", "water_cut_after", "pressure", "downtime",
    "parts_replaced", "engineer_name", "outcome_description", "follow_up_action",
]
NUMERIC_FIELDS = {"cost", "oil_before", "oil_after", "water_before", "water_after", "water_cut_before", "water_cut_after", "pressure", "downtime", "duration"}


class FieldValue(BaseModel):
    value: Optional[Any] = None
    confidence: float = 0.0
    page: Optional[int] = None
    span: Optional[list[int]] = None   # [start, end] character offsets in the page text
    snippet: Optional[str] = None
    source: str = "mock"


class Extraction(BaseModel):
    document_id: str
    source_file: str
    source_language: str = "unknown"
    ocr_confidence: Optional[float] = None
    llm_confidence: float = 0.0
    human_review_status: str = "pending"  # pending | approved | edited | rejected | unreadable
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    raw_text_snippet: str = ""
    provider: str = "mock"

    def to_record(self) -> dict:
        return {k: (v.value) for k, v in self.fields.items()}


class Document(BaseModel):
    document_id: str
    file_name: str
    stored_path: str
    file_type: str
    language: str = "unknown"
    doc_type: str = "unknown"
    date: Optional[str] = None
    well_id: Optional[str] = None
    pages: int = 1
    text_source: str = "text"   # text | ocr | none
    ocr_confidence: Optional[float] = None
    review_status: str = "pending"
    uploaded_at: str = ""
    bundled: bool = False
