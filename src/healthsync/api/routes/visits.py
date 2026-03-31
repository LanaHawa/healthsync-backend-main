# backend/src/healthsync/routes/visits.py

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Depends

from healthsync.data.schemas import (
    VisitCreate,
    VisitEndRequest,
    VisitPatch,
    VisitOut,
    VisitSummaryUpsert,
    VisitSummaryOut,
    AVSUpsert,
    AVSOut,
    ActionItemOut,
    ActionItemCreate,
    ActionItemPatch,
    AgendaItemCreate,
    AgendaItemPatch,
    AgendaItemOut,
    VisitDetailOut,
    AnnotationOut,
    AnnotationImageCreate,
    AnnotationImageOut,
)
from healthsync.services.visits_service import VisitsService
from healthsync.auth.jwt import require_role
from healthsync.db.connection import get_conn

from healthsync.repositories.clinicians_repo import CliniciansRepository
from healthsync.repositories.patients import PatientsRepository
from healthsync.repositories.visits import VisitsRepository


router = APIRouter(prefix="/visits", tags=["visits"])

service = VisitsService()
clinicians_repo = CliniciansRepository()
patients_repo = PatientsRepository()
visits_repo = VisitsRepository()


def _get_clinician_id_from_user(user) -> UUID:
    with get_conn() as conn:
        clinician = clinicians_repo.get_by_auth_user_id(conn, str(user["user_id"]))
        if not clinician:
            raise HTTPException(status_code=404, detail="Clinician profile not found")
        return UUID(str(clinician["clinician_id"]))


def _get_patient_id_from_user(user) -> UUID:
    with get_conn() as conn:
        patient = patients_repo.get_by_auth_user_id_with_conn(
            conn, str(user["user_id"])
        )
        if not patient:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        return UUID(str(patient["patient_id"]))


# ---------------------------
# Clinician/Admin: start a visit
# ---------------------------
@router.post("", response_model=VisitOut, status_code=201)
def start_visit(
    payload: VisitCreate,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        data = service.start_visit(payload.model_dump(), clinician_id=clinician_id)
        return VisitOut(**data)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------
# Clinician/Admin: end a visit
# ---------------------------
@router.patch("/{visit_id}/end", response_model=VisitOut)
def end_visit(
    visit_id: UUID,
    payload: VisitEndRequest,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        data = service.end_visit(
            visit_id, clinician_id=clinician_id, end_time=payload.end_time
        )
        return VisitOut(**data)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------
# Clinician/Admin: upsert visit summary
# created_by comes from JWT user_id (auth_users.user_id)
# ---------------------------
@router.put("/{visit_id}/summary", response_model=VisitSummaryOut)
def upsert_summary(
    visit_id: UUID,
    payload: VisitSummaryUpsert,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.upsert_summary(
            visit_id=visit_id,
            clinician_id=clinician_id,
            created_by=UUID(str(user["user_id"])),
            clinical_findings=payload.clinical_findings,
            decisions=payload.decisions,
            follow_up_plan=payload.follow_up_plan,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------
# Clinician/Admin: upsert AVS
# generated_by comes from JWT user_id (auth_users.user_id)
# ---------------------------
@router.put("/{visit_id}/avs", response_model=AVSOut)
def upsert_avs(
    visit_id: UUID,
    payload: AVSUpsert,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.upsert_avs(
            visit_id=visit_id,
            clinician_id=clinician_id,
            generated_by=UUID(str(user["user_id"])),
            delivered_via=payload.delivered_via,
            content=payload.content,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------
# Patient: list their own annotations across all visits
# patient_id derived from JWT
# ---------------------------
@router.get("/my-annotations", response_model=List[AnnotationOut])
def list_my_annotations(
    limit: int = Query(100, ge=1, le=500),
    user=Depends(require_role("PATIENT")),
):
    patient_id = _get_patient_id_from_user(user)
    with get_conn() as conn:
        return visits_repo.list_annotations_for_patient_with_conn(
            conn, patient_id, limit
        )


# ---------------------------
# Patient: list their own visits
# ---------------------------
@router.get("/my-visits", response_model=List[VisitOut])
def list_my_visits(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(require_role("PATIENT")),
):
    patient_id = _get_patient_id_from_user(user)
    data = service.list_visits_for_patient_self(patient_id, limit=limit, offset=offset)
    return [VisitOut(**row) for row in data]


# ---------------------------
# Patient: list all their action items across all visits
# ---------------------------
@router.get("/my-action-items", response_model=List[ActionItemOut])
def list_my_action_items(
    user=Depends(require_role("PATIENT")),
):
    patient_id = _get_patient_id_from_user(user)
    return service.list_action_items_for_patient(patient_id)


# ---------------------------
# Patient: update status of one of their action items
# ---------------------------
@router.patch("/my-action-items/{item_id}", response_model=ActionItemOut)
def update_my_action_item(
    item_id: UUID,
    payload: ActionItemPatch,
    user=Depends(require_role("PATIENT")),
):
    patient_id = _get_patient_id_from_user(user)
    if not payload.status:
        raise HTTPException(status_code=400, detail="status is required")
    try:
        return service.patch_action_item_by_patient(
            action_id=item_id,
            patient_id=patient_id,
            status=payload.status,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------
# Clinician/Admin: list visits by this clinician
# ---------------------------
@router.get("/by-clinician", response_model=List[VisitOut])
def list_visits_by_clinician(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    data = visits_repo.list_for_clinician(clinician_id, limit=limit, offset=offset)
    return [VisitOut(**row) for row in data]


# ---------------------------
# Clinician/Admin: list visits for a patient
# access enforced using clinician_id from JWT inside service
# ---------------------------
@router.get("/by-patient/{patient_id}", response_model=List[VisitOut])
def list_visits_for_patient(
    patient_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        data = service.list_visits_for_patient(
            patient_id, clinician_id=clinician_id, limit=limit, offset=offset
        )
        return [VisitOut(**row) for row in data]
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ---------------------------
# Clinician/Admin: visit detail
# ---------------------------
@router.get("/{visit_id}", response_model=VisitDetailOut)
def get_visit_detail(
    visit_id: UUID,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.get_visit_detail(visit_id, clinician_id=clinician_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------
# Patient: get AVS for their own visit
# patient_id derived from JWT
# ---------------------------
@router.get("/{visit_id}/avs", response_model=AVSOut)
def get_avs_for_patient(
    visit_id: UUID,
    user=Depends(require_role("PATIENT")),
):
    patient_id = _get_patient_id_from_user(user)
    try:
        return service.get_avs_for_patient(visit_id, patient_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------
# Clinician/Admin: update visit notes (PATCH)
# ---------------------------
@router.patch("/{visit_id}", response_model=VisitOut)
def update_visit(
    visit_id: UUID,
    payload: VisitPatch,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        data = service.update_visit_notes(
            visit_id=visit_id,
            clinician_id=clinician_id,
            notes=payload.notes,
        )
        return VisitOut(**data)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------
# Clinician/Admin: agenda item CRUD
# ---------------------------
@router.get("/{visit_id}/agenda", response_model=List[AgendaItemOut])
def list_agenda_items(
    visit_id: UUID,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.list_agenda_items(visit_id, clinician_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{visit_id}/agenda", response_model=AgendaItemOut, status_code=201)
def create_agenda_item(
    visit_id: UUID,
    payload: AgendaItemCreate,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.create_agenda_item(
            visit_id=visit_id,
            clinician_id=clinician_id,
            title=payload.title,
            description=payload.description,
            order_index=payload.order_index,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{visit_id}/agenda/{item_id}", response_model=AgendaItemOut)
def patch_agenda_item(
    visit_id: UUID,
    item_id: UUID,
    payload: AgendaItemPatch,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.patch_agenda_item(
            visit_id=visit_id,
            clinician_id=clinician_id,
            agenda_item_id=item_id,
            **payload.model_dump(exclude_none=True),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{visit_id}/agenda/{item_id}", status_code=204)
def delete_agenda_item(
    visit_id: UUID,
    item_id: UUID,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        service.delete_agenda_item(visit_id, clinician_id, item_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------
# Clinician/Admin: action item CRUD
# ---------------------------
@router.get("/{visit_id}/action-items", response_model=List[ActionItemOut])
def list_action_items(
    visit_id: UUID,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    _get_clinician_id_from_user(user)  # verifies CLINICIAN role has a profile
    return service.action_repo.list_by_visit(visit_id)


@router.post("/{visit_id}/action-items", response_model=ActionItemOut, status_code=201)
def create_action_item(
    visit_id: UUID,
    payload: ActionItemCreate,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.create_action_item(
            visit_id=visit_id,
            clinician_id=clinician_id,
            created_by=UUID(str(user["user_id"])),
            description=payload.description,
            owner_type=payload.owner_type,
            status=payload.status,
            due_date=payload.due_date,
            follow_up_plan=payload.follow_up_plan,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{visit_id}/action-items/{item_id}", response_model=ActionItemOut)
def patch_action_item(
    visit_id: UUID,
    item_id: UUID,
    payload: ActionItemPatch,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.patch_action_item_by_clinician(
            visit_id=visit_id,
            clinician_id=clinician_id,
            action_id=item_id,
            **payload.model_dump(exclude_none=True),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------
# Clinician/Admin: save annotation image for a visit
# ---------------------------
@router.post(
    "/{visit_id}/annotation-images", response_model=AnnotationImageOut, status_code=201
)
def save_annotation_image(
    visit_id: UUID,
    payload: AnnotationImageCreate,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.save_annotation_image(
            visit_id=visit_id,
            clinician_id=clinician_id,
            created_by=UUID(str(user["user_id"])),
            chart_key=payload.chart_key,
            chart_title=payload.chart_title,
            label=payload.label,
            image_data=payload.image_data,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------
# Clinician/Admin: list annotation images for a visit
# ---------------------------
@router.get("/{visit_id}/annotation-images", response_model=List[AnnotationImageOut])
def list_annotation_images(
    visit_id: UUID,
    user=Depends(require_role("CLINICIAN", "ADMIN")),
):
    clinician_id = _get_clinician_id_from_user(user)
    try:
        return service.list_annotation_images(
            visit_id=visit_id,
            clinician_id=clinician_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
