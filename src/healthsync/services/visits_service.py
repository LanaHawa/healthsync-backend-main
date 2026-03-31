from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime

from healthsync.repositories.visits import VisitsRepository
from healthsync.repositories.action_items import ActionItemsRepository
from healthsync.repositories.agenda_items_repo import AgendaItemsRepository
from healthsync.repositories.access_permissions import AccessPermissionsRepository


class VisitsService:
    def __init__(self) -> None:
        self.visits_repo = VisitsRepository()
        self.action_repo = ActionItemsRepository()
        self.agenda_repo = AgendaItemsRepository()
        self.perms_repo = AccessPermissionsRepository()

    # ---------- helpers ----------
    def _assert_clinician_access(
        self, conn, clinician_id: UUID, patient_id: UUID
    ) -> None:
        """
        Enforce that clinician has APPROVED access to patient.
        Uses the same transaction connection to keep everything consistent.
        """
        ok = self.perms_repo.has_approved_access_with_conn(
            conn, str(clinician_id), str(patient_id)
        )
        if not ok:
            raise PermissionError(
                "Clinician does not have APPROVED access to this patient"
            )

    # ---------- clinician actions ----------
    def start_visit(
        self,
        payload: Dict[str, Any],
        clinician_id: UUID,
        conn=None,
    ) -> Dict[str, Any]:
        """
        Start a visit for a patient by a clinician.

        IMPORTANT: your routes call `start_visit(payload, clinician_id=...)`
        so this signature matches that. We also support passing `conn` from
        a service-layer transaction if you add it later.
        """
        if conn is not None:
            self._assert_clinician_access(
                conn, clinician_id, UUID(str(payload["patient_id"]))
            )

        # visits_repo.create opens its own conn (fine for now)
        return self.visits_repo.create(
            {
                **payload,
                "clinician_id": clinician_id,
            }
        )

    def end_visit(
        self, visit_id: UUID, clinician_id: UUID, end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        End a visit. (You could optionally enforce clinician owns the visit, but
        your repo doesn't currently check that; route already passes clinician_id
        and service can enforce if desired.)
        """
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")

        # Optional: ensure this clinician is the visit clinician
        if str(visit["clinician_id"]) != str(clinician_id):
            raise PermissionError("Clinician is not allowed to end this visit")

        row = self.visits_repo.end_visit(visit_id, end_time=end_time)
        if not row:
            raise KeyError("Visit not found")
        return row

    def upsert_summary(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        created_by: UUID,
        clinical_findings: str,
        decisions: str,
        follow_up_plan: Optional[str],
        conn=None,
    ) -> Dict[str, Any]:
        """
        Upsert a visit summary. We enforce:
          - visit exists
          - clinician owns the visit
          - clinician has APPROVED access to the patient (optional but recommended)
        """
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")

        if str(visit["clinician_id"]) != str(clinician_id):
            raise PermissionError(
                "Clinician is not allowed to write a summary for this visit"
            )

        if conn is not None:
            self._assert_clinician_access(
                conn, clinician_id, UUID(str(visit["patient_id"]))
            )

        return self.visits_repo.upsert_summary(
            visit_id=visit_id,
            created_by=created_by,
            clinical_findings=clinical_findings,
            decisions=decisions,
            follow_up_plan=follow_up_plan,
        )

    def upsert_avs(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        generated_by: UUID,
        delivered_via: str,
        content: str,
        conn=None,
    ) -> Dict[str, Any]:
        """
        Upsert an after-visit summary (AVS). Enforce:
          - visit exists
          - clinician owns visit
          - (optional) APPROVED access
        """
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")

        if str(visit["clinician_id"]) != str(clinician_id):
            raise PermissionError(
                "Clinician is not allowed to write AVS for this visit"
            )

        if conn is not None:
            self._assert_clinician_access(
                conn, clinician_id, UUID(str(visit["patient_id"]))
            )

        return self.visits_repo.upsert_avs(
            visit_id=visit_id,
            generated_by=generated_by,
            delivered_via=delivered_via,
            content=content,
        )

    # ---------- reads ----------
    def list_visits_for_patient(
        self,
        patient_id: UUID,
        clinician_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
        conn=None,
    ) -> List[Dict[str, Any]]:
        """
        List visits for a patient.
        If clinician_id provided, enforce APPROVED access.
        """
        if clinician_id is not None and conn is not None:
            self._assert_clinician_access(conn, clinician_id, patient_id)

        return self.visits_repo.list_for_patient(patient_id, limit=limit, offset=offset)

    def get_visit_detail(
        self, visit_id: UUID, clinician_id: Optional[UUID] = None, conn=None
    ) -> Dict[str, Any]:
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")

        # If clinician_id provided, enforce clinician has APPROVED access to that visit's patient
        if clinician_id is not None and conn is not None:
            self._assert_clinician_access(
                conn, clinician_id, UUID(str(visit["patient_id"]))
            )

        summary = self.visits_repo.get_summary(visit_id)
        avs = self.visits_repo.get_avs(visit_id)
        action_items = self.action_repo.list_by_visit(visit_id)
        agenda_items = self.agenda_repo.list_by_visit(visit_id)

        return {
            "visit": visit,
            "summary": summary,
            "avs": avs,
            "action_items": action_items,
            "agenda_items": agenda_items,
        }

    def get_avs_for_patient(self, visit_id: UUID, patient_id: UUID) -> Dict[str, Any]:
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")

        if str(visit["patient_id"]) != str(patient_id):
            raise PermissionError("This visit does not belong to the patient")

        avs = self.visits_repo.get_avs(visit_id)
        if not avs:
            raise KeyError("AVS not found")

        return avs

    # ---------- visit notes update ----------

    def update_visit_notes(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        notes: Optional[str],
    ) -> Dict[str, Any]:
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")
        if str(visit["clinician_id"]) != str(clinician_id):
            raise PermissionError("Clinician is not allowed to modify this visit")
        row = self.visits_repo.update_notes(visit_id, notes)
        if not row:
            raise KeyError("Visit not found after update")
        return row

    # ---------- annotation images ----------

    def save_annotation_image(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        created_by: UUID,
        chart_key: str,
        chart_title: str,
        label: Optional[str],
        image_data: str,
    ) -> Dict[str, Any]:
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")
        if str(visit["clinician_id"]) != str(clinician_id):
            raise PermissionError("Clinician is not allowed to annotate this visit")
        return self.visits_repo.create_annotation_image(
            {
                "visit_id": visit_id,
                "created_by": created_by,
                "chart_key": chart_key,
                "chart_title": chart_title,
                "label": label,
                "image_data": image_data,
            }
        )

    def list_annotation_images(
        self,
        visit_id: UUID,
        clinician_id: UUID,
    ) -> List[Dict[str, Any]]:
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")
        if str(visit["clinician_id"]) != str(clinician_id):
            raise PermissionError("Clinician is not allowed to view this visit")
        return self.visits_repo.list_annotation_images_for_visit(visit_id)

    # ---------- agenda items ----------

    def _assert_clinician_owns_visit(
        self, visit_id: UUID, clinician_id: UUID
    ) -> Dict[str, Any]:
        visit = self.visits_repo.get(visit_id)
        if not visit:
            raise KeyError("Visit not found")
        if str(visit["clinician_id"]) != str(clinician_id):
            raise PermissionError("Clinician does not own this visit")
        return visit

    def list_agenda_items(
        self, visit_id: UUID, clinician_id: UUID
    ) -> List[Dict[str, Any]]:
        self._assert_clinician_owns_visit(visit_id, clinician_id)
        return self.agenda_repo.list_by_visit(visit_id)

    def create_agenda_item(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        title: str,
        description: Optional[str] = None,
        order_index: int = 0,
    ) -> Dict[str, Any]:
        self._assert_clinician_owns_visit(visit_id, clinician_id)
        return self.agenda_repo.create(visit_id, title, description, order_index)

    def patch_agenda_item(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        agenda_item_id: UUID,
        **kwargs,
    ) -> Dict[str, Any]:
        self._assert_clinician_owns_visit(visit_id, clinician_id)
        row = self.agenda_repo.patch(agenda_item_id, **kwargs)
        if not row:
            raise KeyError("Agenda item not found")
        return row

    def delete_agenda_item(
        self, visit_id: UUID, clinician_id: UUID, agenda_item_id: UUID
    ) -> None:
        self._assert_clinician_owns_visit(visit_id, clinician_id)
        deleted = self.agenda_repo.delete(agenda_item_id)
        if not deleted:
            raise KeyError("Agenda item not found")

    # ---------- action items (clinician) ----------

    def create_action_item(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        created_by: UUID,
        description: str,
        owner_type: str = "PATIENT",
        status: str = "OPEN",
        due_date: Optional[datetime] = None,
        follow_up_plan: Optional[str] = None,
    ) -> Dict[str, Any]:
        visit = self._assert_clinician_owns_visit(visit_id, clinician_id)
        return self.action_repo.create(
            visit_id=visit_id,
            patient_id=UUID(str(visit["patient_id"])),
            description=description,
            owner_type=owner_type,
            created_by=created_by,
            status=status,
            due_date=due_date,
            follow_up_plan=follow_up_plan,
        )

    def patch_action_item_by_clinician(
        self,
        visit_id: UUID,
        clinician_id: UUID,
        action_id: UUID,
        **kwargs,
    ) -> Dict[str, Any]:
        self._assert_clinician_owns_visit(visit_id, clinician_id)
        row = self.action_repo.update(action_id, **kwargs)
        if not row:
            raise KeyError("Action item not found")
        return row

    # ---------- action items (patient) ----------

    def list_action_items_for_patient(self, patient_id: UUID) -> List[Dict[str, Any]]:
        return self.action_repo.list_by_patient(patient_id)

    def patch_action_item_by_patient(
        self, action_id: UUID, patient_id: UUID, status: str
    ) -> Dict[str, Any]:
        item = self.action_repo.get_by_id(action_id)
        if not item:
            raise KeyError("Action item not found")
        if str(item["patient_id"]) != str(patient_id):
            raise PermissionError("Action item does not belong to this patient")
        row = self.action_repo.update(action_id, status=status)
        if not row:
            raise KeyError("Action item not found after update")
        return row

    # ---------- patient: list own visits ----------

    def list_visits_for_patient_self(
        self, patient_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        return self.visits_repo.list_for_patient(patient_id, limit=limit, offset=offset)
