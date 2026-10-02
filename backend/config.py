import os
from pathlib import Path
from dotenv import load_dotenv
from decimal import Decimal

# Load environment variables from .env in project root
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path, override=True)

class Config:
    """Application configuration loaded from environment variables."""
    SECRET_KEY = os.getenv('SECRET_KEY', 'agrismart-connect-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', '1') == '1'
    FLASK_PORT = int(os.getenv('PORT', os.getenv('FLASK_PORT', 5000)))

    # PostgreSQL Database Credentials
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 5432))
    DB_NAME = os.getenv('DB_NAME', 'agrismart')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

    # Connection Pool Configuration
    DB_MIN_CONNECTIONS = int(os.getenv('DB_MIN_CONNECTIONS', 0))
    DB_MAX_CONNECTIONS = int(os.getenv('DB_MAX_CONNECTIONS', 10))
    DB_TIMEOUT = float(os.getenv('DB_TIMEOUT', 5.0))

    # ── AI / LLM Configuration (Gemini API for Cloud / Ollama for Local) ───
    GEMINI_API_KEY             = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL               = os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite')
    OLLAMA_HOST                = os.getenv('OLLAMA_HOST', 'http://localhost:11434')

    # ── Razorpay Payment Gateway ─────────────────────────────────────────
    RAZORPAY_KEY_ID            = os.getenv('RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET        = os.getenv('RAZORPAY_KEY_SECRET', '')
    RAZORPAY_WEBHOOK_SECRET    = os.getenv('RAZORPAY_WEBHOOK_SECRET', '')
    PAYMENT_MODE               = os.getenv('PAYMENT_MODE', 'test')  # 'test' | 'live'
    PLATFORM_COMMISSION_PERCENT = float(os.getenv('PLATFORM_COMMISSION_PERCENT', 10.0))

    # ── Multi-Hub & Demo Configuration ──────────────────────────────────
    DEMO_MODE                  = os.getenv('DEMO_MODE', 'true').lower() in ('1', 'true', 'yes')
    DEFAULT_HUB_FEE            = float(os.getenv('DEFAULT_HUB_FEE', 25.0))
    DEFAULT_DELIVERY_BASE_FARE = float(os.getenv('DEFAULT_DELIVERY_BASE_FARE', 50.0))
    GEOFENCE_RADIUS_METERS     = float(os.getenv('GEOFENCE_RADIUS_METERS', 500.0))

    @classmethod
    def get_db_conn_string(cls) -> str:
        """Construct PostgreSQL connection URI for psycopg."""
        if cls.DATABASE_URL:
            url = cls.DATABASE_URL.strip()
            # Standardize postgres:// to postgresql:// for Psycopg 3 compatibility
            if url.startswith('postgres://'):
                url = 'postgresql://' + url[len('postgres://'):]
            return url

        return (
            f"host={cls.DB_HOST} "
            f"port={cls.DB_PORT} "
            f"dbname={cls.DB_NAME} "
            f"user={cls.DB_USER} "
            f"password={cls.DB_PASSWORD} "
            f"connect_timeout=5"
        )

    @classmethod
    def get_postgres_server_conn_string(cls) -> str:
        """Connection string to root 'postgres' maintenance database for setup/creation."""
        return (
            f"host={cls.DB_HOST} "
            f"port={cls.DB_PORT} "
            f"dbname=postgres "
            f"user={cls.DB_USER} "
            f"password={cls.DB_PASSWORD} "
            f"connect_timeout=5"
        )
