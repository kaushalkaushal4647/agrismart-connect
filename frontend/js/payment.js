/**
 * payment.js — AgriSmart Connect Razorpay Integration
 *
 * Flow:
 *   1. createOrderAndPay(order_id) — called after internal order is created
 *   2. Calls POST /api/payment/create-order to get Razorpay order details
 *   3. Opens Razorpay Checkout modal
 *   4. On success: calls POST /api/payment/verify with payment details
 *   5. On verify success: shows confirmation, redirects to orders page
 *   6. On failure: shows error, offers retry
 *
 * Security:
 *   - RAZORPAY_KEY_SECRET is NEVER in this file
 *   - Amount is NOT sent from here to backend — backend reads from DB
 *   - Payment verification is done server-side with HMAC-SHA256
 */

// ─────────────────────────────────────────────────────────────────────────────
// MAIN ENTRY POINT — called after internal order creation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Initiate Razorpay payment for an already-created internal order.
 * @param {number} internalOrderId  - Our PostgreSQL orders.order_id
 * @param {object} options          - Optional config overrides
 * @param {string} options.customerName
 * @param {string} options.customerEmail
 * @param {string} options.customerPhone
 * @param {function} options.onSuccess  - Called with { order_id, payment_id } on success
 * @param {function} options.onFailure  - Called with { error } on failure
 * @param {function} options.onDismiss  - Called when modal is closed without payment
 */
async function createOrderAndPay(internalOrderId, options = {}) {
    const payBtn = options.buttonEl || null;

    try {
        _setPayButtonState(payBtn, 'loading');

        // ── STEP 1: Get Razorpay Order from backend ────────────────────────
        const orderRes = await apiFetch('/payment/create-order', {
            method: 'POST',
            body: JSON.stringify({ order_id: internalOrderId })
        });

        if (!orderRes || !orderRes.success) {
            const msg = orderRes?.message || 'Failed to initialize payment. Please try again.';
            _setPayButtonState(payBtn, 'idle');
            _showPaymentError(msg);
            if (options.onFailure) options.onFailure({ error: msg });
            return;
        }

        const {
            razorpay_order_id,
            amount,        // paise
            amount_inr,    // display
            currency,
            key_id,
            payment_mode
        } = orderRes;

        // ── STEP 2: Build Razorpay Checkout options ────────────────────────
        const rzpOptions = {
            key:         key_id,                   // rzp_test_xxx — safe to expose
            amount:      amount,                    // in paise
            currency:    currency || 'INR',
            name:        'AgriSmart Connect',
            description: `Order #${internalOrderId} — Farm Fresh Produce`,
            image:       '/css/logo.png',           // shown in modal (optional)
            order_id:    razorpay_order_id,

            // Pre-fill customer info if available
            prefill: {
                name:    options.customerName  || '',
                email:   options.customerEmail || '',
                contact: options.customerPhone || '',
            },

            notes: {
                internal_order_id: String(internalOrderId),
                platform: 'AgriSmartConnect'
            },

            theme: { color: '#16a34a' },            // AgriSmart green

            // ── SUCCESS HANDLER ──────────────────────────────────────────────
            handler: async function (response) {
                _setPayButtonState(payBtn, 'verifying');
                _showPaymentStatus('verifying');

                try {
                    const verifyRes = await apiFetch('/payment/verify', {
                        method: 'POST',
                        body: JSON.stringify({
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_order_id:   response.razorpay_order_id,
                            razorpay_signature:  response.razorpay_signature,
                            order_id:            internalOrderId
                        })
                    });

                    if (verifyRes && verifyRes.success) {
                        _setPayButtonState(payBtn, 'success');
                        _showPaymentSuccess({
                            orderId:    internalOrderId,
                            paymentId:  response.razorpay_payment_id,
                            gross:      verifyRes.gross_amount,
                            commission: verifyRes.commission,
                            farmer:     verifyRes.farmer_amount,
                            mode:       payment_mode
                        });

                        if (options.onSuccess) {
                            options.onSuccess({
                                order_id:   internalOrderId,
                                payment_id: response.razorpay_payment_id
                            });
                        } else {
                            // Default: redirect to orders after 2.5s
                            setTimeout(() => {
                                window.location.href = '/orders.html';
                            }, 2500);
                        }
                    } else {
                        const errMsg = verifyRes?.message || 'Payment verification failed.';
                        _setPayButtonState(payBtn, 'idle');
                        _showPaymentError(errMsg);
                        if (options.onFailure) options.onFailure({ error: errMsg });
                    }
                } catch (verifyErr) {
                    console.error('[Payment] Verify error:', verifyErr);
                    _setPayButtonState(payBtn, 'idle');
                    _showPaymentError(
                        'Payment verification failed. If money was deducted, contact support. ' +
                        'Your order will be confirmed automatically via webhook.'
                    );
                }
            },

            // ── MODAL CLOSE WITHOUT PAYMENT ──────────────────────────────────
            modal: {
                ondismiss: function () {
                    _setPayButtonState(payBtn, 'idle');
                    _showPaymentStatus(null); // clear status
                    if (options.onDismiss) options.onDismiss();
                }
            }
        };

        // ── STEP 3: Open Razorpay Checkout ────────────────────────────────
        if (typeof Razorpay === 'undefined') {
            _setPayButtonState(payBtn, 'idle');
            _showPaymentError('Razorpay SDK not loaded. Please check your internet connection and try again.');
            return;
        }

        const rzp = new Razorpay(rzpOptions);

        rzp.on('payment.failed', function (response) {
            console.error('[Payment] Failed:', response.error);
            _setPayButtonState(payBtn, 'idle');
            _showPaymentError(
                response.error?.description ||
                `Payment failed (${response.error?.reason}). Please try again.`
            );
            if (options.onFailure) {
                options.onFailure({ error: response.error });
            }
        });

        rzp.open();

    } catch (err) {
        console.error('[Payment] createOrderAndPay error:', err);
        _setPayButtonState(payBtn, 'idle');
        const displayErr = err.message || 'An unexpected error occurred. Please try again.';
        _showPaymentError(displayErr);
        if (options.onFailure) options.onFailure({ error: displayErr });
    }
}


// ─────────────────────────────────────────────────────────────────────────────
// COMBINED FLOW — create internal order THEN pay (for consumer.html)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Full checkout flow:
 *   1. Create internal order via POST /api/orders
 *   2. Create Razorpay order and open checkout
 *
 * @param {object} orderPayload  - Body for POST /api/orders
 * @param {object} options       - Same options as createOrderAndPay
 */
async function checkoutAndPay(orderPayload, options = {}) {
    const payBtn = options.buttonEl || null;

    try {
        _setPayButtonState(payBtn, 'loading', 'Creating order...');

        const orderRes = await apiFetch('/orders', {
            method: 'POST',
            body: JSON.stringify(orderPayload)
        });

        if (!orderRes || (orderRes.status !== 'success' && !orderRes.order_id && !orderRes.order?.order_id)) {
            const errMsg = orderRes?.message || 'Failed to create order.';
            _setPayButtonState(payBtn, 'idle');
            _showPaymentError(errMsg);
            if (options.onFailure) options.onFailure({ error: errMsg });
            return;
        }

        const internalOrderId = orderRes.order_id || orderRes.order?.order_id || orderRes.id || (orderRes.data && (orderRes.data.order_id || orderRes.data.id));
        if (!internalOrderId) {
            _setPayButtonState(payBtn, 'idle');
            _showPaymentError('Order created but order ID missing. Please refresh and try again.');
            return;
        }

        // Now proceed to Razorpay payment
        await createOrderAndPay(internalOrderId, options);

    } catch (err) {
        console.error('[Payment] checkoutAndPay error:', err);
        _setPayButtonState(payBtn, 'idle');
        const displayErr = err.message || 'Order creation failed. Please try again.';
        _showPaymentError(displayErr);
        if (options.onFailure) options.onFailure({ error: displayErr });
    }
}


// ─────────────────────────────────────────────────────────────────────────────
// UI HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function _setPayButtonState(btn, state, customText) {
    if (!btn) return;
    const states = {
        idle:       { text: btn.dataset.idleText || 'Pay Now 💳', disabled: false },
        loading:    { text: customText || 'Creating order...', disabled: true },
        verifying:  { text: '🔒 Verifying payment...', disabled: true },
        success:    { text: '✅ Payment Confirmed!', disabled: true },
    };
    const s = states[state] || states.idle;
    btn.textContent = s.text;
    btn.disabled    = s.disabled;
    btn.style.opacity = s.disabled ? '0.7' : '1';
}

function _showPaymentStatus(status) {
    const el = document.getElementById('payment-status-msg');
    if (!el) return;
    if (!status) { el.style.display = 'none'; return; }
    const map = {
        verifying: { cls: 'alert-info',    text: '🔒 Verifying your payment securely...' }
    };
    const s = map[status];
    if (!s) return;
    el.className = `alert ${s.cls}`;
    el.textContent = s.text;
    el.style.display = 'block';
}

function _showPaymentSuccess({ orderId, paymentId, gross, commission, farmer, mode }) {
    const el = document.getElementById('payment-status-msg');
    const testBadge = (mode === 'test') ? ' <span style="font-size:0.75em;opacity:0.8;">[TEST MODE]</span>' : '';
    const html = `
        <div style="text-align:center; padding:1rem;">
            <div style="font-size:3rem; margin-bottom:0.5rem;">✅</div>
            <h3 style="color:#15803d; margin:0 0 0.5rem 0;">Payment Successful!${testBadge}</h3>
            <p style="margin:0 0 0.25rem; font-size:0.95rem;">Order <strong>#${orderId}</strong> is confirmed.</p>
            <p style="margin:0; font-size:0.85rem; color:#555;">Payment ID: <code>${paymentId}</code></p>
            ${gross ? `
            <div style="margin-top:0.85rem; background:#f0fdf4; border-radius:8px; padding:0.75rem; font-size:0.85rem; text-align:left;">
                <div style="display:flex;justify-content:space-between;"><span>Total Paid:</span><strong>₹${parseFloat(gross).toFixed(2)}</strong></div>
                <div style="display:flex;justify-content:space-between;color:#888;"><span>Platform Commission (${commission ? Math.round((commission/gross)*100) : 10}%):</span><span>₹${parseFloat(commission||0).toFixed(2)}</span></div>
                <div style="display:flex;justify-content:space-between;color:#166534;"><span>Farmer Share:</span><strong>₹${parseFloat(farmer||0).toFixed(2)}</strong></div>
            </div>` : ''}
            <p style="margin-top:0.75rem; font-size:0.8rem; color:#888;">Redirecting to My Orders...</p>
        </div>
    `;
    if (el) {
        el.className = 'alert';
        el.style.cssText = 'display:block; background:#f0fdf4; border:1px solid #86efac; border-radius:12px; padding:1rem;';
        el.innerHTML = html;
    } else {
        // Fallback: inject into body
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position:fixed; top:0; left:0; right:0; bottom:0;
            background:rgba(0,0,0,0.5); z-index:9999;
            display:flex; align-items:center; justify-content:center;
        `;
        overlay.innerHTML = `
            <div style="background:#fff; border-radius:16px; padding:2rem; max-width:400px; width:90%; box-shadow:0 20px 60px rgba(0,0,0,0.3);">
                ${html}
            </div>
        `;
        document.body.appendChild(overlay);
    }
}

function _showPaymentError(message) {
    const el = document.getElementById('payment-status-msg');
    if (el) {
        el.className = 'alert';
        el.style.cssText = 'display:block; background:#fef2f2; border:1px solid #fca5a5; border-radius:8px; padding:0.75rem 1rem; color:#b91c1c;';
        el.textContent = `⚠️ ${message}`;
    } else {
        alert(`Payment Error: ${message}`);
    }
}
