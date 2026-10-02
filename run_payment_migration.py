"""Run payment migration against the agrismart PostgreSQL database."""
import psycopg
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'backend'))
from config import Config

sql_file = Path(__file__).parent / 'database' / 'payment_migration.sql'
conn_str = Config.get_db_conn_string()

print('[*] Running payment_migration.sql against agrismart DB...')
try:
    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_file.read_text(encoding='utf-8'))
        conn.commit()
    print('[+] Migration completed successfully!')

    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
                ORDER BY table_name;
            """)
            tables = [r[0] for r in cur.fetchall()]
    print(f'[+] Total tables in DB: {len(tables)}')
    for t in tables:
        print(f'    - {t}')

except Exception as e:
    print(f'[-] Migration FAILED: {e}')
    import traceback; traceback.print_exc()
    sys.exit(1)
