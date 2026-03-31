"""Script to seed the database from CSV files."""

import csv
import sys
import logging
import bcrypt
import secrets
import string
import argparse
import pandas as pd
import random
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from uuid import uuid4
from datetime import datetime, date
from faker import Faker

# Add src to path for imports
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
DATASETS_DIR = BACKEND_DIR / "data" / "datasets"
SYNTHETIC_DIR = BACKEND_DIR / "data" / "synthetic_data"
sys.path.insert(0, str(BACKEND_DIR / "src"))

from healthsync.db.connection import get_conn

# Initialize Faker with a seed for reproducibility
fake = Faker()
Faker.seed(42)
random.seed(42)

# Canadian provinces and territories
CANADIAN_PROVINCES = [
    ("AB", "Alberta"),
    ("BC", "British Columbia"),
    ("MB", "Manitoba"),
    ("NB", "New Brunswick"),
    ("NL", "Newfoundland and Labrador"),
    ("NT", "Northwest Territories"),
    ("NS", "Nova Scotia"),
    ("NU", "Nunavut"),
    ("ON", "Ontario"),
    ("PE", "Prince Edward Island"),
    ("QC", "Quebec"),
    ("SK", "Saskatchewan"),
    ("YT", "Yukon"),
]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DataLoader:
    """Load and parse CSV data for seeding the database."""

    def __init__(
        self, dataset_dir: Path = DATASETS_DIR, synthetic_dir: Path = SYNTHETIC_DIR
    ):
        self.dataset_dir = dataset_dir
        self.synthetic_dir = synthetic_dir
        self.fake = Faker()
        self.fake.seed_instance(42)
        random.seed(42)

    def read_csv(self, filename: str, directory: Path = None) -> List[Dict[str, Any]]:
        """Read a CSV file and return a list of dictionaries."""
        directory = directory or self.dataset_dir
        filepath = directory / filename

        if not filepath.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        with open(filepath, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            return [row for row in reader]

    def generate_patient_name(self, gender: str) -> Tuple[str, str]:
        """Generate a realistic patient name based on gender."""
        if gender.upper() == "M":
            first_name = self.fake.first_name_male()
        elif gender.upper() == "F":
            first_name = self.fake.first_name_female()
        else:
            first_name = self.fake.first_name()

        last_name = self.fake.last_name()
        return first_name, last_name

    def generate_patient_email(self, first_name: str, last_name: str) -> str:
        """Generate a unique email address for a patient."""
        providers = [
            "gmail.com",
            "yahoo.com",
            "outlook.com",
            "hotmail.com",
            "icloud.com",
        ]
        provider = random.choice(providers)

        formats = [
            f"{first_name.lower()}.{last_name.lower()}@{provider}",
            f"{first_name[0].lower()}{last_name.lower()}@{provider}",
            f"{first_name.lower()}{last_name[0].lower()}@{provider}",
            f"{first_name.lower()}{random.randint(1, 999)}@{provider}",
        ]

        return random.choice(formats)

    def generate_secure_password(self, length: int = 16) -> str:
        """Generate a secure random password."""
        alphabet = string.ascii_letters + string.digits + string.punctuation
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def generate_canadian_address(self) -> Tuple[str, str, str]:
        """Generate a realistic Canadian address."""
        province_code, province_name = random.choice(CANADIAN_PROVINCES)

        street_number = random.randint(100, 9999)
        street_name = self.fake.street_name()
        street_type = random.choice(
            ["Street", "Avenue", "Road", "Boulevard", "Drive", "Lane"]
        )

        cities_by_province = {
            "ON": ["Toronto", "Ottawa", "Mississauga", "Hamilton", "London"],
            "BC": ["Vancouver", "Victoria", "Surrey", "Burnaby", "Richmond"],
            "AB": ["Calgary", "Edmonton", "Red Deer", "Lethbridge", "Medicine Hat"],
            "QC": ["Montreal", "Quebec City", "Laval", "Gatineau", "Longueuil"],
        }

        city = random.choice(cities_by_province.get(province_code, [self.fake.city()]))

        postal_code = (
            f"{random.choice(string.ascii_uppercase)}{random.randint(0, 9)}"
            f"{random.choice(string.ascii_uppercase)} {random.randint(0, 9)}"
            f"{random.choice(string.ascii_uppercase)}{random.randint(0, 9)}"
        )

        full_address = (
            f"{street_number} {street_name} {street_type}, "
            f"{city}, {province_code} {postal_code}, Canada"
        )

        return full_address, province_code, province_name

    def parse_bio_data(self, filename: str) -> List[Dict[str, Any]]:
        """Parse biometric data from CSV and enrich with patient information."""
        logger.info(f"Reading biometric data from {filename}")

        patients_data = []
        filepath = self.dataset_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(f"Bio CSV file not found: {filepath}")

        data = pd.read_csv(
            filepath,
            usecols=[
                "subject",
                "Age",
                "Gender",
                "BMI",
                "Body weight ",
                "Height ",
                "Insulin ",
            ],
        )

        if data.empty:
            logger.warning(f"No data found in {filename}")
            return []

        for _, row in data.iterrows():
            subject_id = str(row.get("subject", "")).strip()
            age_str = str(row.get("Age", "")).strip()
            gender = str(row.get("Gender", "")).strip().upper()
            bmi = row.get("BMI", None)
            body_weight = row.get("Body weight ", None)
            height = row.get("Height ", None)
            insulin = row.get("Insulin ", None)

            if not subject_id:
                logger.warning("Skipping row with missing subject ID")
                continue

            dob = self._calculate_dob(age_str)

            first_name, last_name = self.generate_patient_name(gender)
            email = self.generate_patient_email(first_name, last_name)
            password = self.generate_secure_password()
            password_hash = self._create_password_hash(password)
            patient_uuid = uuid4()
            auth_user_uuid = uuid4()
            phone_number = self.fake.phone_number()
            address, province_code, province_name = self.generate_canadian_address()

            phn = f"{random.randint(100000000, 999999999)}"

            glucose_data = self.parse_cgm_files(subject_id)

            patient_record = {
                "patient_id": str(patient_uuid),
                "auth_user_id": str(auth_user_uuid),
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "password": password,
                "password_hash": password_hash,
                "age": int(age_str) if age_str.isdigit() else None,
                "date_of_birth": dob,
                "phone_number": phone_number,
                "address": address,
                "phn": phn,
                "gender": "M" if gender == "M" else "F" if gender == "F" else "OTHER",
                "bmi": float(bmi) if pd.notna(bmi) else None,
                "body_weight_lbs": float(body_weight)
                if pd.notna(body_weight)
                else None,
                "height_inches": float(height) if pd.notna(height) else None,
                "insulin_sensitivity": float(insulin) if pd.notna(insulin) else None,
                "bio_data": {
                    "subject_id": subject_id.zfill(3),
                    "bmi": float(bmi) if pd.notna(bmi) else None,
                },
                "glucose_data": glucose_data,
            }

            patients_data.append(patient_record)
            logger.info(
                f"Parsed patient {first_name} {last_name} (Subject {subject_id}) - "
                f"{len(glucose_data)} CGM records"
            )

        logger.info(f"Total patients parsed: {len(patients_data)}")
        return patients_data

    def parse_cgm_files(self, subject_id: str) -> Dict[str, Any]:
        """Parse CGM data from CSV file for a given patient."""
        padded_subject = subject_id.zfill(3)
        target_filename = f"CGMacros-{padded_subject}.csv"
        target_filepath = self.dataset_dir / target_filename

        if not target_filepath.exists():
            logger.warning(
                f" No CGM file found for subject {subject_id} "
                f"(expected: {target_filename})"
            )
            return {}

        metrics = {}

        try:
            data = pd.read_csv(
                target_filepath,
                usecols=[
                    "Timestamp",
                    "Libre GL",
                    "Dexcom GL",
                    "HR",
                    "Calories (Activity)",
                ],
            )

            if data.empty:
                logger.warning(f" No data in {target_filename}")
                return {}

            for _, row in data.iterrows():
                record_id = str(uuid4())
                timestamp_str = str(row.get("Timestamp", "")).strip()
                timestamp = self._parse_timestamp(timestamp_str)

                libre_gl = row.get("Libre GL")
                dexcom_gl = row.get("Dexcom GL")

                if pd.notna(libre_gl):
                    glucose_level = float(libre_gl)
                    device_type = "Libre"
                elif pd.notna(dexcom_gl):
                    glucose_level = float(dexcom_gl)
                    device_type = "Dexcom"
                else:
                    continue

                hr = row.get("HR")
                calories = row.get("Calories (Activity)")

                metric_record = {
                    "record_id": record_id,
                    "timestamp": timestamp,
                    "device_type": device_type,
                    "glucose_level": glucose_level,
                    "heart_rate": int(float(hr)) if pd.notna(hr) else None,
                    "calories": float(calories) if pd.notna(calories) else None,
                }

                metrics[record_id] = metric_record

        except Exception as e:
            logger.error(f"Error processing {target_filename}: {e}")
            return {}

        return metrics

    def parse_clinics(self, filename: str = "clinics.csv") -> List[Dict[str, Any]]:
        """Parse clinics data from CSV."""
        logger.info(f"Reading clinics from {filename}")

        filepath = self.synthetic_dir / filename
        if not filepath.exists():
            logger.warning(f"Clinics file not found: {filepath}")
            return []

        clinics = []
        data = pd.read_csv(filepath, dtype={"clinic_code": str})

        for _, row in data.iterrows():
            raw_clinic_code = row.get("clinic_code")
            clinic_code = (
                str(raw_clinic_code).strip().zfill(5)
                if pd.notna(raw_clinic_code) and str(raw_clinic_code).strip() != ""
                else None
            )

            clinic_record = {
                "clinic_id": str(uuid4()),
                "name": row.get("name", "Unknown Clinic"),
                "address": row.get("address", "Unknown Address"),
                "phone_number": row.get("phone_number", "000-000-0000"),
                "clinic_code": clinic_code,
            }
            clinics.append(clinic_record)

        logger.info(f"Parsed {len(clinics)} clinics")
        return clinics

    def parse_clinicians(
        self, filename: str = "clinicians.csv"
    ) -> List[Dict[str, Any]]:
        """Parse clinicians data from CSV."""
        logger.info(f"Reading clinicians from {filename}")

        filepath = self.synthetic_dir / filename
        if not filepath.exists():
            logger.warning(f"Clinicians file not found: {filepath}")
            return []

        clinicians = []
        data = pd.read_csv(filepath)

        for _, row in data.iterrows():
            password = row.get("password_plain", self.generate_secure_password())

            license_from_csv = row.get("license_number", "")
            license_str = str(license_from_csv) if license_from_csv else ""
            if license_str and license_str.replace("-", "").isdigit():
                digits_only = "".join(filter(str.isdigit, license_str))
                license_number = digits_only.zfill(7)[:7]
            else:
                license_number = f"{random.randint(1000000, 9999999)}"

            clinician_record = {
                "clinician_id": str(uuid4()),
                "auth_user_id": str(uuid4()),
                "first_name": row.get("first_name", "Unknown"),
                "last_name": row.get("last_name", "Clinician"),
                "email": row.get(
                    "email", f"clinician{random.randint(1000, 9999)}@healthsync.ca"
                ),
                "license_number": license_number,
                "password": password,
                "password_hash": self._create_password_hash(password),
            }
            clinicians.append(clinician_record)

        logger.info(f"Parsed {len(clinicians)} clinicians")
        return clinicians

    def parse_medications(
        self, filename: str = "medications.csv"
    ) -> List[Dict[str, Any]]:
        """Parse medications data from CSV generated by synthetic data script."""
        logger.info(f"Reading medications from {filename}")

        filepath = self.synthetic_dir / filename
        if not filepath.exists():
            logger.warning(f"Medications file not found: {filepath}")
            return []

        medications = []
        data = pd.read_csv(filepath)

        for _, row in data.iterrows():
            medication_record = {
                "medication_id": row.get("medication_id", str(uuid4())),
                "name": row.get("name", "Unknown"),
                "strength": row.get("strength", "Unknown"),
                "form": row.get("form", "Unknown"),
                "route": row.get("route", "Unknown"),
            }
            medications.append(medication_record)

        logger.info(f"Parsed {len(medications)} medications")
        return medications

    def parse_allergies(self, filename: str = "allergies.csv") -> List[Dict[str, Any]]:
        """Parse common allergies data from CSV generated by synthetic data script."""
        logger.info(f"Reading allergies from {filename}")

        filepath = self.synthetic_dir / filename
        if not filepath.exists():
            logger.warning(f"Allergies file not found: {filepath}")
            return []

        allergies = []
        data = pd.read_csv(filepath)

        for _, row in data.iterrows():
            allergy_record = {
                "allergy_id": row.get("allergy_id", str(uuid4())),
                "allergen": row.get("allergen", "Unknown"),
                "severity": row.get("severity", "Unknown"),
                "reaction": row.get("reaction", "Unknown"),
            }
            allergies.append(allergy_record)

        logger.info(f"Parsed {len(allergies)} common allergies")
        return allergies

    def insert_clinics(self, clinics: List[Dict[str, Any]]) -> bool:
        """Insert clinics into the database."""
        if not clinics:
            logger.warning("No clinics to insert")
            return False

        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    for clinic in clinics:
                        cursor.execute(
                            """
                            INSERT INTO clinics (clinic_id, name, address, phone_number, clinic_code)
                            VALUES (%(clinic_id)s, %(name)s, %(address)s, %(phone_number)s, %(clinic_code)s)
                            ON CONFLICT (clinic_id) DO NOTHING
                            """,
                            clinic,
                        )
                        logger.info(
                            f"Inserted clinic: {clinic['name']} (code: {clinic.get('clinic_code', 'N/A')})"
                        )

            logger.info(f"Inserted {len(clinics)} clinics successfully")
            return True

        except Exception as e:
            logger.error(f"Error inserting clinics: {e}")
            return False

    def insert_clinicians(
        self, clinicians: List[Dict[str, Any]]
    ) -> tuple[bool, List[Dict[str, Any]]]:
        """Insert clinicians into the database."""
        if not clinicians:
            logger.warning("No clinicians to insert")
            return False, []

        inserted_clinicians = []
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    for clinician in clinicians:
                        cursor.execute(
                            """
                            SELECT user_id FROM auth_users WHERE email = %(email)s
                            """,
                            {"email": clinician["email"]},
                        )
                        existing_user = cursor.fetchone()

                        if existing_user:
                            logger.info(
                                f"Skipping clinician {clinician['email']} - email already exists"
                            )
                            continue

                        cursor.execute(
                            """
                            SELECT clinician_id FROM clinicians WHERE license_number = %(license_number)s
                            """,
                            {"license_number": clinician["license_number"]},
                        )
                        existing_license = cursor.fetchone()

                        if existing_license:
                            logger.info(
                                f"Skipping clinician {clinician['email']} - license_number {clinician['license_number']} already exists"
                            )
                            continue

                        cursor.execute(
                            """
                            INSERT INTO auth_users (user_id, email, password_hash, role)
                            VALUES (%(auth_user_id)s, %(email)s, %(password_hash)s, 'CLINICIAN'::user_role)
                            ON CONFLICT (user_id) DO NOTHING
                            """,
                            {
                                "auth_user_id": clinician["auth_user_id"],
                                "email": clinician["email"],
                                "password_hash": clinician["password_hash"],
                            },
                        )

                        cursor.execute(
                            """
                            INSERT INTO clinicians (clinician_id, auth_user_id, first_name, last_name, email, license_number)
                            VALUES (%(clinician_id)s, %(auth_user_id)s, %(first_name)s, %(last_name)s, %(email)s, %(license_number)s)
                            ON CONFLICT (clinician_id) DO NOTHING
                            """,
                            clinician,
                        )

                        inserted_clinicians.append(clinician)
                        logger.info(
                            f"✓ Inserted clinician: Dr. {clinician['first_name']} {clinician['last_name']} (license: {clinician['license_number']})"
                        )

            logger.info(f"Inserted {len(inserted_clinicians)} clinicians successfully")
            return True, inserted_clinicians

        except Exception as e:
            logger.error(f"Error inserting clinicians: {e}")
            return False, []

    def insert_patients(
        self, patients: List[Dict[str, Any]]
    ) -> tuple[bool, List[Dict[str, Any]]]:
        """Insert patients and their glucose/activity data into the database."""
        if not patients:
            logger.warning("No patients to insert")
            return False, []

        inserted_patients = []
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    for patient in patients:
                        cursor.execute(
                            """
                            SELECT user_id FROM auth_users WHERE email = %(email)s
                            """,
                            {"email": patient["email"]},
                        )
                        existing_user = cursor.fetchone()

                        if existing_user:
                            logger.info(
                                f"Skipping patient {patient['email']} - already exists"
                            )
                            continue

                        cursor.execute(
                            """
                            INSERT INTO auth_users (user_id, email, password_hash, role)
                            VALUES (%(user_id)s, %(email)s, %(password_hash)s, 'PATIENT'::user_role)
                            ON CONFLICT (user_id) DO NOTHING
                            """,
                            {
                                "user_id": patient["auth_user_id"],
                                "email": patient["email"],
                                "password_hash": patient["password_hash"],
                            },
                        )

                        cursor.execute(
                            """
                            INSERT INTO patients (
                                patient_id, auth_user_id, first_name, last_name, email,
                                phone_number, address, date_of_birth, phn, age, gender,
                                body_weight_lbs, height_inches, bmi, insulin_sensitivity
                            )
                            VALUES (
                                %(patient_id)s, %(auth_user_id)s, %(first_name)s, %(last_name)s, %(email)s,
                                %(phone_number)s, %(address)s, %(date_of_birth)s, %(phn)s, %(age)s, %(gender)s,
                                %(body_weight_lbs)s, %(height_inches)s, %(bmi)s, %(insulin_sensitivity)s
                            )
                            ON CONFLICT (patient_id) DO NOTHING
                            """,
                            {
                                "patient_id": patient["patient_id"],
                                "auth_user_id": patient["auth_user_id"],
                                "first_name": patient["first_name"],
                                "last_name": patient["last_name"],
                                "email": patient["email"],
                                "phone_number": patient["phone_number"],
                                "address": patient["address"],
                                "date_of_birth": patient["date_of_birth"],
                                "phn": patient["phn"],
                                "age": patient["age"],
                                "gender": patient["gender"],
                                "body_weight_lbs": patient["body_weight_lbs"],
                                "height_inches": patient["height_inches"],
                                "bmi": patient["bmi"],
                                "insulin_sensitivity": patient["insulin_sensitivity"],
                            },
                        )

                        device_type_raw = (
                            "Libre"
                            if any(
                                record["device_type"] == "Libre"
                                for record in patient["glucose_data"].values()
                            )
                            else "Dexcom"
                        )

                        device_type_map = {
                            "Libre": "LibreSensor",
                            "Dexcom": "Dexcom",
                        }

                        device_type_enum = device_type_map.get(
                            device_type_raw, "Dexcom"
                        )

                        device_id = str(uuid4())
                        serial_number = (
                            f"SN-{device_type_raw.upper()}-{secrets.token_hex(4).upper()}"
                        )

                        cursor.execute(
                            """
                            INSERT INTO devices (device_id, patient_id, type, serial_number, status, created_at)
                            VALUES (%(device_id)s, %(patient_id)s, %(type)s::device_type, %(serial_number)s, 'ACTIVE'::device_status, NOW())
                            ON CONFLICT (serial_number) DO NOTHING
                            """,
                            {
                                "device_id": device_id,
                                "patient_id": patient["patient_id"],
                                "type": device_type_enum,
                                "serial_number": serial_number,
                            },
                        )

                        glucose_count = 0
                        activity_count = 0

                        for record in patient["glucose_data"].values():
                            cursor.execute(
                                """
                                INSERT INTO glucose_readings (
                                    reading_id, patient_id, device_id, timestamp, value, unit, device_type, acquired_at
                                )
                                VALUES (
                                    %(reading_id)s, %(patient_id)s, %(device_id)s, %(timestamp)s,
                                    %(value)s, 'mg/dL'::glucose_unit, %(device_type)s, NOW()
                                )
                                """,
                                {
                                    "reading_id": record["record_id"],
                                    "patient_id": patient["patient_id"],
                                    "device_id": device_id,
                                    "timestamp": record["timestamp"],
                                    "value": record["glucose_level"],
                                    "device_type": record["device_type"],
                                },
                            )
                            glucose_count += 1

                            if (
                                record["heart_rate"] is not None
                                or record["calories"] is not None
                            ):
                                cursor.execute(
                                    """
                                    INSERT INTO activity_data (
                                        activity_id, patient_id, reading_id, reading_timestamp, timestamp,
                                        heart_rate, calories_burned, created_at
                                    )
                                    VALUES (
                                        %(activity_id)s, %(patient_id)s, %(reading_id)s, %(reading_timestamp)s, %(timestamp)s,
                                        %(heart_rate)s, %(calories)s, NOW()
                                    )
                                    """,
                                    {
                                        "activity_id": str(uuid4()),
                                        "patient_id": patient["patient_id"],
                                        "reading_id": record["record_id"],
                                        "reading_timestamp": record["timestamp"],
                                        "timestamp": record["timestamp"],
                                        "heart_rate": record["heart_rate"],
                                        "calories": record["calories"],
                                    },
                                )
                                activity_count += 1

                        inserted_patients.append(patient)

                        logger.info(
                            f"✓ Patient credentials: {patient['first_name']} {patient['last_name']} | "
                            f"{patient['email']} | password: {patient['password']}"
                        )

                        logger.info(
                            f"Inserted patient {patient['first_name']} {patient['last_name']} - "
                            f"{glucose_count} glucose readings, {activity_count} activity records"
                        )

            logger.info(f"Inserted {len(inserted_patients)} patients successfully")
            return True, inserted_patients

        except Exception as e:
            logger.error(f"Error inserting patients: {e}")
            import traceback

            traceback.print_exc()
            return False, []

    def insert_medications(self, medications: List[Dict[str, Any]]) -> bool:
        """Insert medications into the database."""
        if not medications:
            logger.warning("No medications to insert")
            return False
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    for med in medications:
                        cursor.execute(
                            """
                            INSERT INTO medications (medication_id, name, strength, form, route)
                            VALUES (%(medication_id)s, %(name)s, %(strength)s, %(form)s, %(route)s)
                            ON CONFLICT (medication_id) DO NOTHING
                            """,
                            med,
                        )
            logger.info(f"✓ Inserted {len(medications)} medications successfully")
            return True
        except Exception as e:
            logger.error(f"Error inserting medications: {e}")
            import traceback

            traceback.print_exc()
            return False

    def assign_clinicians_to_clinics(
        self, clinicians: List[Dict[str, Any]], clinics: List[Dict[str, Any]]
    ) -> bool:
        """Assign clinicians to clinics."""
        if not clinicians or not clinics:
            logger.warning("Need both clinicians and clinics")
            return False
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    total = 0
                    for clinician in clinicians:
                        num_clinics = random.randint(1, min(3, len(clinics)))
                        for clinic in random.sample(clinics, num_clinics):
                            cursor.execute(
                                """
                                INSERT INTO clinician_clinic (id, clinician_id, clinic_id, start_date)
                                VALUES (%(id)s, %(clinician_id)s, %(clinic_id)s, %(start_date)s)
                                ON CONFLICT DO NOTHING
                                """,
                                {
                                    "id": str(uuid4()),
                                    "clinician_id": clinician["clinician_id"],
                                    "clinic_id": clinic["clinic_id"],
                                    "start_date": self.fake.date_between(
                                        start_date="-2y", end_date="today"
                                    ),
                                },
                            )
                            total += 1
                        logger.info(
                            f"✓ Assigned Dr. {clinician['first_name']} {clinician['last_name']} to {num_clinics} clinic(s)"
                        )
            logger.info(f"Created {total} clinician-clinic assignments")
            return True
        except Exception as e:
            logger.error(f"Error assigning clinicians to clinics: {e}")
            import traceback

            traceback.print_exc()
            return False

    def assign_clinicians_to_patients(
        self, patients: List[Dict[str, Any]], clinicians: List[Dict[str, Any]]
    ) -> bool:
        """Assign clinicians to patients via access_permissions."""
        if not patients or not clinicians:
            logger.warning("Need both patients and clinicians")
            return False
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    total = 0
                    for patient in patients:
                        num_clinicians = random.randint(1, min(2, len(clinicians)))
                        for clinician in random.sample(clinicians, num_clinicians):
                            cursor.execute(
                                """
                                INSERT INTO access_permissions (permission_id, patient_id, clinician_id, status, granted_at)
                                VALUES (%(permission_id)s, %(patient_id)s, %(clinician_id)s, 'APPROVED'::permission_status, NOW())
                                ON CONFLICT DO NOTHING
                                """,
                                {
                                    "permission_id": str(uuid4()),
                                    "patient_id": patient["patient_id"],
                                    "clinician_id": clinician["clinician_id"],
                                },
                            )
                            total += 1
                        logger.info(
                            f"✓ Assigned {patient['first_name']} {patient['last_name']} to {num_clinicians} clinician(s)"
                        )
            logger.info(f"Created {total} clinician-patient permissions")
            return True
        except Exception as e:
            logger.error(f"Error assigning clinicians to patients: {e}")
            import traceback

            traceback.print_exc()
            return False

    def create_prescriptions(
        self,
        patients: List[Dict[str, Any]],
        clinicians: List[Dict[str, Any]],
        medications: List[Dict[str, Any]],
    ) -> bool:
        """Create prescriptions for patients."""
        if not patients or not clinicians or not medications:
            logger.warning("Need patients, clinicians, and medications")
            return False
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    rx_count = 0
                    item_count = 0
                    for patient in patients:
                        if random.random() < 0.7:
                            cursor.execute(
                                "SELECT clinician_id FROM access_permissions WHERE patient_id = %s LIMIT 1",
                                (patient["patient_id"],),
                            )
                            result = cursor.fetchone()
                            if not result:
                                continue
                            clinician_id = result[0]

                            cursor.execute(
                                "SELECT first_name, last_name FROM clinicians WHERE clinician_id = %s",
                                (clinician_id,),
                            )
                            clinician_result = cursor.fetchone()
                            clinician_name = (
                                f"Dr. {clinician_result[0]} {clinician_result[1]}"
                                if clinician_result
                                else "Dr. Unknown"
                            )

                            prescription_id = str(uuid4())
                            cursor.execute(
                                """
                                INSERT INTO prescriptions (prescription_id, patient_id, clinician_id, issued_at, clinician_name)
                                VALUES (%(prescription_id)s, %(patient_id)s, %(clinician_id)s, %(issued_at)s, %(clinician_name)s)
                                """,
                                {
                                    "prescription_id": prescription_id,
                                    "patient_id": patient["patient_id"],
                                    "clinician_id": clinician_id,
                                    "issued_at": self.fake.date_between(
                                        start_date="-1y", end_date="today"
                                    ),
                                    "clinician_name": clinician_name,
                                },
                            )
                            rx_count += 1

                            num_meds = random.randint(1, 3)
                            for med in random.sample(
                                medications, min(num_meds, len(medications))
                            ):
                                cursor.execute(
                                    """
                                    INSERT INTO prescription_items (item_id, prescription_id, medication_id, medication_name, dose, sig, duration)
                                    VALUES (%(item_id)s, %(prescription_id)s, %(medication_id)s, %(medication_name)s, %(dose)s, %(sig)s, %(duration)s)
                                    """,
                                    {
                                        "item_id": str(uuid4()),
                                        "prescription_id": prescription_id,
                                        "medication_id": med["medication_id"],
                                        "medication_name": med["name"],
                                        "dose": med["strength"],
                                        "sig": random.choice(
                                            [
                                                "Take 1 tablet daily",
                                                "Take 2 tablets twice daily",
                                                "Inject once daily",
                                            ]
                                        ),
                                        "duration": random.choice(
                                            ["30 days", "60 days", "90 days"]
                                        ),
                                    },
                                )
                                item_count += 1
                            logger.info(
                                f"✓ Created prescription for {patient['first_name']} {patient['last_name']} ({num_meds} medications)"
                            )
            logger.info(f"Created {rx_count} prescriptions with {item_count} items")
            return True
        except Exception as e:
            logger.error(f"Error creating prescriptions: {e}")
            import traceback

            traceback.print_exc()
            return False

    def create_patient_medications(
        self, patients: List[Dict[str, Any]], medications: List[Dict[str, Any]]
    ) -> bool:
        """Create current medication records forpatients."""
        if not patients or not medications:
            logger.warning("Need patients and medications")
            return False
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    total = 0
                    for patient in patients:
                        if random.random() < 0.8:
                            num_meds = random.randint(1, 3)
                            for med in random.sample(
                                medications, min(num_meds, len(medications))
                            ):
                                end_date = None
                                if random.random() < 0.2:
                                    end_date = self.fake.date_between(
                                        start_date="-6m", end_date="today"
                                    )
                                cursor.execute(
                                    """
                                    INSERT INTO patient_medications (id, patient_id, medication_id, start_date, end_date)
                                    VALUES (%(id)s, %(patient_id)s, %(medication_id)s, %(start_date)s, %(end_date)s)
                                    """,
                                    {
                                        "id": str(uuid4()),
                                        "patient_id": patient["patient_id"],
                                        "medication_id": med["medication_id"],
                                        "start_date": self.fake.date_between(
                                            start_date="-2y", end_date="-30d"
                                        ),
                                        "end_date": end_date,
                                    },
                                )
                                total += 1
                            logger.info(
                                f"✓ Added {num_meds} medication(s) for {patient['first_name']} {patient['last_name']}"
                            )
            logger.info(f"Created {total} patient medication records")
            return True
        except Exception as e:
            logger.error(f"Error creating patient medications: {e}")
            import traceback

            traceback.print_exc()
            return False

    def create_allergies(
        self, patients: List[Dict[str, Any]], allergies: List[Dict[str, Any]]
    ) -> bool:
        """Create allergy records for patients."""
        if not patients:
            logger.warning("No patients to create allergies for")
            return False
        if not allergies:
            logger.warning("No allergies data available")
            return False
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    total = 0
                    for patient in patients:
                        if random.random() < 0.4:
                            num_allergies = random.randint(1, 3)
                            for allergy in random.sample(
                                allergies, min(num_allergies, len(allergies))
                            ):
                                cursor.execute(
                                    """
                                    INSERT INTO allergies (allergy_id, patient_id, allergen, reaction, severity, created_at)
                                    VALUES (%(allergy_id)s, %(patient_id)s, %(allergen)s, %(reaction)s, %(severity)s, NOW())
                                    """,
                                    {
                                        "allergy_id": str(uuid4()),
                                        "patient_id": patient["patient_id"],
                                        "allergen": allergy["allergen"],
                                        "reaction": allergy["reaction"],
                                        "severity": allergy["severity"],
                                    },
                                )
                                total += 1
                            logger.info(
                                f"✓ Added {num_allergies} allergy/allergies for {patient['first_name']} {patient['last_name']}"
                            )
            logger.info(f"Created {total} allergy records")
            return True
        except Exception as e:
            logger.error(f"Error creating allergies: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _calculate_dob(self, age_str: Optional[str]) -> Optional[date]:
        """Calculate date of birth from age string."""
        if not age_str:
            return None

        try:
            age = int(float(age_str))
            return self.fake.date_of_birth(minimum_age=age, maximum_age=age)
        except (ValueError, TypeError):
            return None

    def _create_password_hash(self, password: str) -> str:
        """Create a bcrypt password hash."""
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def _parse_timestamp(self, ts_str: Optional[str]) -> datetime:
        """Parse timestamp from various formats."""
        if not ts_str:
            return datetime.utcnow()

        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

        try:
            return datetime.fromtimestamp(float(ts_str))
        except (ValueError, TypeError):
            pass

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse timestamp: {ts_str}, using current time")
        return datetime.utcnow()


def main():
    parser = argparse.ArgumentParser(
        description="Seed the HealthSYNC database from CSV files."
    )
    parser.add_argument(
        "--bio-file",
        type=str,
        default="bio.csv",
        help="CSV file containing biometric data (default: bio.csv)",
    )
    parser.add_argument(
        "--clinics-file",
        type=str,
        default="clinics.csv",
        help="CSV file containing clinics data (default: clinics.csv)",
    )
    parser.add_argument(
        "--clinicians-file",
        type=str,
        default="clinicians.csv",
        help="CSV file containing clinicians data (default: clinicians.csv)",
    )
    parser.add_argument(
        "--medications-file",
        type=str,
        default="medications.csv",
        help="CSV file containing medications data (default: medications.csv)",
    )
    parser.add_argument(
        "--allergies-file",
        type=str,
        default="allergies.csv",
        help="CSV file containing allergies data (default: allergies.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview data without inserting into database",
    )
    args = parser.parse_args()

    data_loader = DataLoader()

    logger.info("=" * 70)
    logger.info(" HealthSYNC Database Seeder")
    logger.info("=" * 70)

    clinics = data_loader.parse_clinics(args.clinics_file)
    clinicians = data_loader.parse_clinicians(args.clinicians_file)
    patients = data_loader.parse_bio_data(args.bio_file)
    medications = data_loader.parse_medications(args.medications_file)
    allergies = data_loader.parse_allergies(args.allergies_file)

    if args.dry_run:
        logger.info("\nDRY RUN MODE - No data will be inserted\n")

        logger.info("Data Summary:")
        logger.info(f"  - Clinics: {len(clinics)}")
        logger.info(f"  - Clinicians: {len(clinicians)}")
        logger.info(f"  - Patients: {len(patients)}")
        logger.info(f"  - Medications: {len(medications)}")
        logger.info(f"  - Common Allergies: {len(allergies)}")

        if patients:
            total_glucose = sum(len(p["glucose_data"]) for p in patients)
            logger.info(f"  - Total Glucose Readings: {total_glucose:,}")

        if patients:
            sample = patients[0]
            logger.info("\nSample Patient:")
            logger.info(f"  Name: {sample['first_name']} {sample['last_name']}")
            logger.info(f"  Email: {sample['email']}")
            logger.info(f"  Password: {sample['password']}")
            logger.info(f"  Address: {sample['address']}")
            logger.info(f"  DOB: {sample['date_of_birth']}")
            logger.info(f"  Gender: {sample['gender']}")
            logger.info(f"  BMI: {sample['bio_data'].get('bmi', 'N/A')}")
            logger.info(f"  CGM Records: {len(sample['glucose_data'])}")

        logger.info("\nDry run completed. Use --bio-file bio.csv to insert data.")

    else:
        logger.info("\nInserting data into database...\n")
        success = True

        inserted_clinicians = []
        inserted_patients = []

        if clinics:
            logger.info("\n[1/9] Inserting clinics...")
            success = data_loader.insert_clinics(clinics) and success

        if clinicians:
            logger.info("\n[2/9] Inserting clinicians...")
            clinician_success, inserted_clinicians = data_loader.insert_clinicians(
                clinicians
            )
            success = clinician_success and success

        if patients:
            logger.info("\n[3/9] Inserting patients and glucose data...")
            patient_success, inserted_patients = data_loader.insert_patients(patients)
            success = patient_success and success

        if medications:
            logger.info("\n[4/9] Inserting medications...")
            success = data_loader.insert_medications(medications) and success

        if success and inserted_clinicians and clinics:
            logger.info("\n[5/9] Assigning clinicians to clinics...")
            success = (
                data_loader.assign_clinicians_to_clinics(inserted_clinicians, clinics)
                and success
            )

        if success and inserted_clinicians and inserted_patients:
            logger.info("\n[6/9] Assigning clinicians to patients...")
            success = (
                data_loader.assign_clinicians_to_patients(
                    inserted_patients, inserted_clinicians
                )
                and success
            )

        if success and inserted_patients and inserted_clinicians and medications:
            logger.info("\n[7/9] Creating prescriptions...")
            success = (
                data_loader.create_prescriptions(
                    inserted_patients, inserted_clinicians, medications
                )
                and success
            )

        if success and inserted_patients and medications:
            logger.info("\n[8/9] Creating patient medication records...")
            success = (
                data_loader.create_patient_medications(inserted_patients, medications)
                and success
            )

        if success and inserted_patients and allergies:
            logger.info("\n[9/9] Creating patient allergies...")
            success = (
                data_loader.create_allergies(inserted_patients, allergies) and success
            )

        if success:
            logger.info("\n" + "=" * 70)
            logger.info(" All data inserted successfully!")
            logger.info("=" * 70)
            logger.info("\nDatabase Summary:")
            logger.info(f"  - {len(clinics)} clinics")
            logger.info(f"  - {len(inserted_clinicians)} clinicians")
            logger.info(f"  - {len(inserted_patients)} patients")
            logger.info(f"  - {len(medications)} medications")
            total_glucose = sum(len(p["glucose_data"]) for p in inserted_patients)
            logger.info(f"  - {total_glucose:,} glucose readings")
            logger.info("\nRelationships Created:")
            logger.info("  Clinician-clinic assignments")
            logger.info("  Clinician-patient access permissions")
            logger.info("  Prescriptions with medication items")
            logger.info("  Current patient medications")
            logger.info("  Patient allergies")
            logger.info("\n💡 Login credentials logged during insertion")
        else:
            logger.error("\n Some data insertion failed. Check logs above.")
            sys.exit(1)


if __name__ == "__main__":
    main()