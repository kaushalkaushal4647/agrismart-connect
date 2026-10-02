"""Quick API endpoint check to find issues."""
import requests
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://localhost:5000/api"

def check(method, path, body=None, desc=""):
    url = BASE + path
    try:
        if method == "GET":
            r = requests.get(url, timeout=5)
        else:
            r = requests.post(url, json=body, timeout=5)
        status = r.status_code
        ok = "OK" if status < 400 else "FAIL"
        print(f"[{ok}] [{status}] {method} {path} -- {desc}")
        if status >= 400:
            try:
                print(f"    ERROR: {r.json()}")
            except:
                print(f"    RAW: {r.text[:200]}")
    except Exception as e:
        print(f"[ERR] {method} {path}: {e}")

print("=== AgriSmart Connect API Health Check ===\n")
check("GET", "/health", desc="Health check")
check("GET", "/hubs", desc="List hubs")
check("GET", "/hubs?status=active", desc="Active hubs")
check("GET", "/marketplace/produce", desc="Marketplace listings")
check("GET", "/crops", desc="Crops catalog")
check("GET", "/logistics/dashboard", desc="Logistics dashboard")
check("GET", "/logistics/demand", desc="Demand forecasts")
check("GET", "/logistics/map-data", desc="Map data")
check("GET", "/admin/dashboard", desc="Admin dashboard (auth required)")
check("GET", "/deliveries", desc="Deliveries (auth required)")
check("GET", "/orders", desc="Orders (auth required)")
check("GET", "/farmers/profile", desc="Farmer profile (auth required)")
check("GET", "/payment/key", desc="Payment key")
check("GET", "/auth/profile", desc="Auth profile (auth required)")
