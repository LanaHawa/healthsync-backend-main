import os
import sys
import argparse
import psycopg2
from psycopg2 import sql


READING_TABLE_CANDIDATES = [
    "glucose_readings",
    "cgm_readings",
    "readings",
    "cgm_data",
]

PATIENT_TABLE_CANDIDATES = [
    "patients",
    "patient",
]

USER_TABLE_CANDIDATES = [
    "users",
    "user",
]

TIMESTAMP_COL_CANDIDATES = [
    "timestamp",
    "recorded_at",
    "reading_time",
    "created_at",
    "time",
]

VALUE_COL_CANDIDATES = [
    "value",
    "glucose_value",
    "glucose_mgdl",
    "reading_value",
    "mg_dl",
]

PATIENT_ID_COL_CANDIDATES = [
    "patient_id",
    "user_id",
]


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg2.connect(database_url)


def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        )
        """,
        (table_name,),
    )
    return cur.fetchone()[0]


def get_columns(cur, table_name: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [row[0] for row in cur.fetchall()]


def detect_table(cur, candidates: list[str]) -> str | None:
    for table_name in candidates:
        if table_exists(cur, table_name):
            return table_name
    return None


def detect_column(columns: list[str], candidates: list[str]) -> str | None:
    for col in candidates:
        if col in columns:
            return col
    return None


def get_primary_key_column(cur, table_name: str) -> str | None:
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """,
        (table_name,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_fk_reference(cur, from_table: str, from_column: str):
    """
    Returns (referenced_table, referenced_column) if from_table.from_column
    has a foreign key, else None.
    """
    cur.execute(
        """
        SELECT
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = %s
          AND kcu.column_name = %s
        """,
        (from_table, from_column),
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def detect_name_sql(alias: str, columns: list[str]) -> str | None:
    if "full_name" in columns:
        return f"{alias}.full_name"
    if "name" in columns:
        return f"{alias}.name"
    if "first_name" in columns and "last_name" in columns:
        return f"TRIM(COALESCE({alias}.first_name, '') || ' ' || COALESCE({alias}.last_name, ''))"
    if "email" in columns:
        return f"{alias}.email"
    return None


def detect_email_sql(alias: str, columns: list[str]) -> str | None:
    if "email" in columns:
        return f"{alias}.email"
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Show CGM data distribution with patient names and time ranges."
    )
    parser.add_argument("--patient", default=None, help="Filter by patient name/email/id text match.")
    parser.add_argument("--limit", type=int, default=100, help="Limit number of rows shown.")
    args = parser.parse_args()

    try:
        conn = get_connection()
    except Exception as e:
        print(f"❌ Failed to connect to DB: {e}")
        sys.exit(1)

    try:
        with conn, conn.cursor() as cur:
            # 1) Detect readings table and key columns
            reading_table = detect_table(cur, READING_TABLE_CANDIDATES)
            if not reading_table:
                print("❌ Could not find a glucose/CGM readings table.")
                print(f"Tried: {', '.join(READING_TABLE_CANDIDATES)}")
                sys.exit(1)

            reading_columns = get_columns(cur, reading_table)
            patient_id_col = detect_column(reading_columns, PATIENT_ID_COL_CANDIDATES)
            timestamp_col = detect_column(reading_columns, TIMESTAMP_COL_CANDIDATES)
            value_col = detect_column(reading_columns, VALUE_COL_CANDIDATES)

            if not patient_id_col or not timestamp_col:
                print("❌ Could not detect required columns in readings table.")
                print(f"Readings table: {reading_table}")
                print(f"Columns: {', '.join(reading_columns)}")
                sys.exit(1)

            # Defaults if no joins work
            join_sql = ""
            patient_name_sql = f"CAST(r.{patient_id_col} AS TEXT)"
            patient_email_sql = "NULL"
            name_source_used = "readings table only"

            # 2) Try to join to patients table using FK or PK detection
            patient_table = detect_table(cur, PATIENT_TABLE_CANDIDATES)
            user_table = detect_table(cur, USER_TABLE_CANDIDATES)

            patient_columns = []
            user_columns = []

            patient_alias_name_sql = None
            patient_alias_email_sql = None
            user_alias_name_sql = None
            user_alias_email_sql = None

            if patient_table:
                patient_columns = get_columns(cur, patient_table)
                patient_pk = get_primary_key_column(cur, patient_table)

                fk_ref = get_fk_reference(cur, reading_table, patient_id_col)
                joined_patients = False

                # Best case: glucose_readings.patient_id -> patients.<some_pk>
                if fk_ref and fk_ref[0] == patient_table:
                    join_sql = (
                        f' LEFT JOIN "{patient_table}" p '
                        f'ON p."{fk_ref[1]}" = r."{patient_id_col}" '
                    )
                    joined_patients = True

                # Fallback: if patient_id column name itself exists in patients
                elif patient_id_col in patient_columns:
                    join_sql = (
                        f' LEFT JOIN "{patient_table}" p '
                        f'ON p."{patient_id_col}" = r."{patient_id_col}" '
                    )
                    joined_patients = True

                # Fallback: join by patients PK if it exists and types match in practice
                elif patient_pk:
                    join_sql = (
                        f' LEFT JOIN "{patient_table}" p '
                        f'ON p."{patient_pk}" = r."{patient_id_col}" '
                    )
                    joined_patients = True

                if joined_patients:
                    patient_alias_name_sql = detect_name_sql("p", patient_columns)
                    patient_alias_email_sql = detect_email_sql("p", patient_columns)

                    if patient_alias_name_sql:
                        patient_name_sql = (
                            f"COALESCE(NULLIF({patient_alias_name_sql}, ''), CAST(r.{patient_id_col} AS TEXT))"
                        )
                    if patient_alias_email_sql:
                        patient_email_sql = patient_alias_email_sql

                    name_source_used = patient_table

            # 3) Optionally enrich with users table if patients links to users
            if patient_table and user_table:
                user_columns = get_columns(cur, user_table)
                user_alias_name_sql = detect_name_sql("u", user_columns)
                user_alias_email_sql = detect_email_sql("u", user_columns)

                patient_user_fk = None

                # Find a FK from patients -> users
                for col in ["user_id", "id"]:
                    if col in patient_columns:
                        ref = get_fk_reference(cur, patient_table, col)
                        if ref and ref[0] == user_table:
                            patient_user_fk = (col, ref[1])
                            break

                if patient_user_fk:
                    # Rebuild join with both tables
                    patient_join_part = join_sql

                    # Avoid duplicating patients join if somehow not set
                    if not patient_join_part:
                        patient_pk = get_primary_key_column(cur, patient_table)
                        if patient_pk:
                            patient_join_part = (
                                f' LEFT JOIN "{patient_table}" p '
                                f'ON p."{patient_pk}" = r."{patient_id_col}" '
                            )

                    join_sql = (
                        patient_join_part
                        + f' LEFT JOIN "{user_table}" u '
                        + f'ON u."{patient_user_fk[1]}" = p."{patient_user_fk[0]}" '
                    )

                    name_candidates = []
                    email_candidates = []

                    if patient_alias_name_sql:
                        name_candidates.append(f"NULLIF({patient_alias_name_sql}, '')")
                    if user_alias_name_sql:
                        name_candidates.append(f"NULLIF({user_alias_name_sql}, '')")
                    if patient_alias_email_sql:
                        name_candidates.append(f"NULLIF({patient_alias_email_sql}, '')")
                    if user_alias_email_sql:
                        name_candidates.append(f"NULLIF({user_alias_email_sql}, '')")
                    name_candidates.append(f"CAST(r.{patient_id_col} AS TEXT)")

                    patient_name_sql = f"COALESCE({', '.join(name_candidates)})"

                    if patient_alias_email_sql:
                        email_candidates.append(f"NULLIF({patient_alias_email_sql}, '')")
                    if user_alias_email_sql:
                        email_candidates.append(f"NULLIF({user_alias_email_sql}, '')")

                    patient_email_sql = (
                        f"COALESCE({', '.join(email_candidates)})"
                        if email_candidates else "NULL"
                    )

                    name_source_used = f"{patient_table} + {user_table}"

            filter_expr = f"COALESCE({patient_name_sql}, {patient_email_sql}, CAST(r.{patient_id_col} AS TEXT))"

            where_clause = ""
            params = []

            if args.patient:
                where_clause = f"""
                WHERE (
                    CAST(r.{patient_id_col} AS TEXT) ILIKE %s
                    OR {filter_expr} ILIKE %s
                )
                """
                params = [f"%{args.patient}%", f"%{args.patient}%"]

            summary_query = f"""
            SELECT
                COUNT(*) AS total_readings,
                COUNT(DISTINCT r.{patient_id_col}) AS patients_with_data,
                MIN(r.{timestamp_col}) AS earliest_reading,
                MAX(r.{timestamp_col}) AS latest_reading
            FROM "{reading_table}" r
            {join_sql}
            {where_clause}
            """

            cur.execute(summary_query, params)
            summary = cur.fetchone()

            value_stats_sql = ""
            if value_col:
                value_stats_sql = f"""
                , ROUND(AVG(r.{value_col})::numeric, 2) AS avg_glucose
                , MIN(r.{value_col}) AS min_glucose
                , MAX(r.{value_col}) AS max_glucose
                """

            detail_query = f"""
            SELECT
                r.{patient_id_col} AS patient_id,
                {patient_name_sql} AS patient_name,
                {patient_email_sql} AS patient_email,
                COUNT(*) AS reading_count,
                COUNT(DISTINCT DATE(r.{timestamp_col})) AS days_with_data,
                MIN(r.{timestamp_col}) AS first_reading,
                MAX(r.{timestamp_col}) AS last_reading
                {value_stats_sql}
            FROM "{reading_table}" r
            {join_sql}
            {where_clause}
            GROUP BY
                r.{patient_id_col},
                {patient_name_sql},
                {patient_email_sql}
            ORDER BY reading_count DESC, patient_name ASC
            LIMIT %s
            """

            cur.execute(detail_query, params + [args.limit])
            rows = cur.fetchall()

            print("\n================ CGM DATA DISTRIBUTION REPORT ================\n")
            print(f"Readings table used : {reading_table}")
            print(f"Name source used    : {name_source_used}")
            print(f"Patient ID column   : {patient_id_col}")
            print(f"Timestamp column    : {timestamp_col}")
            print(f"Value column        : {value_col if value_col else 'Not detected'}")
            print()

            print("Overall summary")
            print("---------------")
            print(f"Total readings      : {summary[0]}")
            print(f"Patients with data  : {summary[1]}")
            print(f"Earliest reading    : {summary[2]}")
            print(f"Latest reading      : {summary[3]}")
            print()

            if not rows:
                print("No patient CGM data found for this filter.")
                return

            print("Per-patient distribution")
            print("------------------------")
            print(
                f"{'patient_id':<38} {'name':<28} {'email':<34} "
                f"{'count':>8} {'days':>6} {'first_reading':<22} {'last_reading':<22}"
            )
            print("-" * 170)

            for row in rows:
                patient_id, patient_name, patient_email, reading_count, days_with_data, first_reading, last_reading, *rest = row
                print(
                    f"{str(patient_id):<38} "
                    f"{str(patient_name or '')[:27]:<28} "
                    f"{str(patient_email or '')[:33]:<34} "
                    f"{reading_count:>8} "
                    f"{days_with_data:>6} "
                    f"{str(first_reading)[:21]:<22} "
                    f"{str(last_reading)[:21]:<22}"
                )

            if value_col:
                print("\nDetailed glucose stats")
                print("----------------------")
                print(
                    f"{'name':<28} {'count':>8} {'days':>6} {'avg':>8} {'min':>8} {'max':>8} {'range':<28}"
                )
                print("-" * 110)
                for row in rows:
                    patient_id, patient_name, patient_email, reading_count, days_with_data, first_reading, last_reading, avg_glucose, min_glucose, max_glucose = row
                    date_range = f"{str(first_reading)[:10]} -> {str(last_reading)[:10]}"
                    display_name = patient_name if patient_name and str(patient_name).strip() else patient_id
                    print(
                        f"{str(display_name)[:27]:<28} "
                        f"{reading_count:>8} "
                        f"{days_with_data:>6} "
                        f"{str(avg_glucose):>8} "
                        f"{str(min_glucose):>8} "
                        f"{str(max_glucose):>8} "
                        f"{date_range:<28}"
                    )

            print("\nDone.\n")

    except Exception as e:
        print(f"❌ Error while generating report: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()