"""
Database Initialization Script for AgriSmart Connect.
Creates the 'agrismart' database if not present, and executes schema.sql
to instantiate all 18 normalized relational tables, triggers, and indexes.
"""

import sys
from pathlib import Path
import psycopg
from psycopg import sql

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config


def init_database():
    print("=" * 65)
    print(" AgriSmart Connect - Database Initializer")
    print("=" * 65)

    # 1. Connect to default 'postgres' database to check/create 'agrismart'
    server_conn_info = Config.get_postgres_server_conn_string()
    target_db = Config.DB_NAME

    print(f"[*] Connecting to PostgreSQL server on {Config.DB_HOST}:{Config.DB_PORT} as '{Config.DB_USER}'...")
    try:
        with psycopg.connect(server_conn_info, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Check if target database exists
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target_db,))
                exists = cur.fetchone()
                if not exists:
                    print(f"[*] Database '{target_db}' does not exist. Creating it now...")
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
                    print(f"[+] Successfully created database '{target_db}'!")
                else:
                    print(f"[+] Database '{target_db}' already exists.")
    except Exception as e:
        print(f"\n[-] ERROR connecting to PostgreSQL server: {e}")
        print("\nPlease ensure that:")
        print(f" 1. PostgreSQL service is running on {Config.DB_HOST}:{Config.DB_PORT}")
        print(f" 2. The password in your .env file matches your PostgreSQL 'postgres' user password.")
        sys.exit(1)

    # 2. Connect to the target 'agrismart' database and run schema.sql
    target_conn_info = Config.get_db_conn_string()
    schema_file = Path(__file__).resolve().parent.parent / 'database' / 'schema.sql'

    if not schema_file.exists():
        print(f"[-] ERROR: Schema file not found at: {schema_file}")
        sys.exit(1)

    print(f"[*] Reading schema definition from: {schema_file.name}...")
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    print(f"[*] Applying schema to database '{target_db}'...")
    try:
        with psycopg.connect(target_conn_info) as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()
            print("[+] Successfully executed schema.sql!")

            # 3. Verify created tables
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                """)
                tables = [r[0] for r in cur.fetchall()]

                print(f"\n[+] Verified {len(tables)} tables in '{target_db}' database:")
                for idx, t in enumerate(tables, 1):
                    print(f"    {idx:2d}. {t}")

        print("\n" + "=" * 65)
        print(" Database setup completed successfully!")
        print("=" * 65)

    except Exception as e:
        print(f"\n[-] ERROR executing schema on '{target_db}': {e}")
        sys.exit(1)


if __name__ == '__main__':
    init_database()
