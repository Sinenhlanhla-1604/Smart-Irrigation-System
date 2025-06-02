from flask import Blueprint, request, redirect, url_for, session, jsonify, render_template, flash, get_flashed_messages
from datetime import datetime
from db import (
    get_db_connection,
    get_all_users,
    get_available_devices,
    get_device_assignments
)
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from flask import Blueprint, jsonify
from db import get_db_connection

user_bp = Blueprint("user", __name__)
app_pages = Blueprint('app_pages', __name__)
app_secret = "your_secret_key"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="SGS_Database",
        user="postgres",
        password="123456"
    )

def is_logged_in():
    return session.get('logged_in') is True

@app_pages.route('/')
def homepage():
    return render_template('home.html', messages=get_flashed_messages(with_categories=True))

@app_pages.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    # Admin login (unchanged)
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['logged_in'] = True
        session['role'] = 'admin'
        flash("Logged in as admin.", "success")
        return redirect(url_for('app_pages.admin_dashboard'))

    # User login with device lookup
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get user info
                cur.execute("SELECT user_ID, name, surname, email, location, password FROM Users WHERE email = %s", (username,))
                user = cur.fetchone()

                if user and check_password_hash(user[5], password):
                    user_id = user[0]
                    
                    # Get the user's assigned device(s) - prioritize pulse meter for charts
                    cur.execute("""
                        SELECT device_id, sensor_type 
                        FROM USER_DEVICE 
                        WHERE user_id = %s 
                        ORDER BY CASE 
                            WHEN sensor_type = 'decode_pulsemeter' THEN 1
                            ELSE 2 
                        END
                        LIMIT 1
                    """, (user_id,))
                    
                    device_result = cur.fetchone()
                    device_id = device_result[0] if device_result else None
                    
                    # Store all session data including device_id
                    session.update({
                        'logged_in': True,
                        'role': 'user',
                        'user_id': user[0],
                        'user_name': user[1],
                        'user_email': user[3],
                        'user_location': user[4],
                        'device_id': device_id
                    })
                    
                    print(f"✅ Login successful for {user[1]}")
                    print(f"📱 Device ID stored in session: {device_id}")
                    
                    if not device_id:
                        print(f"⚠️ No device assigned to user {user[1]}")
                        flash(f"Welcome {user[1]}! Note: No device assigned yet.", "warning")
                    else:
                        flash(f"Welcome {user[1]}!", "success")
                    
                    return redirect(url_for('app_pages.user_dashboard'))

                flash("Invalid credentials", "error")
                return redirect(url_for('app_pages.homepage'))
                
    except Exception as e:
        print(f"❌ Login error: {e}")
        flash("Login error occurred", "error")
        return redirect(url_for('app_pages.homepage'))

@app_pages.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('app_pages.homepage'))

@app_pages.route('/user_dashboard')
def user_dashboard():
    if not is_logged_in() or session.get('role') != 'user':
        flash("Login required.", "error")
        return redirect(url_for('app_pages.homepage'))

    return render_template('user.html',
                           user_name=session['user_name'],
                           user_location=session['user_location'],
                           messages=get_flashed_messages(with_categories=True))

@app_pages.route('/admin')
def admin_dashboard():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Admin access required.", "error")
        return redirect(url_for('app_pages.homepage'))

    users = get_all_users()
    available_devices = get_available_devices()
    assignments = get_device_assignments()

    return render_template('admin_dashboard.html',
                           users=users,
                           device_options=available_devices,
                           assignments=assignments,
                           messages=get_flashed_messages(with_categories=True))

@app_pages.route('/add_user', methods=['POST'])
def add_user():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Admin access required.", "error")
        return redirect(url_for('app_pages.homepage'))

    email = request.form['email']
    name = request.form['first_name']
    surname = request.form['last_name']
    password = request.form['password']
    location = request.form['location']

    if not all([email, name, surname, password, location]):
        flash("All fields are required.", "error")
        return redirect(url_for('app_pages.admin_dashboard'))

    try:
        hashed_password = generate_password_hash(password)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO Users (email, name, surname, password, location)
                    VALUES (%s, %s, %s, %s, %s)
                """, (email, name, surname, hashed_password, location))
                conn.commit()
        flash("User added successfully.", "success")
    except psycopg2.IntegrityError:
        flash("Email already exists.", "error")
    except Exception as e:
        flash(f"Error adding user: {e}", "error")

    return redirect(url_for('app_pages.admin_dashboard'))

@app_pages.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Admin access required.", "error")
        return redirect(url_for('app_pages.homepage'))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM Users WHERE user_ID = %s", (user_id,))
                conn.commit()
        flash("User deleted.", "success")
    except Exception as e:
        flash(f"Error deleting user: {e}", "error")

    return redirect(url_for('app_pages.admin_dashboard'))

@app_pages.route('/assign_device', methods=['POST'])
def assign_device():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Admin access required.", "error")
        return redirect(url_for('app_pages.homepage'))

    user_id = request.form.get("user_id")
    combined = request.form.get("device_info")

    try:
        device_id, sensor_type = combined.split('|')
    except ValueError:
        flash("Invalid device selection.", "error")
        return redirect(url_for('app_pages.admin_dashboard'))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM USER_DEVICE WHERE device_id = %s", (device_id,))
                exists = cur.fetchone()
                
                if exists:
                    cur.execute("""
                        UPDATE USER_DEVICE 
                        SET user_id = %s, sensor_type = %s
                        WHERE device_id = %s
                    """, (user_id, sensor_type, device_id))
                else:
                    cur.execute("""
                        INSERT INTO USER_DEVICE (device_id, user_id, sensor_type)
                        VALUES (%s, %s, %s)
                    """, (device_id, user_id, sensor_type))
                    
                conn.commit()
        flash("Device assigned successfully.", "success")
    except Exception as e:
        flash(f"Assignment failed: {e}", "error")

    return redirect(url_for('app_pages.admin_dashboard'))

@app_pages.route('/unassign_device/<device_id>', methods=['POST'])
def unassign_device(device_id):
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Admin access required.", "error")
        return redirect(url_for('app_pages.homepage'))

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE USER_DEVICE SET user_id = NULL WHERE device_id = %s", (device_id,))
                conn.commit()
        flash("Device unassigned.", "success")
    except Exception as e:
        flash(f"Unassignment failed: {e}", "error")

    return redirect(url_for('app_pages.admin_dashboard'))

# FIXED: Enhanced API endpoint with better error handling and null checks
@app_pages.route('/api/user/data')
def api_user_data():
    print("🔍 API /api/user/data called")
    
    if not is_logged_in() or session.get('role') != 'user':
        print("❌ Unauthorized access")
        return jsonify({"error": "Unauthorized"}), 403

    user_id = session.get('user_id')
    print(f"👤 User ID: {user_id}")

    if not user_id:
        print("❌ No user_id in session")
        return jsonify({"error": "Invalid session"}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get user device assignments with better error handling
                cur.execute("""
                    SELECT device_id, sensor_type
                    FROM USER_DEVICE
                    WHERE user_id = %s AND user_id IS NOT NULL
                """, (user_id,))
                assignments = cur.fetchall()
                
                print(f"📱 Found {len(assignments)} device assignments")

                data = {
                    "temperature_sensors": [],
                    "pulse_meters": [],
                    "water_sensors": [],
                    "door_sensors": [],
                    "system_uptime": "99.5%",
                    "last_updated": datetime.now().isoformat()
                }

                for device_id, sensor_type in assignments:
                    print(f"🔍 Processing device {device_id} of type {sensor_type}")
                    
                    try:
                        if sensor_type == "decode_PowerTemp":
                            cur.execute("""
                                SELECT device_id, temp_celsius, received_at
                                FROM PWR_TEMP
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            temp_row = cur.fetchone()
                            
                            if temp_row and temp_row[1] is not None:
                                data["temperature_sensors"].append({
                                    "device_id": temp_row[0],
                                    "temp_celsius": float(temp_row[1]),
                                    "received_at": temp_row[2].isoformat() if temp_row[2] else None
                                })
                                print(f"✅ Added temperature sensor data: {temp_row[1]}°C")
                            else:
                                print(f"⚠️ No temperature data found for device {device_id}")

                        elif sensor_type == "decode_pulsemeter":
                            cur.execute("""
                                SELECT device_id, pulse_count, leak_detected, received_at
                                FROM PULSE_DETECTOR
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            pulse_row = cur.fetchone()
                            
                            if pulse_row:
                                data["pulse_meters"].append({
                                    "device_id": pulse_row[0],
                                    "pulse_count": int(pulse_row[1]) if pulse_row[1] is not None else 0,
                                    "leak_detected": str(pulse_row[2]) if pulse_row[2] is not None else "False",
                                    "received_at": pulse_row[3].isoformat() if pulse_row[3] else None
                                })
                                print(f"✅ Added pulse meter data: {pulse_row[1]} pulses")
                            else:
                                print(f"⚠️ No pulse data found for device {device_id}")

                        elif sensor_type == "decode_water_sensor":
                            cur.execute("""
                                SELECT device_id, water_detected, received_at
                                FROM WATER_DETECTOR
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            water_row = cur.fetchone()
                            
                            if water_row:
                                data["water_sensors"].append({
                                    "device_id": water_row[0],
                                    "water_detected": str(water_row[1]) if water_row[1] is not None else "False",
                                    "received_at": water_row[2].isoformat() if water_row[2] else None
                                })
                                print(f"✅ Added water sensor data: {water_row[1]}")
                            else:
                                print(f"⚠️ No water data found for device {device_id}")

                        # Add this debugging and fix to your /api/user/data route
# Replace the existing door sensor section with this improved version:

                        elif sensor_type == "decode_magnetic_sensor":
                            print(f"🚪 Processing door sensor for device {device_id}")
                            cur.execute("""
                                SELECT device_id, status, received_at
                                FROM MAGNETIC
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            door_row = cur.fetchone()
                            
                            if door_row:
                                # Debug the actual values
                                print(f"🚪 Door sensor raw data: device={door_row[0]}, status='{door_row[1]}', time={door_row[2]}")
                                
                                # Clean and normalize the status value
                                raw_status = door_row[1]
                                if raw_status is not None:
                                    # Convert to string and clean whitespace
                                    status_str = str(raw_status).strip().lower()
                                    # Normalize different possible values
                                    if status_str in ['open', '1', 'true', 'opened']:
                                        normalized_status = 'open'
                                    elif status_str in ['closed', '0', 'false', 'close']:
                                        normalized_status = 'closed'
                                    else:
                                        normalized_status = status_str  # Keep original if unclear
                                else:
                                    normalized_status = 'unknown'
                                
                                print(f"🚪 Normalized door status: '{normalized_status}'")
                                
                                data["door_sensors"].append({
                                    "device_id": door_row[0],
                                    "status": normalized_status,
                                    "received_at": door_row[2].isoformat() if door_row[2] else None
                                })
                                print(f"✅ Added door sensor data: {normalized_status}")
                            else:
                                print(f"⚠️ No door data found for device {device_id}")
                                # Add a placeholder with unknown status
                                data["door_sensors"].append({
                                    "device_id": device_id,
                                    "status": "no_data",
                                    "received_at": None
                                })
                        
                        else:
                            print(f"⚠️ Unknown sensor type: {sensor_type}")
                            
                    except Exception as sensor_error:
                        print(f"❌ Error processing sensor {sensor_type} for device {device_id}: {sensor_error}")
                        continue

                print(f"✅ Returning data with {len(data['temperature_sensors'])} temp, {len(data['pulse_meters'])} pulse, {len(data['water_sensors'])} water, {len(data['door_sensors'])} door sensors")
                return jsonify(data)

    except Exception as e:
        print(f"❌ API error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# FIXED: Enhanced devices endpoint with better null handling
@app_pages.route('/api/user/devices')
def api_user_devices():
    print("🔍 API /api/user/devices called")
    
    if not is_logged_in() or session.get('role') != 'user':
        return jsonify({"error": "Unauthorized"}), 403

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Invalid session"}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Simplified query to avoid complex CASE statements that might fail
                cur.execute("""
                    SELECT device_id, sensor_type
                    FROM USER_DEVICE
                    WHERE user_id = %s
                    ORDER BY sensor_type, device_id
                """, (user_id,))
                devices = cur.fetchall()
                
                result = []
                
                for device_id, sensor_type in devices:
                    device_info = {
                        "device_id": device_id,
                        "sensor_type": sensor_type,
                        "last_value": None,
                        "last_reading": "No Data",
                        "last_updated": None
                    }
                    
                    try:
                        # Get data based on sensor type
                        if sensor_type == "decode_PowerTemp":
                            cur.execute("""
                                SELECT temp_celsius, received_at
                                FROM PWR_TEMP
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            row = cur.fetchone()
                            if row and row[0] is not None:
                                device_info.update({
                                    "last_value": f"{float(row[0]):.1f}°C",
                                    "last_reading": "Temperature",
                                    "last_updated": row[1].isoformat() if row[1] else None
                                })
                                
                        elif sensor_type == "decode_pulsemeter":
                            cur.execute("""
                                SELECT pulse_count, received_at
                                FROM PULSE_DETECTOR
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            row = cur.fetchone()
                            if row:
                                device_info.update({
                                    "last_value": str(int(row[0])) if row[0] is not None else "0",
                                    "last_reading": "Pulse Count",
                                    "last_updated": row[1].isoformat() if row[1] else None
                                })
                                
                        elif sensor_type == "decode_water_sensor":
                            cur.execute("""
                                SELECT water_detected, received_at
                                FROM WATER_DETECTOR
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            row = cur.fetchone()
                            if row:
                                device_info.update({
                                    "last_value": str(row[0]) if row[0] is not None else "False",
                                    "last_reading": "Water Detected",
                                    "last_updated": row[1].isoformat() if row[1] else None
                                })
                                
                        elif sensor_type == "decode_magnetic_sensor":
                            cur.execute("""
                                SELECT status, received_at
                                FROM MAGNETIC
                                WHERE device_id = %s
                                ORDER BY received_at DESC
                                LIMIT 1
                            """, (device_id,))
                            row = cur.fetchone()
                            if row:
                                device_info.update({
                                    "last_value": str(row[0]) if row[0] is not None else "Unknown",
                                    "last_reading": "Door Status",
                                    "last_updated": row[1].isoformat() if row[1] else None
                                })
                    
                    except Exception as device_error:
                        print(f"❌ Error fetching data for device {device_id}: {device_error}")
                        # Keep default values set above
                    
                    result.append(device_info)
                    
                print(f"✅ Returning {len(result)} devices")
                return jsonify(result)

    except Exception as e:
        print(f"❌ Error fetching user devices: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# FIXED: Chart data endpoint with better error handling
@app_pages.route('/api/user/usage')
def api_user_chart_data():
    print("🔍 API /api/user/usage called")
    
    if not is_logged_in() or session.get('role') != 'user':
        print("❌ Unauthorized access attempt")
        return jsonify({"error": "Unauthorized"}), 403

    device_id = session.get('device_id')
    user_id = session.get('user_id')
    
    print(f"📱 Device ID from session: {device_id}")
    print(f"👤 User ID from session: {user_id}")

    # If no device_id in session, try to get it from database
    if not device_id and user_id:
        print("🔄 Attempting to refresh device_id from database...")
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT device_id, sensor_type 
                        FROM USER_DEVICE 
                        WHERE user_id = %s 
                        ORDER BY CASE 
                            WHEN sensor_type = 'decode_pulsemeter' THEN 1
                            ELSE 2 
                        END
                        LIMIT 1
                    """, (user_id,))
                    
                    device_result = cur.fetchone()
                    if device_result:
                        device_id = device_result[0]
                        session['device_id'] = device_id  # Update session
                        print(f"✅ Retrieved device_id from database: {device_id}")
                    else:
                        print("❌ No device found for user in database")
                        
        except Exception as e:
            print(f"❌ Error retrieving device_id: {e}")

    if not device_id:
        print("⚠️ No device_id available, returning empty data")
        return jsonify({
            "labels": [], 
            "values": [], 
            "message": "No device assigned to user",
            "error": "NO_DEVICE"
        })

    try:
        period = request.args.get('period', 'Weekly')
        print(f"📊 Requested period: {period}")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if device exists and has data first
                cur.execute("""
                    SELECT COUNT(*) as total_records,
                           MIN(received_at) as earliest,
                           MAX(received_at) as latest
                    FROM PULSE_DETECTOR 
                    WHERE device_id = %s
                """, (device_id,))
                
                stats = cur.fetchone()
                total_records = stats[0] if stats else 0
                
                print(f"📊 Device {device_id} has {total_records} total records")
                
                if total_records == 0:
                    return jsonify({
                        "labels": [], 
                        "values": [], 
                        "message": f"No data found for device {device_id}",
                        "total_records": 0
                    })
                
                # Define time configurations
                time_configs = {
                    "Daily": {
                        "trunc": "DATE_TRUNC('hour', received_at)",
                        "where": "received_at >= NOW() - INTERVAL '1 day'",
                        "format_key": "hour"
                    },
                    "Weekly": {
                        "trunc": "DATE_TRUNC('day', received_at)",
                        "where": "received_at >= NOW() - INTERVAL '7 days'",
                        "format_key": "day"
                    },
                    "Monthly": {
                        "trunc": "DATE_TRUNC('day', received_at)",
                        "where": "received_at >= NOW() - INTERVAL '30 days'",
                        "format_key": "day"
                    },
                    "All": {
                        "trunc": "DATE_TRUNC('day', received_at)",
                        "where": "1=1",
                        "format_key": "day"
                    }
                }
                
                config = time_configs.get(period, time_configs["Weekly"])
                
                query = f"""
                    SELECT {config['trunc']} AS interval, 
                           COALESCE(SUM(pulse_count), 0) as total_pulses
                    FROM PULSE_DETECTOR
                    WHERE device_id = %s AND {config['where']}
                    GROUP BY interval
                    ORDER BY interval ASC
                """
                
                print(f"🔍 Executing query: {query}")
                
                cur.execute(query, (device_id,))
                rows = cur.fetchall()
                
                print(f"📊 Query returned {len(rows)} rows")
                
                if not rows:
                    return jsonify({
                        "labels": [], 
                        "values": [], 
                        "message": f"No data available for {period.lower()} period",
                        "total_records": total_records
                    })
                
                # Process the data
                labels = []
                values = []
                
                for row in rows:
                    interval_date = row[0]
                    pulse_count = int(row[1]) if row[1] is not None else 0
                    
                    # Format the date based on period
                    if period == "Daily":
                        formatted_date = interval_date.strftime("%H:00")
                    else:
                        formatted_date = interval_date.strftime("%m-%d")
                    
                    labels.append(formatted_date)
                    values.append(pulse_count)
                    
                    print(f"📊 Data point: {formatted_date} = {pulse_count} pulses")
                
                result = {
                    "labels": labels,
                    "values": values,
                    "total_points": len(labels),
                    "period": period,
                    "device_id": device_id,
                    "total_records": total_records
                }
                
                print(f"✅ Returning chart data: {len(labels)} points")
                return jsonify(result)

    except Exception as e:
        print(f"❌ Chart API error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": "Internal server error", 
            "details": str(e),
            "labels": [],
            "values": []
        }), 500

