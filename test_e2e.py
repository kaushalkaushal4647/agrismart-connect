"""
End-to-end workflow test for AgriSmart Connect.
Tests the complete farmer -> order -> hub -> delivery -> settlement pipeline.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import json

BASE = "http://localhost:5000/api"
TOKEN = None
USER_ID = None

def get(path, token=None, desc=""):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(BASE + path, headers=headers, timeout=5)
    status = "OK" if r.status_code < 400 else "FAIL"
    print(f"[{status}] [{r.status_code}] GET {path} -- {desc}")
    if r.status_code >= 400:
        try:
            print(f"  ERR: {r.json()}")
        except:
            print(f"  RAW: {r.text[:100]}")
    return r

def post(path, body, token=None, desc=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(BASE + path, json=body, headers=headers, timeout=5)
    status = "OK" if r.status_code < 400 else "FAIL"
    print(f"[{status}] [{r.status_code}] POST {path} -- {desc}")
    if r.status_code >= 400:
        try:
            print(f"  ERR: {r.json()}")
        except:
            print(f"  RAW: {r.text[:100]}")
    return r

print("=" * 60)
print("AgriSmart Connect -- E2E Workflow Test")
print("=" * 60)

# 1. Login as admin
print("\n--- 1. Login as Admin ---")
r = post("/auth/login", {"identifier": "admin@demo.com", "password": "Password@123"}, desc="Admin login")
if r.status_code == 200:
    TOKEN = r.json().get("token")
    USER_ID = r.json().get("user", {}).get("user_id")
    print(f"  Admin token: {TOKEN[:30]}... (user_id={USER_ID})")
else:
    print("  Admin login failed!")

# 2. Check hubs
print("\n--- 2. Hub Network ---")
r = get("/hubs", desc="All Tamil Nadu hubs")
if r.status_code == 200:
    hubs = r.json().get("hubs", [])
    print(f"  Found {len(hubs)} hubs across Tamil Nadu")
    if hubs:
        print(f"  Sample: {hubs[0].get('hub_name')} ({hubs[0].get('district')})")

# 3. Marketplace listings
print("\n--- 3. Marketplace Produce ---")
r = get("/marketplace", desc="Active marketplace listings")
if r.status_code == 200:
    items = r.json().get("produce", [])
    print(f"  Found {len(items)} produce listings")
    if items:
        print(f"  Sample: {items[0].get('crop_name')} @ Rs.{items[0].get('minimum_price_per_kg')}/kg")

# 4. Admin dashboard
print("\n--- 4. Admin Dashboard ---")
if TOKEN:
    r = get("/admin/dashboard", token=TOKEN, desc="Admin overview")
    if r.status_code == 200:
        ov = r.json().get("overview", {})
        print(f"  Farmers: {ov.get('total_farmers')}, Buyers: {ov.get('total_buyers')}")
        print(f"  Orders: {ov.get('total_orders')}, Active Hubs: {ov.get('active_hubs')}")
        print(f"  Total GMV: Rs.{ov.get('total_sales')}")
        print(f"  Pending Payouts: Rs.{ov.get('pending_payouts')}")

# 5. Payouts check
print("\n--- 5. Farmer Payouts ---")
if TOKEN:
    r = get("/payments/payouts", token=TOKEN, desc="Farmer payout ledger")
    if r.status_code == 200:
        payouts = r.json().get("payouts", [])
        print(f"  Found {len(payouts)} farmer payout records")

# 6. Delivery payouts
print("\n--- 6. Delivery Partner Payouts ---")
if TOKEN:
    r = get("/payments/delivery-payouts", token=TOKEN, desc="Driver payout ledger")
    if r.status_code == 200:
        payouts = r.json().get("payouts", [])
        print(f"  Found {len(payouts)} delivery partner payouts")

# 7. Orders list
print("\n--- 7. Active Orders ---")
if TOKEN:
    r = get("/orders", token=TOKEN, desc="All orders")
    if r.status_code == 200:
        orders = r.json().get("orders", [])
        print(f"  Found {len(orders)} orders")
        for o in orders[:3]:
            print(f"  Order #{o.get('order_id')}: {o.get('order_status')} - Rs.{o.get('total_amount')}")

# 8. Logistics
print("\n--- 8. AI Logistics ---")
r = get("/logistics/dashboard", desc="Logistics dashboard")
if r.status_code == 200:
    ov = r.json().get("overview", {})
    print(f"  Active Hubs: {ov.get('active_hubs')}, Today Orders: {ov.get('today_orders')}")
    print(f"  Predicted Demand: {ov.get('predicted_demand_kg')} kg")

# 9. Payment key
print("\n--- 9. Payment Config ---")
r = get("/payment/key", desc="Razorpay key")
if r.status_code == 200:
    print(f"  Key: {r.json().get('key_id')}, Mode: {r.json().get('payment_mode')}")

print("\n" + "=" * 60)
print("E2E WORKFLOW TEST COMPLETE")
print("=" * 60)
