"""
Authentication routes for AgriSmart Connect.
Provides registration for all 7 roles, login (email or phone), and profile retrieval.
"""

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from database import get_db_cursor, fetch_one
    from auth_middleware import generate_token, token_required
except ImportError:
    from backend.database import get_db_cursor, fetch_one
    from backend.auth_middleware import generate_token, token_required

auth_bp = Blueprint('auth', __name__)

VALID_ROLES = {
    'farmer',
    'consumer',
    'restaurant',
    'retailer',
    'delivery_partner',
    'admin',
    'hub_operator'
}


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user and create their role-specific profile in a single atomic transaction.
    Roles: farmer, consumer, restaurant, retailer, delivery_partner, admin, hub_operator.
    """
    data = request.get_json() or {}

    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    role = data.get('role', '').strip().lower()

    # Basic validations
    if not all([name, phone, email, password, role]):
        return jsonify({'error': 'Bad Request', 'message': 'Missing required fields (name, phone, email, password, role).'}), 400

    if role not in VALID_ROLES:
        return jsonify({
            'error': 'Bad Request',
            'message': f"Invalid role '{role}'. Must be one of: {', '.join(sorted(VALID_ROLES))}"
        }), 400

    if len(password) < 6:
        return jsonify({'error': 'Bad Request', 'message': 'Password must be at least 6 characters long.'}), 400

    password_hash = generate_password_hash(password)

    try:
        with get_db_cursor(commit=True) as cur:
            # Check for existing email or phone
            cur.execute("SELECT user_id, email, phone FROM users WHERE email = %s OR phone = %s;", (email, phone))
            existing = cur.fetchone()
            if existing:
                if existing['email'] == email:
                    return jsonify({'error': 'Conflict', 'message': 'A user with this email already exists.'}), 409
                if existing['phone'] == phone:
                    return jsonify({'error': 'Conflict', 'message': 'A user with this phone number already exists.'}), 409

            # 1. Insert into users table
            cur.execute("""
                INSERT INTO users (name, phone, email, password_hash, role)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING user_id, name, phone, email, role, is_active, created_at;
            """, (name, phone, email, password_hash, role))
            new_user = dict(cur.fetchone())

            user_id = new_user['user_id']
            profile_data = {}

            # 2. Insert into role-specific profile table
            if role == 'farmer':
                farm_name = data.get('farm_name', f"{name}'s Farm")
                village = data.get('village', '')
                district = data.get('district', '')
                state = data.get('state', '')
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                farm_size = data.get('farm_size')
                address = data.get('address', '')

                cur.execute("""
                    INSERT INTO farmer_profiles (user_id, farm_name, village, district, state, latitude, longitude, farm_size, address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING farmer_id, farm_name, village, district, state, latitude, longitude, farm_size, address;
                """, (user_id, farm_name, village, district, state, latitude, longitude, farm_size, address))
                profile_data = dict(cur.fetchone())

            elif role in ('consumer', 'restaurant', 'retailer'):
                business_name = data.get('business_name', name if role == 'consumer' else f"{name} Store")
                address = data.get('address', '')
                village = data.get('village', '')
                district = data.get('district', '')
                latitude = data.get('latitude')
                longitude = data.get('longitude')

                cur.execute("""
                    INSERT INTO buyers (user_id, buyer_type, business_name, address, village, district, latitude, longitude)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING buyer_id, buyer_type, business_name, address, village, district, latitude, longitude;
                """, (user_id, role, business_name, address, village, district, latitude, longitude))
                profile_data = dict(cur.fetchone())

        # Generate JWT token
        token = generate_token(new_user)

        return jsonify({
            'status': 'success',
            'message': f"Account registered successfully as {role}!",
            'token': token,
            'user': {
                'user_id': new_user['user_id'],
                'name': new_user['name'],
                'phone': new_user['phone'],
                'email': new_user['email'],
                'role': new_user['role'],
                'profile': profile_data
            }
        }), 201

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate user via Email or Phone, and return a JWT access token.
    """
    data = request.get_json() or {}
    identifier = data.get('identifier', data.get('email', data.get('phone', ''))).strip()
    password = data.get('password', '')

    if not identifier or not password:
        return jsonify({'error': 'Bad Request', 'message': 'Identifier (email or phone) and password are required.'}), 400

    try:
        # Search by email or phone
        user = fetch_one("""
            SELECT user_id, name, phone, email, password_hash, role, is_active, created_at
            FROM users
            WHERE email = %s OR phone = %s;
        """, (identifier.lower(), identifier))

        if not user:
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid email/phone or password.'}), 401

        if not user.get('is_active', True):
            return jsonify({'error': 'Forbidden', 'message': 'Account is suspended. Contact administrator.'}), 403

        if not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid email/phone or password.'}), 401

        # Retrieve role-specific profile details
        role = user['role']
        profile = {}

        if role == 'farmer':
            profile = fetch_one("SELECT * FROM farmer_profiles WHERE user_id = %s;", (user['user_id'],)) or {}
        elif role in ('consumer', 'restaurant', 'retailer'):
            profile = fetch_one("SELECT * FROM buyers WHERE user_id = %s;", (user['user_id'],)) or {}

        # Remove sensitive password_hash before returning
        user.pop('password_hash', None)

        # Generate JWT token
        token = generate_token(user)

        return jsonify({
            'status': 'success',
            'message': 'Login successful.',
            'token': token,
            'user': {
                'user_id': user['user_id'],
                'name': user['name'],
                'phone': user['phone'],
                'email': user['email'],
                'role': user['role'],
                'profile': profile
            }
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user():
    """
    Return currently authenticated user's profile and permissions.
    """
    user_id = request.current_user['user_id']
    try:
        user = fetch_one("""
            SELECT user_id, name, phone, email, role, is_active, created_at
            FROM users WHERE user_id = %s;
        """, (user_id,))

        if not user:
            return jsonify({'error': 'Not Found', 'message': 'User not found.'}), 404

        role = user['role']
        profile = {}

        if role == 'farmer':
            profile = fetch_one("SELECT * FROM farmer_profiles WHERE user_id = %s;", (user_id,)) or {}
        elif role in ('consumer', 'restaurant', 'retailer'):
            profile = fetch_one("SELECT * FROM buyers WHERE user_id = %s;", (user_id,)) or {}

        return jsonify({
            'status': 'success',
            'user': {
                'user_id': user['user_id'],
                'name': user['name'],
                'phone': user['phone'],
                'email': user['email'],
                'role': user['role'],
                'profile': profile
            }
        }), 200

    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500
