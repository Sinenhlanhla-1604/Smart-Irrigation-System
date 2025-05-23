from flask import Blueprint, request, redirect, url_for, session, jsonify, render_template, flash, get_flashed_messages
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

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['logged_in'] = True
        session['role'] = 'admin'
        flash("Logged in as admin.", "success")
        return redirect(url_for('app_pages.admin_dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_ID, name, surname, email, location, password FROM Users WHERE email = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and check_password_hash(user[5], password):
        session.update({
            'logged_in': True,
            'role': 'user',
            'user_id': user[0],
            'user_name': user[1],
            'user_email': user[3],
            'user_location': user[4]
        })
        flash(f"Welcome {user[1]}!", "success")
        return redirect(url_for('app_pages.user_dashboard'))

    flash("Invalid credentials", "error")
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

    device_options = ""
    for group in available_devices:
        device_options += f'<optgroup label="{group["sensor_type"]}">'
        for device_id in group["devices"]:
            device_options += f'<option value="{device_id}|{group["sensor_type"]}">{device_id}</option>'
        device_options += '</optgroup>'

    return render_template('admin_dashboard.html',
                           users=users,
                           device_options=device_options,
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
                cur.execute("""
                    INSERT INTO USER_DEVICE (device_id, user_id, sensor_type)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE
                    SET user_id = EXCLUDED.user_id, sensor_type = EXCLUDED.sensor_type
                """, (device_id, user_id, sensor_type))
                conn.commit()
        flash("Device assigned.", "success")
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



@app_pages.route('/api/user/data')
def api_user_data():
    if not is_logged_in() or session.get('role') != 'user':
        return jsonify({"error": "Unauthorized"}), 403

    user_id = session['user_id']

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get user device assignments
                cur.execute("""
                    SELECT device_id, sensor_type
                    FROM USER_DEVICE
                    WHERE user_id = %s
                """, (user_id,))
                assignments = cur.fetchall()

                data = {
                    "temperature_1": None,
                    "temperature_2": None,
                    "pulse_count": None,
                    "leak_detected": "False",
                    "water_status": [None, None, None],
                    "door_status": [None, None],
                }

                for device_id, sensor_type in assignments:
                    if sensor_type == "decode_PowerTemp":
                        cur.execute("""
                            SELECT temp_celsius
                            FROM PWR_TEMP
                            WHERE device_id = %s
                            ORDER BY received_at DESC
                            LIMIT 1
                        """, (device_id,))
                        temp = cur.fetchone()
                        if data["temperature_1"] is None:
                            data["temperature_1"] = temp[0] if temp else None
                        else:
                            data["temperature_2"] = temp[0] if temp else None

                    elif sensor_type == "decode_pulsemeter":
                        cur.execute("""
                            SELECT pulse_count, leak_detected
                            FROM PULSE_DETECTOR
                            WHERE device_id = %s
                            ORDER BY received_at DESC
                            LIMIT 1
                        """, (device_id,))
                        row = cur.fetchone()
                        if row:
                            data["pulse_count"] = row[0]
                            data["leak_detected"] = row[1]

                    elif sensor_type == "decode_water_sensor":
                        cur.execute("""
                            SELECT water_detected
                            FROM WATER_DETECTOR
                            WHERE device_id = %s
                            ORDER BY received_at DESC
                            LIMIT 1
                        """, (device_id,))
                        row = cur.fetchone()
                        for i in range(3):
                            if data["water_status"][i] is None:
                                data["water_status"][i] = row[0] if row else "False"
                                break

                    elif sensor_type == "decode_magnetic_sensor":
                        cur.execute("""
                            SELECT status
                            FROM MAGNETIC
                            WHERE device_id = %s
                            ORDER BY received_at DESC
                            LIMIT 1
                        """, (device_id,))
                        row = cur.fetchone()
                        for i in range(2):
                            if data["door_status"][i] is None:
                                data["door_status"][i] = row[0] if row else "closed"
                                break

        return jsonify(data)

    except Exception as e:
        print(f"❌ API error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app_pages.route('/api/user/usage')
def api_user_usage():
    if not is_logged_in() or session.get('role') != 'user':
        return jsonify({"error": "Unauthorized"}), 403

    user_id = session['user_id']
    period = request.args.get("period", "Weekly")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get all pulse meters assigned to user
                cur.execute("""
                    SELECT device_id FROM USER_DEVICE
                    WHERE user_id = %s AND sensor_type = 'decode_pulsemeter'
                """, (user_id,))
                device_ids = [row[0] for row in cur.fetchall()]

                if not device_ids:
                    return jsonify({"labels": [], "values": []})

                if period == "Daily":
                    time_filter = "AND received_at >= now() - interval '1 day'"
                    group_by = "hour"
                    label_format = "HH24"
                elif period == "Weekly":
                    time_filter = "AND received_at >= now() - interval '7 days'"
                    group_by = "date_trunc('day', received_at)"
                    label_format = "YYYY-MM-DD"
                elif period == "Monthly":
                    time_filter = "AND received_at >= now() - interval '30 days'"
                    group_by = "date_trunc('day', received_at)"
                    label_format = "YYYY-MM-DD"
                else:
                    time_filter = ""
                    group_by = "date_trunc('day', received_at)"
                    label_format = "YYYY-MM-DD"

                cur.execute(f"""
                    SELECT to_char({group_by}, '{label_format}') as label,
                           SUM(pulse_count) as total
                    FROM PULSE_DETECTOR
                    WHERE device_id = ANY(%s) {time_filter}
                    GROUP BY label
                    ORDER BY label
                """, (device_ids,))
                results = cur.fetchall()

                labels = [row[0] for row in results]
                values = [row[1] for row in results]

                return jsonify({"labels": labels, "values": values})

    except Exception as e:
        print(f"❌ Error loading usage chart: {e}")
        return jsonify({"error": "Internal server error"}), 500
