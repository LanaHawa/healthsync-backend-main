# backend/src/healthsync/data/schemas/visits.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# IMPORTANT: Must match your SQL enum EXACTLY:
#   CREATE TYPE visit_type_enum AS ENUM ('FOLLOW_UP', 'CHECK_IN', 'OTHER');
VisitType = Literal["FOLLOW_UP", "CHECK_IN", "OTHER"]

# Must match:
#   CREATE TYPE avs_channel AS ENUM ('EMAIL', 'PRINT');
AVSChannel = Literal["EMAIL", "PRINT"]


class VisitCreate(BaseModel):
    patient_id: UUID
    clinic_id: Optional[UUID] = None

    # If not provided, backend service can default to NOW()
    start_time: Optional[datetime] = None

    visit_type: VisitType
    visit_type_other_text: Optional[str] = None

    notes: Optional[str] = None

    @model_validator(mode="after")
    def _validate_other_text(self):
        # SQL has a CHECK that OTHER requires visit_type_other_text
        if self.visit_type == "OTHER" and not (
            self.visit_type_other_text and self.visit_type_other_text.strip()
        ):
            raise ValueError(
                "visit_type_other_text is required when visit_type is OTHER"
            )
        # If not OTHER, ignore any provided other text to keep data clean
        if self.visit_type != "OTHER":
            self.visit_type_other_text = None
        return self


class VisitEndRequest(BaseModel):
    end_time: Optional[datetime] = None


class VisitOut(BaseModel):
    visit_id: UUID
    patient_id: UUID
    clinician_id: UUID
    clinic_id: Optional[UUID] = None

    start_time: datetime
    end_time: Optional[datetime] = None

    visit_type: VisitType
    visit_type_other_text: Optional[str] = None

    notes: Optional[str] = None

    patient_first_name: Optional[str] = None
    patient_last_name: Optional[str] = None

    created_at: datetime
    updated_at: datetime


class VisitSummaryUpsert(BaseModel):
    clinical_findings: str = Field(..., min_length=1)
    decisions: str = Field(..., min_length=1)
    follow_up_plan: Optional[str] = None


class VisitSummaryOut(BaseModel):
    summary_id: UUID
    visit_id: UUID
    created_by: UUID
    created_at: datetime
    clinical_findings: str
    decisions: str
    follow_up_plan: Optional[str] = None


class AVSUpsert(BaseModel):
    delivered_via: AVSChannel
    content: str = Field(..., min_length=1)


class AVSOut(BaseModel):
    avs_id: UUID
    visit_id: UUID
    created_at: datetime
    generated_by: UUID
    delivered_via: AVSChannel
    content: str


class ActionItemOut(BaseModel):
    action_id: UUID
    visit_id: UUID
    patient_id: UUID
    description: str
    owner_type: Literal["PATIENT", "CLINICIAN", "SYSTEM"]  # stakeholder_type enum
    status: Literal[
        "OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"
    ]  # action_status enum
    due_date: Optional[datetime] = None
    follow_up_plan: Optional[str] = None
    created_at: datetime
    created_by: UUID


class ActionItemCreate(BaseModel):
    description: str = Field(..., min_length=1)
    owner_type: Literal["PATIENT", "CLINICIAN", "SYSTEM"] = "PATIENT"
    status: Literal["OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"] = "OPEN"
    due_date: Optional[datetime] = None
    follow_up_plan: Optional[str] = None


class ActionItemPatch(BaseModel):
    description: Optional[str] = None
    owner_type: Optional[Literal["PATIENT", "CLINICIAN", "SYSTEM"]] = None
    status: Optional[Literal["OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"]] = None
    due_date: Optional[datetime] = None
    follow_up_plan: Optional[str] = None


class AgendaItemCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    order_index: int = 0


class AgendaItemPatch(BaseModel):
    status: Optional[Literal["OPEN", "DONE", "SKIPPED"]] = None
    title: Optional[str] = None
    description: Optional[str] = None


class AgendaItemOut(BaseModel):
    agenda_item_id: UUID
    visit_id: UUID
    title: str
    description: Optional[str] = None
    order_index: int
    status: Literal["OPEN", "DONE", "SKIPPED"]


class VisitDetailOut(BaseModel):
    visit: VisitOut
    summary: Optional[VisitSummaryOut] = None
    avs: Optional[AVSOut] = None
    action_items: List[ActionItemOut] = Field(default_factory=list)
    agenda_items: List[AgendaItemOut] = Field(default_factory=list)


class AnnotationOut(BaseModel):
    annotation_id: UUID
    visit_id: UUID
    type: str
    content: str
    created_at: datetime
    visit_start_time: Optional[datetime] = None


class VisitPatch(BaseModel):
    """Fields the clinician is allowed to update on an existing visit."""

    notes: Optional[str] = None


class AnnotationImageCreate(BaseModel):
    chart_key: str
    chart_title: str
    label: Optional[str] = None
    image_data: str  # base64 PNG data URL produced by the annotation overlay


class AnnotationImageOut(BaseModel):
    image_id: UUID
    visit_id: UUID
    created_by: UUID
    chart_key: str
    chart_title: str
    label: Optional[str] = None
    image_data: str
    saved_at: datetime
