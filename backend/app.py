"""
AgriSmart Connect - Backend Flask Application Entry Point.
Sets up Flask, CORS, connection pool lifecycle, and registers API blueprints.
"""

import atexit
import datetime
from decimal import Decimal
import logging
import sys
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS

# Add backend directory to module search path
sys.path.insert(0, str(Path(__file__).resolve().parent))

class AgriSmartJSONProvider(DefaultJSONProvider):
    """Custom JSON provider to safely serialize datetime.time, datetime.date, Decimal, etc."""
    def default(self, obj):
        if isinstance(obj, datetime.time):
            return obj.strftime('%H:%M:%S')
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

try:
    from config import Config
    from database import init_pool, close_pool
    from routes.health import health_bp
    from routes.auth import auth_bp
    from routes.crops import crops_bp
    from routes.hubs import hubs_bp
    from routes.farmers import farmers_bp
    from routes.marketplace import marketplace_bp
    from routes.demand import demand_bp
    from routes.matching import matching_bp
    from routes.orders import orders_bp
    from routes.quality import quality_bp
    from routes.delivery import delivery_bp
    from routes.payments import payments_bp
    from routes.admin import admin_bp
    from routes.forecasts import forecasts_bp
    from routes.ai import ai_bp
    from routes.iot import iot_bp
    from routes.webhooks import webhooks_bp
    from routes.logistics import logistics_bp
except ImportError:
    from backend.config import Config
    from backend.database import init_pool, close_pool
    from backend.routes.health import health_bp
    from backend.routes.auth import auth_bp
    from backend.routes.crops import crops_bp
    from backend.routes.hubs import hubs_bp
    from backend.routes.farmers import farmers_bp
    from backend.routes.marketplace import marketplace_bp
    from backend.routes.demand import demand_bp
    from backend.routes.matching import matching_bp
    from backend.routes.orders import orders_bp
    from backend.routes.quality import quality_bp
    from backend.routes.delivery import delivery_bp
    from backend.routes.payments import payments_bp
    from backend.routes.admin import admin_bp
    from backend.routes.forecasts import forecasts_bp
    from backend.routes.ai import ai_bp
    from backend.routes.iot import iot_bp
    from backend.routes.webhooks import webhooks_bp
    from backend.routes.logistics import logistics_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('agrismart')

FRONTEND_DIR = Path(__file__).resolve().parent.parent / 'frontend'
UPLOADS_DIR = FRONTEND_DIR / 'uploads' / 'products'
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def create_app() -> Flask:
    """Application factory for AgriSmart Connect."""
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
    app.json_provider_class = AgriSmartJSONProvider
    app.json = AgriSmartJSONProvider(app)
    app.config.from_object(Config)

    # Enable CORS for all API routes (allows frontend to talk to backend without origin blocking)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints
    app.register_blueprint(health_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(crops_bp, url_prefix='/api/crops')
    app.register_blueprint(hubs_bp, url_prefix='/api/hubs')
    app.register_blueprint(farmers_bp, url_prefix='/api/farmers')
    app.register_blueprint(marketplace_bp, url_prefix='/api/marketplace')
    app.register_blueprint(demand_bp, url_prefix='/api/demand')
    app.register_blueprint(matching_bp, url_prefix='/api/matching')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(quality_bp, url_prefix='/api/quality-checks')
    app.register_blueprint(delivery_bp, url_prefix='/api/deliveries')
    app.register_blueprint(payments_bp, url_prefix='/api/payments')
    app.register_blueprint(payments_bp, url_prefix='/api/payment', name='payment_singular')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(forecasts_bp, url_prefix='/api/forecasts')
    app.register_blueprint(ai_bp, url_prefix='/api/ai')
    app.register_blueprint(iot_bp, url_prefix='/api/iot')
    app.register_blueprint(webhooks_bp, url_prefix='/api/webhooks')
    app.register_blueprint(logistics_bp, url_prefix='/api/logistics')

    # Frontend routes
    @app.route('/')
    def index():
        return send_from_directory(str(FRONTEND_DIR), 'index.html')

    @app.route('/<path:filename>')
    def serve_frontend_file(filename):
        target = FRONTEND_DIR / filename
        if target.is_file():
            return send_from_directory(str(FRONTEND_DIR), filename)
        return jsonify({'error': 'Not Found', 'message': f"Resource '{filename}' not found."}), 404

    # Error handlers for JSON API responses
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({'error': 'Not Found', 'message': 'The requested resource was not found.'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal Server Error', 'message': 'An unexpected server error occurred.'}), 500

    # Ensure connection pool is closed when the application terminates
    atexit.register(close_pool)

    return app


# Application instance
app = create_app()

if __name__ == '__main__':
    print("=" * 65)
    print(f" Starting AgriSmart Connect Backend on port {Config.FLASK_PORT}")
    print(f" Health check: http://localhost:{Config.FLASK_PORT}/api/health")
    print(f" DB Test:     http://localhost:{Config.FLASK_PORT}/api/db-test")
    print("=" * 65)
    app.run(host='0.0.0.0', port=Config.FLASK_PORT, debug=Config.FLASK_DEBUG)
