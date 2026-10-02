# AgriSmart Connect — Payment Setup Guide

## Quick Start

### 1. Install Dependencies
```bash
python -m pip install -r backend/requirements.txt
```

### 2. Configure Environment Variables
Open `.env` and replace the placeholder values with your real Razorpay **Test** credentials:

```env
RAZORPAY_KEY_ID=rzp_test_YOUR_ACTUAL_KEY_ID
RAZORPAY_KEY_SECRET=YOUR_ACTUAL_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET
PLATFORM_COMMISSION_PERCENT=10
PAYMENT_MODE=test
```

**Where to get these:**
| Variable | Location |
|---|---|
| `RAZORPAY_KEY_ID` | [Razorpay Dashboard](https://dashboard.razorpay.com/app/keys) → Settings → API Keys → Generate Test Key |
| `RAZORPAY_KEY_SECRET` | Same page — copy immediately, shown only once |
| `RAZORPAY_WEBHOOK_SECRET` | Dashboard → Webhooks → Create Webhook → set a secret string |

> ⚠️ **NEVER** commit `.env` to Git. It is already listed in `.gitignore`.

### 3. Run the Database Migration
```bash
python run_payment_migration.py
```

This creates 7 new tables (additive only — no data loss):
- `razorpay_orders`
- `razorpay_payments`
- `webhook_events`
- `farmer_accounts`
- `transfers`
- `refunds`
- Alters `payments` table to add Razorpay columns

### 4. Start the Backend
```bash
python backend/app.py
```
Or using the provided batch file:
```
start_agrismart.bat
```

### 5. Test a Payment (Consumer Flow)

1. Open `http://localhost:5000`
2. Register/Login as a **Consumer**
3. Go to **Fresh Produce** page (`/consumer.html`)
4. Select any produce → set quantity → enter delivery address
5. Click **"Pay & Confirm Order 💳"**
6. Razorpay Test Checkout modal opens
7. Use test card: `4111 1111 1111 1111` | Expiry: any future date | CVV: any 3 digits
8. Complete payment → verify green success banner appears
9. You are redirected to `/orders.html`

### 6. Verify Database After Payment
```sql
-- Check order was confirmed
SELECT order_id, payment_status, order_status FROM orders ORDER BY order_id DESC LIMIT 5;

-- Check Razorpay order record
SELECT * FROM razorpay_orders ORDER BY created_at DESC LIMIT 3;

-- Check payment capture
SELECT * FROM razorpay_payments ORDER BY created_at DESC LIMIT 3;

-- Check payment table (with commission breakdown)
SELECT order_id, gross_amount, commission_percent, commission_amount,
       farmer_amount, settlement_status FROM payments ORDER BY order_id DESC LIMIT 5;

-- Check farmer settlement (SIMULATED in test mode)
SELECT * FROM transfers ORDER BY created_at DESC LIMIT 5;

-- Check webhook events
SELECT event_id, event_type, processed, created_at FROM webhook_events ORDER BY created_at DESC LIMIT 5;
```

Expected result:
```
gross_amount = total paid by customer
commission_amount = gross × 10%
farmer_amount = gross - commission
settlement_status = SIMULATED
```

### 7. Test Webhook (Local)

Razorpay cannot reach `localhost` directly. Use [ngrok](https://ngrok.com) to expose your local server:

```bash
ngrok http 5000
```

Then in Razorpay Dashboard → Webhooks:
- URL: `https://YOUR-NGROK-ID.ngrok.io/api/webhooks/razorpay`
- Events: `payment.authorized`, `payment.captured`, `payment.failed`
- Secret: same as `RAZORPAY_WEBHOOK_SECRET` in your `.env`

---

## Architecture Overview

```
Consumer → consumer.html
    ↓ (click "Pay & Confirm")
POST /api/orders
    ↓ Creates order, reserves inventory
POST /api/payments/create-order
    ↓ Reads total from DB, creates Razorpay Order
Razorpay Checkout.js modal
    ↓ Customer pays with test card
POST /api/payments/verify
    ↓ HMAC-SHA256 signature verified server-side
    ↓ confirm_payment_and_settle() runs in DB transaction
    ↓ Orders → confirmed, inventory reduced, farmer settlement SIMULATED
POST /api/webhooks/razorpay
    ↓ payment.captured event received
    ↓ Idempotency check (webhook_events table)
    ↓ Final DB confirmation if verify hadn't already done it
```

---

## Security Notes

| Concern | How it's handled |
|---|---|
| Key Secret exposed to JS | ❌ Never — only `key_id` sent to frontend |
| Frontend amount trusted | ❌ Never — amount always fetched from DB |
| Signature not verified | ✅ HMAC-SHA256 via `client.utility.verify_payment_signature()` |
| Duplicate webhooks | ✅ `webhook_events.event_id` unique constraint |
| Wrong user pays another's order | ✅ `buyer_user_id` ownership check on every endpoint |
| Inventory double-deducted | ✅ `transfers` existence check + `ON CONFLICT DO NOTHING` |
| Stack trace in API response | ✅ Never — errors are logged server-side only |

---

## API Endpoints Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/payments/create-order` | Consumer JWT | Create Razorpay Order from internal order_id |
| `POST` | `/api/payments/verify` | Consumer JWT | Verify HMAC signature + confirm payment |
| `GET` | `/api/payments/<order_id>` | JWT | Get payment details for an order |
| `POST` | `/api/payments/refund` | JWT | Initiate Razorpay refund |
| `GET` | `/api/payments/admin/summary` | Admin JWT | Aggregated payment metrics |
| `GET` | `/api/payments/farmer-account/<id>` | JWT | Farmer Route account status |
| `POST` | `/api/webhooks/razorpay` | Webhook signature | Razorpay event handler |

---

## Commission Configuration

Platform commission is configurable via `.env`:
```env
PLATFORM_COMMISSION_PERCENT=10
```

This is read by `Config.PLATFORM_COMMISSION_PERCENT` and applied in:
- `routes/orders.py` — at order creation (platform_fee column)
- `services/payment_service.py` — at payment confirmation (commission stored per payment)
- `routes/orders.py` — at delivery (farmer_payouts table)

---

## Farmer Settlement (Current: SIMULATED)

In Test Mode, every payment creates `transfers` records with `status='SIMULATED'`.
No real money is transferred to farmers.

DB record:
```
transfers.status = 'SIMULATED'
transfers.settlement_status = 'SIMULATED'
payments.settlement_status = 'SIMULATED'
```

### Migrating to Real Farmer Settlement (Production)

1. Activate **Razorpay Route/Marketplace** on your live account
2. Complete KYC for your business
3. Onboard each farmer via `/api/payments/farmer-account/<id>` (calls `razorpay_route.create_farmer_account()`)
4. Store `farmer_accounts.razorpay_account_id` per farmer
5. Set `PAYMENT_MODE=live` in `.env`
6. Use Live API keys (`rzp_live_...`)
7. Set up production webhook URL (HTTPS required)
8. `razorpay_route.create_transfer()` will then call the real Route API instead of simulating

---

## Test Cards (Razorpay Test Mode)

| Card Number | Network | Result |
|---|---|---|
| `4111 1111 1111 1111` | Visa | Success |
| `5267 3181 8797 5449` | Mastercard | Success |
| `4000 0000 0000 0002` | Visa | Failure |

- Expiry: any future date
- CVV: any 3 digits
- OTP: `1234` (test mode)

---

## Files Changed / Created

### New Files
| File | Purpose |
|---|---|
| `database/payment_migration.sql` | Additive DB migration — run once |
| `run_payment_migration.py` | Migration runner script |
| `backend/services/razorpay_service.py` | Razorpay SDK wrapper |
| `backend/services/payment_service.py` | Post-payment business logic |
| `backend/services/razorpay_route.py` | Route/marketplace stub (SIMULATED) |
| `backend/routes/webhooks.py` | Webhook handler with idempotency |
| `frontend/js/payment.js` | Frontend Razorpay Checkout integration |
| `docs/PAYMENT_SETUP.md` | This file |

### Modified Files
| File | What Changed |
|---|---|
| `.env` | Added Razorpay + commission config |
| `backend/config.py` | Added `RAZORPAY_*` + `PLATFORM_COMMISSION_PERCENT` |
| `backend/requirements.txt` | Added `razorpay>=1.4.0` |
| `backend/app.py` | Registered `webhooks_bp` |
| `backend/routes/payments.py` | Full Razorpay endpoints (create-order, verify, refund) |
| `backend/routes/orders.py` | Commission now reads from `Config` |
| `frontend/consumer.html` | Razorpay Checkout.js loaded, Pay button wired |
