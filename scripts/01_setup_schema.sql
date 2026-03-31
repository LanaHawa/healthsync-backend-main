-- ============================================================
-- HealthSYNC FULL SCHEMA (Clean + Complete)
-- Replaces: backend/scripts/create_tables.sql
-- ============================================================
-- =========================
-- Extensions
-- =========================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- If you use TimescaleDB container/image, keep this:
CREATE EXTENSION IF NOT EXISTS "timescaledb";
-- =========================
-- ENUMS
-- =========================
DO $$ BEGIN IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'user_role'
) THEN CREATE TYPE user_role AS ENUM ('PATIENT', 'CLINICIAN', 'ADMIN');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'permission_status'
) THEN CREATE TYPE permission_status AS ENUM ('REQUESTED', 'APPROVED', 'REJECTED', 'REVOKED');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'stakeholder_type'
) THEN CREATE TYPE stakeholder_type AS ENUM ('PATIENT', 'CLINICIAN', 'SYSTEM');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'action_status'
) THEN CREATE TYPE action_status AS ENUM ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'device_type'
) THEN CREATE TYPE device_type AS ENUM ('Dexcom', 'LibreSensor');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'device_status'
) THEN CREATE TYPE device_status AS ENUM ('ACTIVE', 'INACTIVE', 'DISCONNECTED', 'RETIRED');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'avs_channel'
) THEN CREATE TYPE avs_channel AS ENUM ('EMAIL', 'PRINT');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'annotation_type'
) THEN CREATE TYPE annotation_type AS ENUM ('TEXT', 'HIGHLIGHT', 'COMMENT', 'MARKER');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'visualization_type'
) THEN CREATE TYPE visualization_type AS ENUM (
  'GLUCOSE_TREND',
  'TIME_IN_RANGE',
  'HEATMAP',
  'SUMMARY'
);
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'abnormal_event_type'
) THEN CREATE TYPE abnormal_event_type AS ENUM (
  'HYPOGLYCEMIA',
  'HYPERGLYCEMIA',
  'RAPID_DROP',
  'RAPID_RISE'
);
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'report_type'
) THEN CREATE TYPE report_type AS ENUM ('VISIT', 'WEEKLY', 'MONTHLY', 'CUSTOM');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'agenda_status'
) THEN CREATE TYPE agenda_status AS ENUM ('OPEN', 'DONE', 'SKIPPED');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'glucose_unit'
) THEN CREATE TYPE glucose_unit AS ENUM ('mg/dL', 'mmol/L');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'notification_type'
) THEN CREATE TYPE notification_type AS ENUM (
  'ACCESS_REQUEST',
  'ACCESS_APPROVED',
  'ACCESS_REJECTED'
);
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'visit_type_enum'
) THEN CREATE TYPE visit_type_enum AS ENUM ('FOLLOW_UP', 'CHECK_IN', 'OTHER');
END IF;
END $$;
-- =========================
-- AUTH / CONFIG
-- =========================
CREATE TABLE IF NOT EXISTS auth_users (
  user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role user_role NOT NULL,
  mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  identity_provider TEXT NOT NULL DEFAULT 'local',
  last_login_at TIMESTAMPTZ NULL
);
CREATE TABLE IF NOT EXISTS user_preferences (
  preference_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  auth_user_id UUID NOT NULL UNIQUE REFERENCES auth_users(user_id) ON DELETE CASCADE,
  language TEXT NOT NULL DEFAULT 'en',
  color_palette TEXT NOT NULL DEFAULT 'default',
  simplified_view_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  time_format TEXT NOT NULL DEFAULT '24h',
  date_format TEXT NOT NULL DEFAULT 'YYYY-MM-DD',
  default_glucose_unit glucose_unit NOT NULL DEFAULT 'mg/dL',
  has_completed_onboarding BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS system_configs (
  config_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  config_key TEXT NOT NULL UNIQUE,
  config_value TEXT NOT NULL,
  description TEXT NULL,
  updated_by UUID NULL REFERENCES auth_users(user_id) ON DELETE
  SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- =========================
-- CLINICS / CLINICIANS / PATIENTS
-- =========================
CREATE TABLE IF NOT EXISTS clinics (
  clinic_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  address TEXT NOT NULL,
  phone_number TEXT NOT NULL,
  last_number TEXT NULL,
  clinic_code CHAR(5) NULL,
  CONSTRAINT clinics_code_5_digits CHECK (
    clinic_code IS NULL
    OR clinic_code ~ '^[0-9]{5}$'
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS clinics_clinic_code_uq ON clinics (clinic_code);
CREATE TABLE IF NOT EXISTS clinicians (
  clinician_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  auth_user_id UUID NOT NULL UNIQUE REFERENCES auth_users(user_id) ON DELETE CASCADE,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT NOT NULL,
  license_number TEXT NOT NULL
);
-- if you truly want 7 digits only, keep it; otherwise remove it:
DO $$ BEGIN IF NOT EXISTS (
  SELECT 1
  FROM pg_constraint
  WHERE conname = 'clinicians_license_7_digits'
) THEN
ALTER TABLE clinicians
ADD CONSTRAINT clinicians_license_7_digits CHECK (license_number ~ '^[0-9]{7}$');
END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS clinicians_license_number_uq ON clinicians (license_number);
CREATE TABLE IF NOT EXISTS patients (
  patient_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  auth_user_id UUID NOT NULL UNIQUE REFERENCES auth_users(user_id) ON DELETE CASCADE,
  -- Keep email here because your seeder inserts it
  email TEXT NOT NULL,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  phone_number TEXT NULL,
  -- optional (matches your latest requirement)
  address TEXT NOT NULL,
  -- optional relations (you said removed from signup UI, but DB can keep)
  primary_clinician_id UUID NULL REFERENCES clinicians(clinician_id) ON DELETE
  SET NULL,
    clinic_id UUID NULL REFERENCES clinics(clinic_id) ON DELETE
  SET NULL,
    -- healthcare fields used by seeder
    date_of_birth DATE NULL,
    age INT NULL,
    gender TEXT NULL,
    body_weight_lbs DOUBLE PRECISION NULL,
    height_inches DOUBLE PRECISION NULL,
    bmi DOUBLE PRECISION NULL,
    insulin_sensitivity DOUBLE PRECISION NULL,
    -- PHN (you want to show as Health Card Number in UI)
    phn CHAR(9) NULL,
    CONSTRAINT patients_phn_9_digits CHECK (
      phn IS NULL
      OR phn ~ '^[0-9]{9}$'
    ),
    deleted_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS patients_phn_uq ON patients (phn);
CREATE INDEX IF NOT EXISTS idx_patients_auth_user ON patients(auth_user_id);
-- ClinicianClinic bridge
CREATE TABLE IF NOT EXISTS clinician_clinic (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  clinician_id UUID NOT NULL REFERENCES clinicians(clinician_id) ON DELETE CASCADE,
  clinic_id UUID NOT NULL REFERENCES clinics(clinic_id) ON DELETE CASCADE,
  start_date DATE NULL,
  end_date DATE NULL,
  role TEXT NULL,
  UNIQUE (clinician_id, clinic_id)
);
-- AccessPermission
CREATE TABLE IF NOT EXISTS access_permissions (
  permission_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  clinician_id UUID NOT NULL REFERENCES clinicians(clinician_id) ON DELETE RESTRICT,
  status permission_status NOT NULL DEFAULT 'REQUESTED',
  requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  granted_at TIMESTAMPTZ NULL,
  revoked_at TIMESTAMPTZ NULL,
  notes TEXT NULL,
  UNIQUE (patient_id, clinician_id)
);
CREATE INDEX IF NOT EXISTS idx_access_permissions_patient ON access_permissions(patient_id);
CREATE INDEX IF NOT EXISTS idx_access_permissions_clinician ON access_permissions(clinician_id);
-- =========================
-- NOTIFICATIONS
-- =========================
CREATE TABLE IF NOT EXISTS notifications (
  notification_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  recipient_user_id UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
  type notification_type NOT NULL,
  title TEXT NOT NULL,
  body TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  read_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient_created ON notifications (recipient_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread ON notifications (recipient_user_id)
WHERE is_read = FALSE;
-- =========================
-- AUDIT LOG
-- =========================
-- NOTE: Composite PK includes timestamp for TimescaleDB partitioning requirement
CREATE TABLE IF NOT EXISTS audit_log_entries (
  log_id UUID NOT NULL DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT,
  patient_id UUID NULL REFERENCES patients(patient_id) ON DELETE
  SET NULL,
    action_type TEXT NOT NULL,
    target_id TEXT NULL,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (log_id, "timestamp")
);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_log_entries(user_id, "timestamp");
CREATE INDEX IF NOT EXISTS idx_audit_patient_ts ON audit_log_entries(patient_id, "timestamp");
-- =========================
-- HEALTH APPS / DEVICES / READINGS
-- =========================
CREATE TABLE IF NOT EXISTS health_apps (
  app_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  source_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  device_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  type device_type NOT NULL,
  model TEXT NULL,
  serial_number TEXT NOT NULL UNIQUE,
  status device_status NOT NULL DEFAULT 'ACTIVE',
  linked_app_name TEXT NULL,
  last_sync_at TIMESTAMPTZ NULL,
  app_id UUID NULL REFERENCES health_apps(app_id) ON DELETE
  SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_devices_patient ON devices(patient_id);
CREATE TABLE IF NOT EXISTS glucose_readings (
  reading_id UUID NOT NULL DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  device_id UUID NOT NULL REFERENCES devices(device_id) ON DELETE RESTRICT,
  "timestamp" TIMESTAMPTZ NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  unit glucose_unit NOT NULL,
  -- Keep these for your seeder:
  device_type TEXT NULL,
  source_type TEXT NULL,
  acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (reading_id, "timestamp")
);
CREATE INDEX IF NOT EXISTS idx_glucose_patient_ts ON glucose_readings(patient_id, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_glucose_device_ts ON glucose_readings(device_id, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_glucose_device_ts ON glucose_readings(device_id, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_glucose_value_ts ON glucose_readings(value, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_glucose_value_ts ON glucose_readings(value, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_glucose_device_type ON glucose_readings(device_type, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_glucose_device_type ON glucose_readings(device_type, "timestamp" DESC);
-- Timescale hypertable (safe: only runs if extension exists)
DO $$ BEGIN IF EXISTS (
  SELECT 1
  FROM pg_extension
  WHERE extname = 'timescaledb'
) THEN PERFORM create_hypertable(
  'glucose_readings',
  'timestamp',
  if_not_exists => TRUE
);
END IF;
END $$;
-- Activity table (used by seeder)
-- NOTE: No FK to glucose_readings because TimescaleDB hypertables cannot reference other hypertables
-- NOTE: Composite PK includes timestamp for TimescaleDB partitioning requirement
CREATE TABLE IF NOT EXISTS activity_data (
  activity_id UUID NOT NULL DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  reading_id UUID NULL,
  reading_timestamp TIMESTAMPTZ NULL,
  "timestamp" TIMESTAMPTZ NOT NULL,
  heart_rate INT NULL,
  calories_burned DOUBLE PRECISION NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (activity_id, "timestamp")
);
CREATE INDEX IF NOT EXISTS idx_activity_patient_time ON activity_data(patient_id, "timestamp");
DO $$ BEGIN IF EXISTS (
  SELECT 1
  FROM pg_extension
  WHERE extname = 'timescaledb'
) THEN PERFORM create_hypertable(
  'activity_data',
  'timestamp',
  if_not_exists => TRUE
);
END IF;
END $$;
-- =========================
-- PATIENT RECORD
-- =========================
CREATE TABLE IF NOT EXISTS patient_records (
  record_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL UNIQUE REFERENCES patients(patient_id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_sync_start TIMESTAMPTZ NULL,
  last_sync_end TIMESTAMPTZ NULL,
  summary_notes TEXT NULL
);
-- =========================
-- VISITS + SUMMARIES
-- =========================
CREATE TABLE IF NOT EXISTS visits (
  visit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  clinician_id UUID NOT NULL REFERENCES clinicians(clinician_id) ON DELETE RESTRICT,
  clinic_id UUID NULL REFERENCES clinics(clinic_id) ON DELETE
  SET NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NULL,
    visit_type visit_type_enum NOT NULL,
    visit_type_other_text TEXT NULL,
    notes TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT visit_other_requires_text CHECK (
      visit_type <> 'OTHER'
      OR visit_type_other_text IS NOT NULL
    )
);
CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id);
CREATE INDEX IF NOT EXISTS idx_visits_patient_time ON visits(patient_id, start_time);
CREATE TABLE IF NOT EXISTS visit_summaries (
  summary_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL UNIQUE REFERENCES visits(visit_id) ON DELETE RESTRICT,
  created_by UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  clinical_findings TEXT NOT NULL,
  decisions TEXT NOT NULL,
  follow_up_plan TEXT NULL
);
CREATE TABLE IF NOT EXISTS after_visit_summaries (
  avs_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL UNIQUE REFERENCES visits(visit_id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  generated_by UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT,
  delivered_via avs_channel NOT NULL,
  content TEXT NOT NULL
);
-- Composite PNG screenshots captured by clinicians during a visit
CREATE TABLE IF NOT EXISTS visit_annotation_images (
  image_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL REFERENCES visits(visit_id) ON DELETE RESTRICT,
  created_by UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT,
  chart_key TEXT NOT NULL,
  -- e.g. AGP | TIR | LIFESTYLE
  chart_title TEXT NOT NULL,
  label TEXT NULL,
  image_data TEXT NOT NULL,
  -- base64 PNG data URL
  saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vai_visit ON visit_annotation_images(visit_id);
-- =========================
-- VISUALIZATIONS / ANNOTATIONS / BOOKMARKS / AGENDA
-- =========================
CREATE TABLE IF NOT EXISTS visualizations (
  visualization_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  visit_id UUID NULL REFERENCES visits(visit_id) ON DELETE
  SET NULL,
    type visualization_type NOT NULL,
    title TEXT NOT NULL,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_visualizations_patient ON visualizations(patient_id);
CREATE TABLE IF NOT EXISTS annotations (
  annotation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL REFERENCES visits(visit_id) ON DELETE RESTRICT,
  visualization_id UUID NOT NULL REFERENCES visualizations(visualization_id) ON DELETE RESTRICT,
  created_by UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT,
  type annotation_type NOT NULL,
  content TEXT NOT NULL,
  time_start TIMESTAMPTZ NULL,
  time_end TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_annotations_visit ON annotations(visit_id);
CREATE INDEX IF NOT EXISTS idx_annotations_visualization ON annotations(visualization_id);
CREATE TABLE IF NOT EXISTS bookmarks (
  bookmark_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL REFERENCES visits(visit_id) ON DELETE RESTRICT,
  visualization_id UUID NOT NULL REFERENCES visualizations(visualization_id) ON DELETE RESTRICT,
  created_by UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT,
  label TEXT NOT NULL,
  time_start TIMESTAMPTZ NOT NULL,
  time_end TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_visit ON bookmarks(visit_id);
CREATE TABLE IF NOT EXISTS agenda_items (
  agenda_item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL REFERENCES visits(visit_id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  description TEXT NULL,
  order_index INT NOT NULL DEFAULT 0,
  status agenda_status NOT NULL DEFAULT 'OPEN',
  bookmark_id UUID NULL REFERENCES bookmarks(bookmark_id) ON DELETE
  SET NULL
);
CREATE INDEX IF NOT EXISTS idx_agenda_visit ON agenda_items(visit_id);
-- =========================
-- ACTION ITEMS
-- =========================
CREATE TABLE IF NOT EXISTS action_items (
  action_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL REFERENCES visits(visit_id) ON DELETE RESTRICT,
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  description TEXT NOT NULL,
  owner_type stakeholder_type NOT NULL,
  status action_status NOT NULL DEFAULT 'OPEN',
  due_date TIMESTAMPTZ NULL,
  follow_up_plan TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by UUID NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_action_items_visit ON action_items(visit_id);
CREATE INDEX IF NOT EXISTS idx_action_items_patient ON action_items(patient_id);
-- =========================
-- REPORTS
-- =========================
CREATE TABLE IF NOT EXISTS reports (
  report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  clinician_id UUID NOT NULL REFERENCES clinicians(clinician_id) ON DELETE RESTRICT,
  type report_type NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id);
CREATE TABLE IF NOT EXISTS report_visualizations (
  report_id UUID NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
  visualization_id UUID NOT NULL REFERENCES visualizations(visualization_id) ON DELETE CASCADE,
  PRIMARY KEY (report_id, visualization_id)
);
-- =========================
-- ABNORMAL EVENTS
-- =========================
CREATE TABLE IF NOT EXISTS abnormal_events (
  event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  visit_id UUID NULL REFERENCES visits(visit_id) ON DELETE
  SET NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    type abnormal_event_type NOT NULL,
    severity INT NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_abnormal_patient_time ON abnormal_events(patient_id, start_time);
-- Junction table linking events to glucose readings
-- NOTE: FK to glucose_readings is allowed because this table is NOT a hypertable
CREATE TABLE IF NOT EXISTS abnormal_event_readings (
  event_id UUID NOT NULL REFERENCES abnormal_events(event_id) ON DELETE CASCADE,
  reading_id UUID NOT NULL,
  reading_timestamp TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (event_id, reading_id, reading_timestamp),
  FOREIGN KEY (reading_id, reading_timestamp) REFERENCES glucose_readings(reading_id, "timestamp") ON DELETE CASCADE
);
-- =========================
-- MEDICATIONS / PRESCRIPTIONS / ALLERGIES
-- =========================
CREATE TABLE IF NOT EXISTS medications (
  medication_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  strength TEXT NOT NULL,
  form TEXT NOT NULL,
  route TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patient_medications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  medication_id UUID NOT NULL REFERENCES medications(medication_id) ON DELETE RESTRICT,
  start_date TIMESTAMPTZ NOT NULL,
  end_date TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_patient_meds_patient ON patient_medications(patient_id);
CREATE TABLE IF NOT EXISTS allergies (
  allergy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
  allergen TEXT NOT NULL,
  reaction TEXT,
  severity TEXT NOT NULL CHECK (severity IN ('Low', 'Moderate', 'High')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_allergies_patient_id ON allergies(patient_id);
CREATE TABLE IF NOT EXISTS prescriptions (
  prescription_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  clinician_id UUID NOT NULL REFERENCES clinicians(clinician_id) ON DELETE RESTRICT,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  clinician_name TEXT NOT NULL,
  medication_name TEXT NULL,
  dose TEXT NULL,
  sig TEXT NULL
);
CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id);
CREATE TABLE IF NOT EXISTS prescription_items (
  item_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  prescription_id UUID NOT NULL REFERENCES prescriptions(prescription_id) ON DELETE CASCADE,
  medication_id UUID NOT NULL REFERENCES medications(medication_id) ON DELETE RESTRICT,
  medication_name TEXT NOT NULL,
  dose TEXT NOT NULL,
  sig TEXT NOT NULL,
  duration TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prescription_items_rx ON prescription_items(prescription_id);
-- =========================
-- LIFESTYLE DATA
-- sleep_records, meal_logs, step_records, activity_sessions
-- =========================
-- Enums for lifestyle
DO $$ BEGIN IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'meal_type_enum'
) THEN CREATE TYPE meal_type_enum AS ENUM ('BREAKFAST', 'LUNCH', 'DINNER', 'SNACK', 'OTHER');
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'activity_type_enum'
) THEN CREATE TYPE activity_type_enum AS ENUM (
  'WALKING',
  'RUNNING',
  'CYCLING',
  'SWIMMING',
  'STRENGTH_TRAINING',
  'YOGA',
  'HIIT',
  'OTHER'
);
END IF;
IF NOT EXISTS (
  SELECT 1
  FROM pg_type
  WHERE typname = 'activity_intensity_enum'
) THEN CREATE TYPE activity_intensity_enum AS ENUM ('LOW', 'MODERATE', 'HIGH');
END IF;
END $$;
-- One record per sleep session (typically one per night)
CREATE TABLE IF NOT EXISTS sleep_records (
  sleep_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  sleep_start TIMESTAMPTZ NOT NULL,
  sleep_end TIMESTAMPTZ NOT NULL,
  duration_min INT NOT NULL,
  -- total sleep in minutes
  deep_sleep_min INT NULL,
  rem_sleep_min INT NULL,
  light_sleep_min INT NULL,
  awakenings INT NULL DEFAULT 0,
  quality_score SMALLINT NULL CHECK (
    quality_score BETWEEN 1 AND 10
  ),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sleep_patient_start ON sleep_records(patient_id, sleep_start DESC);
-- Meal logs — timestamped; hypertable partitioned by logged_at
CREATE TABLE IF NOT EXISTS meal_logs (
  log_id UUID NOT NULL DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  logged_at TIMESTAMPTZ NOT NULL,
  meal_type meal_type_enum NOT NULL DEFAULT 'OTHER',
  description TEXT NULL,
  calories_kcal DOUBLE PRECISION NULL,
  carbs_g DOUBLE PRECISION NULL,
  protein_g DOUBLE PRECISION NULL,
  fat_g DOUBLE PRECISION NULL,
  fiber_g DOUBLE PRECISION NULL,
  glycemic_index INT NULL,
  PRIMARY KEY (log_id, logged_at)
);
CREATE INDEX IF NOT EXISTS idx_meal_patient_ts ON meal_logs(patient_id, logged_at DESC);
DO $$ BEGIN IF EXISTS (
  SELECT 1
  FROM pg_extension
  WHERE extname = 'timescaledb'
) THEN PERFORM create_hypertable('meal_logs', 'logged_at', if_not_exists => TRUE);
END IF;
END $$;
-- Daily step / distance summary (one row per patient per calendar day)
CREATE TABLE IF NOT EXISTS step_records (
  step_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  record_date DATE NOT NULL,
  step_count INT NOT NULL DEFAULT 0,
  distance_meters DOUBLE PRECISION NULL,
  floors_climbed INT NULL,
  active_minutes INT NULL,
  sedentary_minutes INT NULL,
  calories_burned DOUBLE PRECISION NULL,
  UNIQUE (patient_id, record_date)
);
CREATE INDEX IF NOT EXISTS idx_steps_patient_date ON step_records(patient_id, record_date DESC);
-- Structured exercise / activity sessions
CREATE TABLE IF NOT EXISTS activity_sessions (
  session_id UUID NOT NULL DEFAULT uuid_generate_v4(),
  patient_id UUID NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NULL,
  activity_type activity_type_enum NOT NULL DEFAULT 'OTHER',
  intensity activity_intensity_enum NULL,
  duration_min INT NULL,
  calories_burned DOUBLE PRECISION NULL,
  avg_heart_rate INT NULL,
  max_heart_rate INT NULL,
  steps INT NULL,
  distance_meters DOUBLE PRECISION NULL,
  notes TEXT NULL,
  PRIMARY KEY (session_id, start_time)
);
CREATE INDEX IF NOT EXISTS idx_activity_sessions_patient_start ON activity_sessions(patient_id, start_time DESC);
DO $$ BEGIN IF EXISTS (
  SELECT 1
  FROM pg_extension
  WHERE extname = 'timescaledb'
) THEN PERFORM create_hypertable(
  'activity_sessions',
  'start_time',
  if_not_exists => TRUE
);
END IF;
END $$;
-- =========================
-- ANNOTATION EXTENSIONS
-- (freehand stylus/touch drawing on large multitouch surface)
-- =========================
-- Add FREEHAND ink type to annotation_type enum
DO $$ BEGIN IF NOT EXISTS (
  SELECT 1
  FROM pg_enum
  WHERE enumlabel = 'FREEHAND'
    AND enumtypid = 'annotation_type'::regtype
) THEN ALTER TYPE annotation_type
ADD VALUE 'FREEHAND';
END IF;
END $$;
-- Ink/stroke data: serialized JSON array of strokes
-- (points, pressure, color, width per stroke)
ALTER TABLE annotations
ADD COLUMN IF NOT EXISTS stroke_data JSONB NULL;
-- Default stroke color (hex) used when type = FREEHAND
ALTER TABLE annotations
ADD COLUMN IF NOT EXISTS stroke_color TEXT NOT NULL DEFAULT '#1a1a2e';
-- Base stroke width in logical canvas pixels
ALTER TABLE annotations
ADD COLUMN IF NOT EXISTS stroke_width FLOAT NOT NULL DEFAULT 4.0;