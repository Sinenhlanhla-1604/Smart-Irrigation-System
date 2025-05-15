from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from datetime import datetime, timezone
import psycopg2


app = Flask(__name__)

# Step 1: Connect to default 'postgres' DB to create ''SGS_Database' DB if not exists
base_conn_str = "postgresql://postgres:123456@localhost:5432/postgres?"

# Connection string to the target 'SGS_Database database
TARGET_CONN_STR = ( #name of database username  password
    "dbname='SGS_Database' user='postgres' password='123456' host='localhost' port='5432'"
)

def create_database():
    """Create the 'SGS_Database' database if it does not exist."""
    try:
        engine = create_engine(base_conn_str, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :dbname"), {"dbname": "SGS_Database"})
            if result.scalar() is None:
                conn.execute(text('CREATE DATABASE "SGS_Database"'))
                print("✅ Database 'SGS_Database' created.")
            else:
                print("ℹ️ Database 'SGS_Database' already exists.")
    except (ProgrammingError, OperationalError) as e:
        print(f"❌ Error creating database: {e}")
    

# def create_Admin_table():
#     """Create the 'Admin' table in the 'SGS_Database' database if it does not exist."""
#     try:
#         conn = psycopg2.connect(TARGET_CONN_STR)
#         cursor = conn.cursor()
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS Admin (
#                 Admin_ID SERIAL PRIMARY KEY,
#                 username TEXT UNIQUE NOT NULL,
#                 password TEXT NOT NULL,
#                 last_login TIMESTAMP
#             )
#         """)
#         conn.commit()
#         print("✅ Table 'Admin' is ready.")
#     except Exception as e:
#         print(f"❌ Error creating Admin table: {e}")
#     finally:
#         if 'cursor' in locals():
#             cursor.close()
#         if 'conn' in locals():
#             conn.close()

# def insert_admins():
#     """Insert predefined Admins into the Admin table."""
#     try:
#         conn = psycopg2.connect(TARGET_CONN_STR)
#         cursor = conn.cursor()

#         now = datetime.now(timezone.utc)
#         users = [
#             ('Admin', 'Adminpass', now),
#             ('Tshepang_Admin', 'Adminpass', now)
#         ]

#         for user in users: 
#             cursor.execute("""
#                 INSERT INTO Admin (username, password, last_login)
#                 VALUES (%s, %s, %s)
#                 ON CONFLICT (username) DO NOTHING
#             """, user)

#         conn.commit()
#         print("✅ Admins inserted.")
#     except Exception as e:
#         print(f"❌ Error inserting admins: {e}")
#     finally:
#         if 'cursor' in locals():
#             cursor.close()
#         if 'conn' in locals():
#             conn.close()

def create_Users_table(): 
    """Create the 'Users' table in the 'SGS_Database' database if it does not exist.""" 
    try:
        conn = psycopg2.connect(TARGET_CONN_STR)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                User_ID SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                last_login TIMESTAMP
            )
        """)
        conn.commit()
        print("✅ Table 'Users' is ready.")
    except Exception as e:
        print(f"❌ Error creating Users table: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def insert_users():
    """Insert predefined Users into the Users table."""
    try:
        conn = psycopg2.connect(TARGET_CONN_STR)
        cursor = conn.cursor()

        now = datetime.now(timezone.utc)
        users = [
            ('User_1', 'Userpass', now),
            ('Ashock', 'Iamafarmer', now)
        ]

        for user in users:
            cursor.execute("""
                INSERT INTO Users (username, password, last_login)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            """, user)

        conn.commit()
        print("✅ Users inserted.")
    except Exception as e:
        print(f"❌ Error inserting users: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
     create_database()
    #  create_Admin_table()
    #  insert_admins()
     create_Users_table()
     insert_users()
