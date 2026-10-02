"""
Run Multi-Hub, Order State Machine, Routing, and Settlement migration for AgriSmart Connect.
"""
import sys
from pathlib import Path

# Add backend directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / 'backend'))

from database import get_db_cursor, fetch_all

def run_migration():
    migration_file = BASE_DIR / 'database' / 'multihub_settlement_migration.sql'
    print(f"Reading migration file: {migration_file}")
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql = f.read()

    print("Applying migration to PostgreSQL 'agrismart' database...")
    with get_db_cursor(commit=True) as cur:
        cur.execute(sql)
    print("Migration applied successfully!")

    # Verify tables
    tables = [
        'order_events', 'order_routes', 'hub_transfers',
        'hub_staff', 'farmer_payout_accounts', 'settlements',
        'delivery_partner_locations', 'delivery_earnings'
    ]
    check_sql = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = ANY(%s);
    """
    rows = fetch_all(check_sql, (tables,))
    found = [r['table_name'] for r in rows]
    print(f"Verified new tables in database: {found}")

    # Seed sample bank payout accounts for farmers without UPI
    farmers = fetch_all("SELECT fp.farmer_id, u.name FROM farmer_profiles fp JOIN users u ON fp.user_id = u.user_id LIMIT 10;")
    with get_db_cursor(commit=True) as cur:
        for idx, f in enumerate(farmers):
            acc_num = f"6048102394{idx:02d}"
            cur.execute("""
                INSERT INTO farmer_payout_accounts (
                    farmer_id, account_holder_name, bank_account_number, bank_name, IFSC, UPI_ID, UPI_available, verification_status, payout_provider_reference
                )
                VALUES (%s, %s, %s, 'State Bank of India', 'SBIN0001234', %s, %s, 'VERIFIED', %s)
                ON CONFLICT (farmer_id) DO NOTHING;
            """, (
                f['farmer_id'],
                f['name'],
                acc_num,
                f"farmer{f['farmer_id']}@okaxis" if idx % 2 == 0 else None,
                True if idx % 2 == 0 else False,
                f"PAYOUT-ACC-{f['farmer_id']}"
            ))
    print(f"Seeded bank payout accounts for {len(farmers)} farmers (some with UPI, some bank-only).")

    # Seed hub staff for hubs
    hubs = fetch_all("SELECT hub_id, hub_name, district FROM hubs LIMIT 15;")
    users = fetch_all("SELECT user_id, role, name FROM users WHERE role IN ('hub_operator', 'hub_staff', 'hub_manager') LIMIT 10;")
    if hubs and users:
        with get_db_cursor(commit=True) as cur:
            for i, u in enumerate(users):
                h = hubs[i % len(hubs)]
                cur.execute("""
                    INSERT INTO hub_staff (hub_id, user_id, staff_role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (hub_id, user_id) DO NOTHING;
                """, (h['hub_id'], u['user_id'], 'MANAGER' if i == 0 else 'INSPECTOR'))
                cur.execute("UPDATE users SET assigned_hub_id = %s WHERE user_id = %s;", (h['hub_id'], u['user_id']))
                cur.execute("UPDATE hubs SET manager_id = %s WHERE hub_id = %s AND manager_id IS NULL;", (u['user_id'], h['hub_id']))
        print("Associated hub staff and managers with operating hubs.")

if __name__ == '__main__':
    run_migration()
