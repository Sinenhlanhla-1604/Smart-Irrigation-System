import psycopg2
import json
import os
from datetime import datetime
from flask import request

# Environment-based configuration
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_NAME = os.getenv("DB_NAME", "smartGrow")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

TARGET_CONN_STR = f"dbname='{DB_NAME}' user='{DB_USER}' password='{DB_PASSWORD}' host='{DB_HOST}' port='{DB_PORT}'"

def get_connection():
    return psycopg2.connect(TARGET_CONN_STR)

def save_device_data(device_id, data_type, value, unit=None):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                if data_type in ['water_detected', 'leak_detected'] and value:
                    cursor.execute("""
                        INSERT INTO alerts (device_id, alert_type, message, severity)
                        VALUES (%s, %s, %s, %s)
                        RETURNING alert_id
                    """, (device_id, data_type, f"{data_type} detected on device {device_id}", "high"))
                    alert_id = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        INSERT INTO user_notifications (user_id, alert_id)
                        SELECT user_id, %s FROM devices WHERE device_id = %s
                    """, (alert_id, device_id))

                cursor.execute("""
                    INSERT INTO device_data (device_id, data_type, value, unit)
                    VALUES (%s, %s, %s, %s)
                """, (device_id, data_type, value, unit))
    except Exception as e:
        print(f"Error saving device data: {e}")

def save_device_info(device_id, user_id, device_name, device_type, decoded_data, seq_number, status):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO devices (device_id, user_id, device_name, device_type, is_active)
                    VALUES (%s, %s, %s, (SELECT device_id FROM device_types WHERE type_name = %s), %s)
                    ON CONFLICT (device_id) 
                    DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        device_name = EXCLUDED.device_name,
                        device_type = EXCLUDED.device_type,
                        is_active = EXCLUDED.is_active,
                        updated_at = CURRENT_TIMESTAMP
                """, (device_id, user_id, device_name, device_type, status == "Active"))

                cursor.execute("""
                    INSERT INTO device_metadata (device_id, seq_number, raw_payload, decoded_data)
                    VALUES (%s, %s, %s, %s)
                """, (device_id, seq_number, request.json.get("data", ""), json.dumps(decoded_data)))
    except Exception as e:
        print(f"Error saving device info: {e}")

# You can continue to move other database-related functions like:
# - get_user_devices()
# - get_device_data()
# - manage_users()
# - list_all_devices()
# - view_audit_log()
# into this module as well.
