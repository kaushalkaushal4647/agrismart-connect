from backend.database import fetch_all, fetch_one

# Tables
tables = fetch_all("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
print("=== TABLES ===")
for t in tables:
    print(" -", t['table_name'])

# Hubs
print("\n=== HUBS ===")
hubs = fetch_all("SELECT hub_id, hub_name, district, status FROM hubs LIMIT 10")
for h in hubs:
    print(h)

# Users by role
print("\n=== USER ROLES ===")
roles = fetch_all("SELECT role, COUNT(*) as cnt FROM users GROUP BY role ORDER BY cnt DESC")
for r in roles:
    print(r)

# Recent orders
print("\n=== RECENT ORDERS ===")
orders = fetch_all("SELECT order_id, order_status, total_amount FROM orders ORDER BY order_id DESC LIMIT 5")
for o in orders:
    print(o)
