"""
Authentication & Authorization Middleware for AgriSmart Connect.
Provides JWT token generation, decoding, and role-based access decorators.
"""

from functools import wraps
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import jwt
from flask import request, jsonify

try:
    from config import Config
except ImportError:
    from backend.config import Config


def generate_token(user_payload: Dict[str, Any], expires_in_days: int = 7) -> str:
    """Generate a signed JWT token containing user identity and role."""
    payload = {
        'user_id': user_payload['user_id'],
        'email': user_payload['email'],
        'phone': user_payload.get('phone', ''),
        'role': user_payload['role'],
        'name': user_payload.get('name', ''),
        'exp': datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        'iat': datetime.now(timezone.utc)
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    """
    Decorator requiring a valid JWT token in Authorization: Bearer <token>
    Sets request.current_user to the decoded payload.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', None)
        if not auth_header:
            return jsonify({'error': 'Unauthorized', 'message': 'Missing Authorization header.'}), 401

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid Authorization header format. Format: Bearer <token>'}), 401

        token = parts[1]
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Unauthorized', 'message': 'Token is invalid or has expired.'}), 401

        request.current_user = payload
        return f(*args, **kwargs)
    return decorated


def roles_required(*allowed_roles: str):
    """
    Decorator ensuring the authenticated user has one of the specified roles.
    Usage:
        @roles_required('admin')
        @roles_required('farmer', 'admin')
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user') or not request.current_user:
                return jsonify({'error': 'Unauthorized', 'message': 'Authentication required.'}), 401

            user_role = request.current_user.get('role')
            if user_role not in allowed_roles:
                return jsonify({
                    'error': 'Forbidden',
                    'message': f"Access restricted. Role '{user_role}' is not authorized for this resource.",
                    'required_roles': list(allowed_roles)
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator
