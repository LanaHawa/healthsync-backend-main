"""Generate synthetic data for HealthSYNC database"""

import argparse
import csv
import logging
import random
import secrets
import string
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import bcrypt
import numpy as np
from faker import Faker

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
SYNTHETIC_DATA_DIR = BACKEND_DIR / "data" / "synthetic_data"
sys.path.insert(0, str(BACKEND_DIR / "src"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

fake = Faker("en_CA")

# Common diabetes medications
DIABETES_MEDICATIONS = [
    {"name": "Metformin", "strength": "500mg", "form": "Tablet", "route": "Oral"},
    {"name": "Metformin", "strength": "850mg", "form": "Tablet", "route": "Oral"},
    {"name": "Metformin", "strength": "1000mg", "form": "Tablet", "route": "Oral"},
    {"name": "Januvia", "strength": "100mg", "form": "Tablet", "route": "Oral"},
    {"name": "Jardiance", "strength": "10mg", "form": "Tablet", "route": "Oral"},
    {"name": "Jardiance", "strength": "25mg", "form": "Tablet", "route": "Oral"},
    {
        "name": "Lantus",
        "strength": "100 units/mL",
        "form": "Injection",
        "route": "Subcutaneous",
    },
    {
        "name": "Humalog",
        "strength": "100 units/mL",
        "form": "Injection",
        "route": "Subcutaneous",
    },
    {
        "name": "Ozempic",
        "strength": "0.5mg",
        "form": "Injection",
        "route": "Subcutaneous",
    },
    {
        "name": "Ozempic",
        "strength": "1mg",
        "form": "Injection",
        "route": "Subcutaneous",
    },
    {
        "name": "Trulicity",
        "strength": "1.5mg",
        "form": "Injection",
        "route": "Subcutaneous",
    },
    {
        "name": "Victoza",
        "strength": "1.8mg",
        "form": "Injection",
        "route": "Subcutaneous",
    },
    {"name": "Glipizide", "strength": "5mg", "form": "Tablet", "route": "Oral"},
    {"name": "Glipizide", "strength": "10mg", "form": "Tablet", "route": "Oral"},
    {"name": "Actos", "strength": "30mg", "form": "Tablet", "route": "Oral"},
]

# Common allergies
COMMON_ALLERGIES = [
    {"allergen": "Penicillin", "severity": "High", "reaction": "Anaphylaxis"},
    {"allergen": "Sulfa drugs", "severity": "Moderate", "reaction": "Rash, hives"},
    {"allergen": "Aspirin", "severity": "Moderate", "reaction": "Stomach upset"},
    {"allergen": "Ibuprofen", "severity": "Low", "reaction": "Skin rash"},
    {"allergen": "Latex", "severity": "Moderate", "reaction": "Contact dermatitis"},
    {"allergen": "Shellfish", "severity": "High", "reaction": "Anaphylaxis"},
    {"allergen": "Peanuts", "severity": "High", "reaction": "Anaphylaxis"},
    {"allergen": "Tree nuts", "severity": "Moderate", "reaction": "Hives, swelling"},
    {"allergen": "Eggs", "severity": "Low", "reaction": "Digestive issues"},
    {"allergen": "Codeine", "severity": "Moderate", "reaction": "Nausea, dizziness"},
]


class SyntheticDataGenerator:
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)
        fake.seed_instance(seed)
        self.clinics: List[Dict[str, Any]] = []
        self.clinicians: List[Dict[str, Any]] = []
        self.medications: List[Dict[str, Any]] = []
        self.allergies: List[Dict[str, Any]] = []
        self.clinic_clinicians: Dict[str, List[str]] = {}

    def generate_secure_password(self, length: int = 12) -> str:
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    def generate_password_hash(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def generate_clinics(self, count: int = 3) -> List[Dict[str, Any]]:
        logger.info(f"Generating {count} clinics...")
        specialties = ["Diabetes", "Endocrinology", "Family Medicine", "Primary Care"]
        formats = [
            "{city} {specialty} Centre",
            "{city} {specialty} Clinic",
            "{last_name} {specialty} Associates",
        ]

        for _ in range(count):
            clinic_id = str(uuid4())
            address = fake.address().replace("\n", ", ")
            name_format = random.choice(formats)
            clinic_name = name_format.format(
                city=fake.city(),
                last_name=fake.last_name(),
                specialty=random.choice(specialties),
            )

            clinic = {
                "clinic_id": clinic_id,
                "name": clinic_name,
                "address": address,
                "phone_number": fake.phone_number(),
                "last_number": None,
                "clinic_code": f"{random.randint(0, 99999):05d}",
            }
            self.clinics.append(clinic)
            self.clinic_clinicians[clinic_id] = []
            logger.info(f"  {clinic_name}")

        return self.clinics

    def generate_clinicians(self, count: int = 5) -> List[Dict[str, Any]]:
        logger.info(f"Generating {count} clinicians...")
        if not self.clinics:
            raise ValueError("Generate clinics first")

        for _ in range(count):
            auth_user_id = str(uuid4())
            clinician_id = str(uuid4())

            first_name = fake.first_name()
            last_name = fake.last_name()
            email = f"{first_name.lower()}.{last_name.lower()}@healthsync.ca"

            clinic = random.choice(self.clinics)
            clinic_id = clinic["clinic_id"]

            password = self.generate_secure_password(length=12)
            password_hash = self.generate_password_hash(password)

            auth_user = {
                "user_id": auth_user_id,
                "email": email,
                "password_hash": password_hash,
                "role": "CLINICIAN",
                "mfa_enabled": random.choice([True, False]),
                "identity_provider": "local",
                "last_login_at": fake.date_time_between(
                    start_date="-30d", end_date="now"
                ).isoformat(),
            }

            clinician = {
                "clinician_id": clinician_id,
                "auth_user_id": auth_user_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                # if your schema enforces 7 digits, generate digits:
                "license_number": f"{random.randint(0, 9999999):07d}",
                "clinic_id": clinic_id,
                "password_plain": password,
                "auth_user": auth_user,
            }

            self.clinicians.append(clinician)
            self.clinic_clinicians[clinic_id].append(clinician_id)

            logger.info(f"  Dr. {first_name} {last_name} @ {clinic['name']}")

        return self.clinicians

    def generate_medications(self) -> List[Dict[str, Any]]:
        """Generate medication records for diabetes management."""
        logger.info(f"Generating {len(DIABETES_MEDICATIONS)} medications...")

        for med in DIABETES_MEDICATIONS:
            medication = {"medication_id": str(uuid4()), **med}
            self.medications.append(medication)
            logger.info(f"  {med['name']} ({med['strength']})")

        return self.medications

    def generate_allergies_list(self) -> List[Dict[str, Any]]:
        """Generate common allergy records."""
        logger.info(f"Generating {len(COMMON_ALLERGIES)} common allergies...")

        for allergy in COMMON_ALLERGIES:
            allergy_record = {"allergy_id": str(uuid4()), **allergy}
            self.allergies.append(allergy_record)
            logger.info(f"  {allergy['allergen']} ({allergy['severity']} severity)")

        return self.allergies

    def export_to_csv(self):
        logger.info("Exporting to CSV...")
        SYNTHETIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

        # clinics.csv
        with open(
            SYNTHETIC_DATA_DIR / "clinics.csv", "w", newline="", encoding="utf-8"
        ) as f:
            if self.clinics:
                w = csv.DictWriter(f, fieldnames=list(self.clinics[0].keys()))
                w.writeheader()
                w.writerows(self.clinics)

        # clinicians.csv (flatten)
        rows = []
        for c in self.clinicians:
            row = {k: v for k, v in c.items() if k != "auth_user"}
            rows.append(row)

        if rows:
            with open(
                SYNTHETIC_DATA_DIR / "clinicians.csv", "w", newline="", encoding="utf-8"
            ) as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

        # medications.csv
        with open(
            SYNTHETIC_DATA_DIR / "medications.csv", "w", newline="", encoding="utf-8"
        ) as f:
            if self.medications:
                w = csv.DictWriter(f, fieldnames=list(self.medications[0].keys()))
                w.writeheader()
                w.writerows(self.medications)

        # allergies.csv
        with open(
            SYNTHETIC_DATA_DIR / "allergies.csv", "w", newline="", encoding="utf-8"
        ) as f:
            if self.allergies:
                w = csv.DictWriter(f, fieldnames=list(self.allergies[0].keys()))
                w.writeheader()
                w.writerows(self.allergies)

        logger.info(f"CSV exported to: {SYNTHETIC_DATA_DIR}")


def main():
    p = argparse.ArgumentParser(description="Generate synthetic data")
    p.add_argument("--clinics", type=int, default=20)
    p.add_argument("--clinicians", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--export-csv", action="store_true")
    args = p.parse_args()

    if args.quick:
        args.clinics = 2
        args.clinicians = 2

    try:
        g = SyntheticDataGenerator(seed=args.seed)
        g.generate_clinics(args.clinics)
        g.generate_clinicians(args.clinicians)
        g.generate_medications()
        g.generate_allergies_list()
        if args.export_csv:
            g.export_to_csv()
        logger.info("Synthetic generation completed.")
    except Exception as e:
        logger.error(f"Failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
