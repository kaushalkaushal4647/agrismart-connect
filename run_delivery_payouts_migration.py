"""
AgriSmart Connect - Apply Delivery Partner Payouts Migration
Applies database/delivery_payouts_migration.sql to the existing PostgreSQL database.
"""

import sys
from pathlib import Path
import psycopg

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / 'backend'))

from config import Config

def run_migration():
    print("=" * 65)
    print(" AgriSmart Connect - Delivery Partner Payouts Migration")
    print("=" * 65)

    migration_file = BASE_DIR / 'database' / 'delivery_payouts_migration.sql'
    if not migration_file.exists():
        print(f"[-] Migration file not found: {migration_file}")
        sys.exit(1)

    with open(migration_file, 'r', encoding='utf-8') as f:
        sql_script = f.read()

    conn_str = Config.get_db_conn_string()
    print(f"[*] Connecting to database '{Config.DB_NAME}' on {Config.DB_HOST}:{Config.DB_PORT}...")

    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_script)
                print("[+] Migration executed successfully!")

                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'delivery_payouts';
                """)
                verified = [r[0] for r in cur.fetchall()]
                print(f"[+] Verified newly created table: {verified}")

        print("=" * 65)
        print(" Migration completed successfully.")
        print("=" * 65)
        return True
    except Exception as e:
        print(f"[-] Migration failed: {e}")
        return False

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
