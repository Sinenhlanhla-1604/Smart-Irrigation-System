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

# Updated sensor tables to support historical data (multiple records per device)
sensor_tables = {
    "PWR_TEMP": """
        CREATE TABLE IF NOT EXISTS PWR_TEMP (
            id SERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            sequence INTEGER,
            temp_celsius FLOAT,
            received_at TIMESTAMP,
            UNIQUE(device_id, sequence, received_at)
        )
    """,
    "WATER_DETECTOR": """
        CREATE TABLE IF NOT EXISTS WATER_DETECTOR (
            id SERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            sequence INTEGER,
            water_detected TEXT,
            received_at TIMESTAMP,
            UNIQUE(device_id, sequence, received_at)
        )
    """,
    "PULSE_DETECTOR": """
        CREATE TABLE IF NOT EXISTS PULSE_DETECTOR (
            id SERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            sequence INTEGER,
            pulse_count INTEGER,
            leak_detected TEXT,
            received_at TIMESTAMP,
            UNIQUE(device_id, sequence, received_at)
        )
    """,
    "MAGNETIC": """
        CREATE TABLE IF NOT EXISTS MAGNETIC (
            id SERIAL PRIMARY KEY,
            device_id TEXT NOT NULL,
            sequence INTEGER,
            status TEXT,
            received_at TIMESTAMP,
            UNIQUE(device_id, sequence, received_at)
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
            device_id TEXT NOT NULL,
            user_id INTEGER REFERENCES Users(user_ID) ON DELETE SET NULL,
            sensor_type TEXT NOT NULL,
            PRIMARY KEY (device_id),
            UNIQUE (device_id, sensor_type)
        )
    """, "USER_DEVICE")

    for table_name, ddl in sensor_tables.items():
        execute_sql(ddl, table_name)

def create_tables():
    create_users_table()
    create_user_device_table()
    insert_users()

def save_useful_data(entry):
    """
    Save sensor data keeping all historical records.
    This version prevents duplicate entries and preserves all sensor readings over time.
    """
    sensor_type = entry.get("sensor_group")
    device_id = entry.get("device_id")
    sequence = entry.get("sequence")
    decoded = entry.get("decoded", {})
    received_at = entry.get("received_at")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # First ensure device exists in USER_DEVICE table
                cur.execute("""
                    INSERT INTO USER_DEVICE (device_id, sensor_type, user_id)
                    VALUES (%s, %s, NULL)
                    ON CONFLICT (device_id) DO NOTHING
                """, (device_id, sensor_type))
                
                # Save sensor data - keeps all historical records, prevents duplicates
                if sensor_type == "decode_PowerTemp":
                    cur.execute("""
                        INSERT INTO PWR_TEMP (device_id, sequence, temp_celsius, received_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (device_id, sequence, received_at) DO NOTHING
                    """, (device_id, sequence, decoded.get("temp_celsius"), received_at))

                elif sensor_type == "decode_water_sensor":
                    cur.execute("""
                        INSERT INTO WATER_DETECTOR (device_id, sequence, water_detected, received_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (device_id, sequence, received_at) DO NOTHING
                    """, (device_id, sequence, str(decoded.get("water_detected")), received_at))

                elif sensor_type == "decode_pulsemeter":
                    cur.execute("""
                        INSERT INTO PULSE_DETECTOR (device_id, sequence, pulse_count, leak_detected, received_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (device_id, sequence, received_at) DO NOTHING
                    """, (device_id, sequence, decoded.get("pulse_count"), str(decoded.get("leak_detected")), received_at))

                elif sensor_type == "decode_magnetic_sensor":
                    cur.execute("""
                        INSERT INTO MAGNETIC (device_id, sequence, status, received_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (device_id, sequence, received_at) DO NOTHING
                    """, (device_id, sequence, decoded.get("status"), received_at))

                conn.commit()
                print(f"✅ Data saved for device {device_id} ({sensor_type})")
    except Exception as e:
        print(f"❌ Error saving useful data: {e}")

def save_useful_data_overwrite(entry):
    """
    Alternative version that overwrites existing data (keeps only latest reading per device).
    Use this if you only want to store the most recent reading for each device.
    """
    sensor_type = entry.get("sensor_group")
    device_id = entry.get("device_id")
    sequence = entry.get("sequence")
    decoded = entry.get("decoded", {})
    received_at = entry.get("received_at")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # First ensure device exists in USER_DEVICE table
                cur.execute("""
                    INSERT INTO USER_DEVICE (device_id, sensor_type, user_id)
                    VALUES (%s, %s, NULL)
                    ON CONFLICT (device_id) DO NOTHING
                """, (device_id, sensor_type))
                
                # Overwrite existing data with latest reading
                if sensor_type == "decode_PowerTemp":
                    cur.execute("""
                        DELETE FROM PWR_TEMP WHERE device_id = %s;
                        INSERT INTO PWR_TEMP (device_id, sequence, temp_celsius, received_at)
                        VALUES (%s, %s, %s, %s)
                    """, (device_id, device_id, sequence, decoded.get("temp_celsius"), received_at))

                elif sensor_type == "decode_water_sensor":
                    cur.execute("""
                        DELETE FROM WATER_DETECTOR WHERE device_id = %s;
                        INSERT INTO WATER_DETECTOR (device_id, sequence, water_detected, received_at)
                        VALUES (%s, %s, %s, %s)
                    """, (device_id, device_id, sequence, str(decoded.get("water_detected")), received_at))

                elif sensor_type == "decode_pulsemeter":
                    cur.execute("""
                        DELETE FROM PULSE_DETECTOR WHERE device_id = %s;
                        INSERT INTO PULSE_DETECTOR (device_id, sequence, pulse_count, leak_detected, received_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (device_id, device_id, sequence, decoded.get("pulse_count"), str(decoded.get("leak_detected")), received_at))

                elif sensor_type == "decode_magnetic_sensor":
                    cur.execute("""
                        DELETE FROM MAGNETIC WHERE device_id = %s;
                        INSERT INTO MAGNETIC (device_id, sequence, status, received_at)
                        VALUES (%s, %s, %s, %s)
                    """, (device_id, device_id, sequence, decoded.get("status"), received_at))

                conn.commit()
                print(f"✅ Data overwritten for device {device_id} ({sensor_type})")
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
            # Get all devices from sensor tables that aren't assigned yet
            cur.execute("""
                SELECT DISTINCT device_id, 'decode_PowerTemp' as sensor_type 
                FROM PWR_TEMP 
                WHERE device_id NOT IN (SELECT device_id FROM USER_DEVICE WHERE user_id IS NOT NULL)
                
                UNION
                
                SELECT DISTINCT device_id, 'decode_pulsemeter' as sensor_type 
                FROM PULSE_DETECTOR 
                WHERE device_id NOT IN (SELECT device_id FROM USER_DEVICE WHERE user_id IS NOT NULL)
                
                UNION
                
                SELECT DISTINCT device_id, 'decode_water_sensor' as sensor_type 
                FROM WATER_DETECTOR 
                WHERE device_id NOT IN (SELECT device_id FROM USER_DEVICE WHERE user_id IS NOT NULL)
                
                UNION
                
                SELECT DISTINCT device_id, 'decode_magnetic_sensor' as sensor_type 
                FROM MAGNETIC 
                WHERE device_id NOT IN (SELECT device_id FROM USER_DEVICE WHERE user_id IS NOT NULL)
            """)
            new_devices = cur.fetchall()
            
            # Also get devices that are in USER_DEVICE but unassigned
            cur.execute("""
                SELECT device_id, sensor_type
                FROM USER_DEVICE
                WHERE user_id IS NULL
            """)
            unassigned_devices = cur.fetchall()
            
            # Combine both lists
            all_devices = new_devices + unassigned_devices

    # Group by sensor type
    grouped = {}
    for device_id, sensor_type in all_devices:
        grouped.setdefault(sensor_type, []).append(device_id)

    return [{"sensor_type": stype, "devices": ids} for stype, ids in grouped.items()]

def get_device_assignments():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.name, u.email, d.device_id, d.sensor_type
                FROM USER_DEVICE d
                JOIN Users u ON u.user_ID = d.user_id
                WHERE d.user_id IS NOT NULL
            """)
            rows = cur.fetchall()
            return [
                {"user_name": row[0], "user_email": row[1], "device_id": row[2], "sensor_type": row[3]}
                for row in rows
            ]

def get_device_data(device_id, sensor_type, limit=10):
    """
    Get recent data for a specific device.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if sensor_type == "decode_PowerTemp":
                    cur.execute("""
                        SELECT device_id, sequence, temp_celsius, received_at 
                        FROM PWR_TEMP 
                        WHERE device_id = %s 
                        ORDER BY received_at DESC 
                        LIMIT %s
                    """, (device_id, limit))
                    columns = ['device_id', 'sequence', 'temp_celsius', 'received_at']
                
                elif sensor_type == "decode_water_sensor":
                    cur.execute("""
                        SELECT device_id, sequence, water_detected, received_at 
                        FROM WATER_DETECTOR 
                        WHERE device_id = %s 
                        ORDER BY received_at DESC 
                        LIMIT %s
                    """, (device_id, limit))
                    columns = ['device_id', 'sequence', 'water_detected', 'received_at']
                
                elif sensor_type == "decode_pulsemeter":
                    cur.execute("""
                        SELECT device_id, sequence, pulse_count, leak_detected, received_at 
                        FROM PULSE_DETECTOR 
                        WHERE device_id = %s 
                        ORDER BY received_at DESC 
                        LIMIT %s
                    """, (device_id, limit))
                    columns = ['device_id', 'sequence', 'pulse_count', 'leak_detected', 'received_at']
                
                elif sensor_type == "decode_magnetic_sensor":
                    cur.execute("""
                        SELECT device_id, sequence, status, received_at 
                        FROM MAGNETIC 
                        WHERE device_id = %s 
                        ORDER BY received_at DESC 
                        LIMIT %s
                    """, (device_id, limit))
                    columns = ['device_id', 'sequence', 'status', 'received_at']
                
                else:
                    return []
                
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
    
    except Exception as e:
        print(f"❌ Error getting device data: {e}")
        return []

def assign_device_to_user(device_id, user_id):
    """
    Assign a device to a specific user.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE USER_DEVICE 
                    SET user_id = %s 
                    WHERE device_id = %s
                """, (user_id, device_id))
                
                if cur.rowcount > 0:
                    conn.commit()
                    print(f"✅ Device {device_id} assigned to user {user_id}")
                    return True
                else:
                    print(f"❌ Device {device_id} not found")
                    return False
                    
    except Exception as e:
        print(f"❌ Error assigning device: {e}")
        return False

def unassign_device(device_id):
    """
    Remove user assignment from a device.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE USER_DEVICE 
                    SET user_id = NULL 
                    WHERE device_id = %s
                """, (device_id,))
                
                if cur.rowcount > 0:
                    conn.commit()
                    print(f"✅ Device {device_id} unassigned")
                    return True
                else:
                    print(f"❌ Device {device_id} not found")
                    return False
                    
    except Exception as e:
        print(f"❌ Error unassigning device: {e}")
        return False

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

def drop_and_recreate_tables():
    """
    Use this function if you need to migrate from the old table structure.
    WARNING: This will delete all existing sensor data!
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Drop existing sensor tables
                cur.execute("DROP TABLE IF EXISTS PWR_TEMP CASCADE")
                cur.execute("DROP TABLE IF EXISTS WATER_DETECTOR CASCADE")
                cur.execute("DROP TABLE IF EXISTS PULSE_DETECTOR CASCADE")
                cur.execute("DROP TABLE IF EXISTS MAGNETIC CASCADE")
                conn.commit()
                print("✅ Old tables dropped")
                
        # Recreate tables with new structure
        for table_name, ddl in sensor_tables.items():
            execute_sql(ddl, table_name)
            
    except Exception as e:
        print(f"❌ Error recreating tables: {e}")

if __name__ == "__main__":
    create_database()
    create_tables()
    test_db_connection()
    
    # Uncomment the line below if you need to migrate from old table structure
    # drop_and_recreate_tables()
