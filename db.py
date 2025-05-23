from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from datetime import datetime
import psycopg2
import json
import os

# DB connection strings
BASE_CONN_STR = "postgresql://postgres:123456@localhost:5432/postgres?"
TARGET_DB_NAME = "SGS_Database"
TARGET_CONN_STR = f"dbname='{TARGET_DB_NAME}' user='postgres' password='123456' host='localhost' port='5432'"

sensor_tables = {
    "PWR_TEMP": """
        CREATE TABLE IF NOT EXISTS PWR_TEMP (
            device_id TEXT PRIMARY KEY,
            sequence INTEGER,
            temp_celsius FLOAT,
            received_at TIMESTAMP
        )
    """,
    "WATER_DETECTOR": """
        CREATE TABLE IF NOT EXISTS WATER_DETECTOR (
            device_id TEXT PRIMARY KEY,
            sequence INTEGER,
            water_detected TEXT,
            received_at TIMESTAMP
        )
    """,
    "PULSE_DETECTOR": """
        CREATE TABLE IF NOT EXISTS PULSE_DETECTOR (
            device_id TEXT PRIMARY KEY,
            sequence INTEGER,
            pulse_count INTEGER,
            leak_detected TEXT,
            received_at TIMESTAMP
        )
    """,
    "MAGNETIC": """
        CREATE TABLE IF NOT EXISTS MAGNETIC (
            device_id TEXT PRIMARY KEY,
            sequence INTEGER,
            status TEXT,
            received_at TIMESTAMP
        )
    """
}

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database=TARGET_DB_NAME,
        user="postgres",
        password="123456"
    )

def create_database():
    """Create the target database if it doesn't exist."""
    try:
        engine = create_engine(BASE_CONN_STR, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :dbname"), {"dbname": TARGET_DB_NAME})
            if result.scalar() is None:
                conn.execute(text(f'CREATE DATABASE "{TARGET_DB_NAME}"'))
                print(f"✅ Database '{TARGET_DB_NAME}' created.")
            else:
                print(f"ℹ️ Database '{TARGET_DB_NAME}' already exists.")
    except (ProgrammingError, OperationalError) as e:
        print(f"❌ Error creating database: {e}")

def create_users_table():
    execute_sql("""
        CREATE TABLE IF NOT EXISTS Users (
            user_ID SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            surname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            location VARCHAR NOT NULL,
            password TEXT NOT NULL
        )
    """, "Users")

def create_user_device_table():
    execute_sql("""
        CREATE TABLE IF NOT EXISTS USER_DEVICE (
            device_id TEXT PRIMARY KEY,
            user_id INTEGER REFERENCES Users(user_ID) ON DELETE CASCADE,
            sensor_type TEXT NOT NULL
        )
    """, "USER_DEVICE")
    for table_name, ddl in sensor_tables.items():
        execute_sql(ddl, table_name)

def create_tables():
    create_users_table()
    create_user_device_table()
    insert_users()

def save_useful_data(entry):
    sensor_type = entry.get("sensor_group")
    device_id = entry.get("device_id")
    sequence = entry.get("sequence")
    decoded = entry.get("decoded", {})
    received_at = entry.get("received_at")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if sensor_type == "decode_PowerTemp":
                    cur.execute("""
                        INSERT INTO PWR_TEMP (device_id, sequence, temp_celsius, received_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                        sequence = EXCLUDED.sequence,
                        temp_celsius = EXCLUDED.temp_celsius,
                        received_at = EXCLUDED.received_at
                    """, (device_id, sequence, decoded.get("temp_celsius"), received_at))

                elif sensor_type == "decode_water_sensor":
                    cur.execute("""
                        INSERT INTO WATER_DETECTOR (device_id, sequence, water_detected, received_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                        sequence = EXCLUDED.sequence,
                        water_detected = EXCLUDED.water_detected,
                        received_at = EXCLUDED.received_at
                    """, (device_id, sequence, str(decoded.get("water_detected")), received_at))

                elif sensor_type == "decode_pulsemeter":
                    cur.execute("""
                        INSERT INTO PULSE_DETECTOR (device_id, sequence, pulse_count, leak_detected, received_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                        sequence = EXCLUDED.sequence,
                        pulse_count = EXCLUDED.pulse_count,
                        leak_detected = EXCLUDED.leak_detected,
                        received_at = EXCLUDED.received_at
                    """, (device_id, sequence, decoded.get("pulse_count"), str(decoded.get("leak_detected")), received_at))

                elif sensor_type == "decode_magnetic_sensor":
                    cur.execute("""
                        INSERT INTO MAGNETIC (device_id, sequence, status, received_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                        sequence = EXCLUDED.sequence,
                        status = EXCLUDED.status,
                        received_at = EXCLUDED.received_at
                    """, (device_id, sequence, decoded.get("status"), received_at))

                conn.commit()
    except Exception as e:
        print(f"❌ Error saving useful data: {e}")

def save_to_db(entry):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sigfox_raw (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP,
                        device_id TEXT,
                        device_type TEXT,
                        sequence INTEGER,
                        raw_payload TEXT,
                        decoded JSONB,
                        sensor_group TEXT,
                        received_at TIMESTAMP
                    )
                """)
                cur.execute("""
                    INSERT INTO sigfox_raw (timestamp, device_id, device_type, sequence, raw_payload, decoded, sensor_group, received_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    entry.get("timestamp"),
                    entry.get("device_id"),
                    entry.get("device_type"),
                    entry.get("sequence"),
                    entry.get("raw_payload"),
                    json.dumps(entry.get("decoded", {})),
                    entry.get("sensor_group"),
                    entry.get("received_at")
                ))
                conn.commit()
    except Exception as e:
        print(f"❌ Error saving raw data: {e}")

def get_all_users():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_ID, name, surname, email, location FROM Users")
            rows = cur.fetchall()
            return [dict(user_ID=row[0], name=row[1], surname=row[2], email=row[3], location=row[4]) for row in rows]

def get_available_devices():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sensor_type, device_id
                FROM USER_DEVICE
                WHERE user_id IS NULL
            """)
            devices = cur.fetchall()

    grouped = {}
    for sensor_type, device_id in devices:
        grouped.setdefault(sensor_type, []).append(device_id)

    return [{"sensor_type": stype, "devices": ids} for stype, ids in grouped.items()]

def get_device_assignments():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.name, u.email, d.device_id, d.sensor_type
                FROM USER_DEVICE d
                JOIN Users u ON u.user_ID = d.user_id
            """)
            rows = cur.fetchall()
            return [
                {"user_name": row[0], "user_email": row[1], "device_id": row[2], "sensor_type": row[3]}
                for row in rows
            ]

def insert_users():
    users = [
        ('User_1', 'Surname1', 'user1@example.com', 'Userpass', 'Location1'),
        ('Ashock', 'Surname2', 'ashock@example.com', 'Iamafarmer', 'Location2')
    ]
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for name, surname, email, password, location in users:
                    cur.execute("""
                        INSERT INTO Users (name, surname, email, password, location)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (email) DO NOTHING
                    """, (name, surname, email, password, location))
                conn.commit()
                print("✅ Sample users inserted.")
    except Exception as e:
        print(f"❌ Error inserting users: {e}")

def test_db_connection():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                print("✅ Database connection successful")
                return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def execute_sql(statement, table_name=""):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(statement)
                conn.commit()
                if table_name:
                    print(f"✅ Table '{table_name}' is ready.")
    except Exception as e:
        print(f"❌ Error with table '{table_name}': {e}")

if __name__ == "__main__":
    create_database()
    create_tables()
    test_db_connection()
