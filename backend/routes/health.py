"""
Health check and database connectivity verification endpoints.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify
try:
    from database import test_connection
    from config import Config
except ImportError:
    from backend.database import test_connection
    from backend.config import Config

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Basic service health check endpoint.
    Verifies that the Flask application process is alive and responsive.
    """
    return jsonify({
        'status': 'healthy',
        'service': 'AgriSmart Connect API',
        'version': '1.0.0',
        'environment': Config.FLASK_ENV,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), 200


@health_bp.route('/db-test', methods=['GET'])
def database_test():
    """
    Database connectivity check endpoint.
    Tests pool acquisition, runs a query on PostgreSQL, and verifies tables.
    """
    try:
        db_info = test_connection()
        return jsonify({
            'status': 'connected',
            'message': 'Successfully connected to PostgreSQL database!',
            'database': db_info.get('current_db'),
            'tables_count': db_info.get('table_count'),
            'server_version': db_info.get('db_version'),
            'server_time': str(db_info.get('server_time')),
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'user': Config.DB_USER
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to connect to PostgreSQL database.',
            'error': str(e),
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'database': Config.DB_NAME,
            'user': Config.DB_USER,
            'troubleshooting': 'Please ensure PostgreSQL is running and check DB credentials in .env.'
        }), 503
