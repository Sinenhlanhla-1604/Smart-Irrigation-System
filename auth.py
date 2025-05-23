from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from werkzeug.security import check_password_hash, generate_password_hash
from db import get_db_connection

auth = Blueprint('auth', __name__)

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD_HASH = generate_password_hash('admin123')

@auth.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')  # Your login form HTML

@auth.route('/login', methods=['POST'])
def login():
    data = request.get_json(force=True)
    username = data.get('username')
    password = data.get('password')

    # Validate username/password (admin + db users) as before
    # On success, set session and return JSON redirect url
    # On failure, return JSON error message

    # (Your existing login POST logic here)

@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login_page'))
