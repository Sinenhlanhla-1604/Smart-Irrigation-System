import psycopg2

# Connection string to the target 'SGS_Database database
TARGET_CONN_STR = ( #name of database username  password
    "dbname='SGS_Database' user='postgres' password='123456' host='localhost' port='5432'"
)

def fetch_latest_record(table_name, timestamp_field='received_at'):
    """Generic function to fetch the latest record from a table using a timestamp field."""
    try:
        conn = psycopg2.connect(TARGET_CONN_STR)
        cursor = conn.cursor()
        query = f"""
            SELECT * FROM {table_name}
            ORDER BY {timestamp_field} DESC;
        """
        cursor.execute(query)
        row = cursor.fetchone()
        if row:
            print(f"🔹 Latest record from {table_name}: {row}")
        else:
            print(f"⚠️ No records found in {table_name}.")
    except Exception as e:
        print(f"❌ Error fetching from {table_name}: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def fetch_latest_notification():
    """Fetch latest notification based on 'notification_id' as the ordering column."""
    try:
        conn = psycopg2.connect(TARGET_CONN_STR)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM NOTIFICATIONS
            ORDER BY notification_id DESC
            LIMIT 1;
        """)
        row = cursor.fetchone()
        if row:
            print(f"🔹 Latest record from NOTIFICATIONS: {row}")
        else:
            print("⚠️ No records found in NOTIFICATIONS.")
    except Exception as e:
        print(f"❌ Error fetching from NOTIFICATIONS: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def fetch_latest_user():
    """Fetch the latest user based on last_login."""
    try:
        conn = psycopg2.connect(TARGET_CONN_STR)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM Users
            ORDER BY last_login DESC
            LIMIT 1;
        """)
        row = cursor.fetchone()
        if row:
            print(f"🔹 Latest user by last login: {row}")
        else:
            print("⚠️ No users found.")
    except Exception as e:
        print(f"❌ Error fetching user: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def fetch_latest_user_device():
    """Fetch the latest entry in USER_DEVICE (assuming device_id or user_id increase over time)."""
    try:
        conn = psycopg2.connect(TARGET_CONN_STR)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM USER_DEVICE
            ORDER BY device_id DESC
            LIMIT 1;
        """)
        row = cursor.fetchone()
        if row:
            print(f"🔹 Latest record from USER_DEVICE: {row}")
        else:
            print("⚠️ No records found in USER_DEVICE.")
    except Exception as e:
        print(f"❌ Error fetching from USER_DEVICE: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    # Fetch latest records
    print("\n📦 Fetching latest records from each table:")
    fetch_latest_user()
    fetch_latest_record("PWR_TEMP")
    fetch_latest_record("WATER_DETECTOR")
    fetch_latest_record("PULSE_DETECTOR")
    fetch_latest_record("MAGNETIC")
    fetch_latest_notification()
    fetch_latest_user_device()
