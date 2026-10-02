/**
 * AgriSmart Connect - Orders, Cart & B2B Demand Matching Controller
 */

const CART_KEY = 'agrismart_cart';

// ==========================================
// 1. CART MANAGEMENT (LOCAL STORAGE)
// ==========================================
function getCart() {
    try {
        return JSON.parse(localStorage.getItem(CART_KEY)) || [];
    } catch {
        return [];
    }
}

function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    updateCartCount();
}

function addToCart(item, quantityKg) {
    let cart = getCart();
    const existingIndex = cart.findIndex(i => i.produce_id === item.produce_id);

    if (existingIndex > -1) {
        cart[existingIndex].quantity_kg += Number(quantityKg);
    } else {
        cart.push({
            produce_id: item.produce_id,
            crop_name: item.crop_name,
            variety_name: item.variety_name,
            price_per_kg: Number(item.minimum_price_per_kg),
            quantity_kg: Number(quantityKg),
            available_kg: Number(item.available_quantity_kg),
            farm_name: item.farm_name,
            farmer_name: item.farmer_name,
            hub_id: item.preferred_hub_id
        });
    }

    saveCart(cart);
    showToast(`Added ${quantityKg} kg of ${item.crop_name} to cart!`, 'success');
}

function removeFromCart(produceId) {
    let cart = getCart().filter(i => i.produce_id !== produceId);
    saveCart(cart);
    renderCartModal();
}

function clearCart() {
    localStorage.removeItem(CART_KEY);
    updateCartCount();
}

function updateCartCount() {
    const badge = document.getElementById('cart-badge');
    if (badge) {
        const cart = getCart();
        const count = cart.reduce((acc, i) => acc + 1, 0);
        badge.innerText = count;
        badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
}

// ==========================================
// 2. CHECKOUT & ORDER CREATION
// ==========================================
async function checkoutCart(deliveryAddress, deliveryLat, deliveryLon) {
    const user = getCurrentUser();
    if (!user) {
        showToast('Please sign in to place an order.', 'error');
        setTimeout(() => window.location.href = '/login.html', 1200);
        return;
    }

    const cart = getCart();
    if (!cart.length) {
        showToast('Your cart is empty.', 'error');
        return;
    }

    const payload = {
        delivery_address: deliveryAddress,
        delivery_latitude: deliveryLat,
        delivery_longitude: deliveryLon,
        hub_id: cart[0].hub_id || null,
        items: cart.map(i => ({
            produce_id: i.produce_id,
            quantity_kg: i.quantity_kg,
            price_per_kg: i.price_per_kg
        }))
    };

    try {
        const res = await apiFetch('/orders', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        clearCart();
        showToast('Order placed successfully! Farmers and collection hub notified.', 'success');
        setTimeout(() => {
            window.location.href = '/orders.html';
        }, 1200);

    } catch (err) {
        showToast(err.message || 'Failed to place order.', 'error');
    }
}

// ==========================================
// 3. LOAD ORDERS LIST & STATUS PIPELINE
// ==========================================
async function loadOrders() {
    const container = document.getElementById('orders-list-container');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--slate-400);">Loading your orders...</div>';

    try {
        let orders = [];
        try {
            const res = await apiFetch('/orders');
            orders = res.orders || [];
        } catch (apiErr) {
            console.warn('Could not fetch server orders:', apiErr);
        }

        try {
            const localConsignments = JSON.parse(localStorage.getItem('agrismart_retailer_consignments') || '[]');
            orders = [...localConsignments, ...orders];
        } catch (e) {}

        if (!orders.length) {
            container.innerHTML = `
                <div style="text-align:center;padding:4rem 1rem;background:var(--white);border-radius:var(--radius-lg);border:1px solid var(--slate-200);">
                    <div style="font-size:2.5rem;margin-bottom:1rem;">📦</div>
                    <h3 style="font-size:1.35rem;margin-bottom:0.5rem;">No Active Orders Found</h3>
                    <p style="color:var(--slate-500);font-size:0.95rem;max-width:400px;margin:0 auto 1.5rem;">
                        Browse the marketplace or create bulk requirements to initiate farm-to-hub collection.
                    </p>
                    <a href="/marketplace.html" class="btn btn-primary btn-sm">Explore Marketplace</a>
                </div>
            `;
            return;
        }

        container.innerHTML = orders.map(o => {
            const dateFormatted = new Date(o.order_date).toLocaleDateString('en-IN', {
                day: 'numeric',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });

            const stepperHtml = renderOrderStepper(o.order_status);

            return `
                <div class="order-card" style="background:var(--white);border:1px solid var(--slate-200);border-radius:var(--radius-lg);padding:1.75rem;margin-bottom:1.5rem;box-shadow:var(--shadow-sm);">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem;margin-bottom:1.25rem;border-bottom:1px solid var(--slate-100);padding-bottom:1rem;">
                        <div>
                            <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.35rem;">
                                <h3 style="font-size:1.25rem;">Order #${o.order_id}</h3>
                                <span class="status-badge ${getOrderBadgeClass(o.order_status)}">${o.order_status.replace('_', ' ').toUpperCase()}</span>
                                <span class="status-badge" style="background:#ede9fe;color:#5b21b6;">PAYMENT: ${o.payment_status.toUpperCase()}</span>
                            </div>
                            <div style="font-size:0.85rem;color:var(--slate-500);">
                                Placed on: <strong>${dateFormatted}</strong> | Assigned Hub: <strong>${o.hub_name || 'Regional Hub'}</strong>
                            </div>
                        </div>

                        <div style="text-align:right;">
                            <div style="font-size:0.8rem;color:var(--slate-500);">Total Bill</div>
                            <div style="font-family:'Outfit',sans-serif;font-size:1.5rem;font-weight:800;color:var(--primary-dark);">₹${Number(o.total_amount).toFixed(2)}</div>
                            <div style="font-size:0.75rem;color:var(--slate-400);">(Subtotal: ₹${o.subtotal} + Delivery: ₹${o.delivery_fee} + Fee: ₹${o.platform_fee})</div>
                        </div>
                    </div>

                    <!-- Pipeline Stepper -->
                    <div style="margin:1.5rem 0;">
                        ${stepperHtml}
                    </div>

                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;margin-top:1.25rem;padding-top:1rem;border-top:1px solid var(--slate-100);">
                        <div style="font-size:0.85rem;color:var(--slate-600);">
                            📍 Delivery Address: <strong>${o.delivery_address}</strong>
                            ${o.tracking_reference ? ` | Tracking: <code style="background:var(--slate-100);padding:0.2rem 0.4rem;border-radius:4px;">${o.tracking_reference}</code>` : ''}
                        </div>

                        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;">
                            ${o.order_status !== 'delivered' && o.order_status !== 'cancelled' ? `
                                <button class="btn btn-outline btn-sm" style="color:#047857;border-color:#10b981;background:#ecfdf5;font-weight:600;" onclick="advanceOrderStatus('${o.order_id}')" title="Advance to next fulfillment stage">
                                    ⚡ Advance Step
                                </button>
                            ` : ''}
                            ${o.order_status === 'placed' ? `
                                <button class="btn btn-outline btn-sm" style="color:var(--status-danger);" onclick="cancelOrder('${o.order_id}')">Cancel Order</button>
                            ` : ''}
                            <button class="btn btn-outline btn-sm" onclick="viewOrderDetails('${o.order_id}')">View Breakdown</button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        container.innerHTML = `<div style="color:var(--status-danger);text-align:center;padding:2rem;">Failed to load orders: ${err.message}</div>`;
    }
}

// Stepper Generator
function renderOrderStepper(status) {
    const steps = [
        { id: 'placed', label: 'Order Placed' },
        { id: 'farmer_assigned', label: 'Farmer Assigned' },
        { id: 'collecting', label: 'Collection' },
        { id: 'at_hub', label: 'At Hub QA' },
        { id: 'packed', label: 'Packed' },
        { id: 'out_for_delivery', label: 'Out for Delivery' },
        { id: 'delivered', label: 'Delivered' }
    ];

    if (status === 'cancelled') {
        return `
            <div style="background:#fef2f2;border:1px solid #fecaca;padding:0.75rem 1rem;border-radius:var(--radius-md);color:#991b1b;font-size:0.9rem;font-weight:600;">
                ✕ This order was cancelled. Reserved produce has been released back to farmer inventory.
            </div>
        `;
    }

    const currentIndex = steps.findIndex(s => s.id === status);

    return `
        <div class="stepper-wrapper" style="display:flex;justify-content:space-between;position:relative;gap:0.5rem;overflow-x:auto;padding-bottom:0.5rem;">
            ${steps.map((s, idx) => {
                const isPassed = idx <= (currentIndex === -1 ? 0 : currentIndex);
                const isCurrent = idx === currentIndex;
                const dotColor = isPassed ? 'var(--primary)' : 'var(--slate-300)';
                const textColor = isPassed ? 'var(--slate-800)' : 'var(--slate-400)';
                return `
                    <div style="display:flex;flex-direction:column;align-items:center;flex:1;min-width:75px;text-align:center;">
                        <div style="width:24px;height:24px;border-radius:50%;background:${dotColor};color:white;display:flex;align-items:center;justify-content:center;font-size:0.75rem;font-weight:bold;margin-bottom:0.35rem;box-shadow:${isCurrent ? '0 0 8px rgba(34,197,94,0.6)' : 'none'};">
                            ${isPassed ? '✓' : idx + 1}
                        </div>
                        <span style="font-size:0.72rem;font-weight:${isCurrent ? '700' : '500'};color:${textColor};line-height:1.2;">${s.label}</span>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

function getOrderBadgeClass(status) {
    switch (status) {
        case 'placed': return 'badge-open';
        case 'confirmed':
        case 'farmer_assigned': return 'badge-open';
        case 'collecting':
        case 'at_hub':
        case 'quality_checked': return 'badge-matched';
        case 'packed':
        case 'out_for_delivery': return 'badge-available';
        case 'delivered': return 'badge-paid';
        case 'cancelled': return 'badge-danger';
        default: return 'badge-open';
    }
}

function getNextPipelineStep(status) {
    const pipeline = [
        { id: 'placed', label: 'Order Placed', nextId: 'farmer_assigned', nextLabel: 'Farmer Assignment' },
        { id: 'farmer_assigned', label: 'Farmer Assigned', nextId: 'collecting', nextLabel: 'Harvest Collection Run' },
        { id: 'collecting', label: 'Collection', nextId: 'at_hub', nextLabel: 'At Hub QA Inspection' },
        { id: 'at_hub', label: 'At Hub QA', nextId: 'packed', nextLabel: 'Sorting & Packaging' },
        { id: 'packed', label: 'Packed', nextId: 'out_for_delivery', nextLabel: 'Out for Delivery Dispatch' },
        { id: 'out_for_delivery', label: 'Out for Delivery', nextId: 'delivered', nextLabel: 'Delivered (e-POD Complete)' }
    ];

    const item = pipeline.find(p => p.id === status);
    return item ? { nextId: item.nextId, nextLabel: item.nextLabel } : null;
}

async function advanceOrderStatus(orderId) {
    const orderIdStr = String(orderId);
    const isConsignment = orderIdStr.startsWith('CONS-');

    if (isConsignment) {
        let localConsignments = JSON.parse(localStorage.getItem('agrismart_retailer_consignments') || '[]');
        const idx = localConsignments.findIndex(c => String(c.order_id) === orderIdStr);
        if (idx === -1) {
            showToast('Consignment not found in storage.', 'error');
            return;
        }

        const currentStatus = localConsignments[idx].order_status;
        const nextInfo = getNextPipelineStep(currentStatus);
        if (!nextInfo) {
            showToast(`Order #${orderId} is already completed (${currentStatus}).`, 'info');
            return;
        }

        localConsignments[idx].order_status = nextInfo.nextId;
        if (nextInfo.nextId === 'delivered') {
            localConsignments[idx].payment_status = 'escrow_released';
        }
        localStorage.setItem('agrismart_retailer_consignments', JSON.stringify(localConsignments));

        showToast(`Order #${orderId} advanced to "${nextInfo.nextLabel}"!`, 'success');
        loadOrders();
        return;
    }

    // Backend database order
    try {
        const res = await apiFetch(`/orders/${orderId}`);
        if (!res || !res.order) {
            showToast('Order not found on server.', 'error');
            return;
        }

        const currentStatus = res.order.order_status;
        const nextInfo = getNextPipelineStep(currentStatus);
        if (!nextInfo) {
            showToast(`Order #${orderId} is already completed (${currentStatus}).`, 'info');
            return;
        }

        await apiFetch(`/orders/${orderId}/status`, {
            method: 'PUT',
            body: JSON.stringify({ order_status: nextInfo.nextId })
        });

        showToast(`Order #${orderId} advanced to "${nextInfo.nextLabel}"!`, 'success');
        loadOrders();
    } catch (err) {
        showToast('Failed to update status: ' + err.message, 'error');
    }
}

// Auto-simulate all active orders through fulfillment pipeline
let simulationTimer = null;
function autoSimulateAllOrders() {
    if (simulationTimer) {
        clearInterval(simulationTimer);
        simulationTimer = null;
        showToast('Fulfillment simulation paused.', 'info');
        return;
    }

    showToast('🚀 Auto-simulating order fulfillment pipeline...', 'success');

    simulationTimer = setInterval(() => {
        let localConsignments = JSON.parse(localStorage.getItem('agrismart_retailer_consignments') || '[]');
        let advancedCount = 0;

        localConsignments = localConsignments.map(c => {
            if (c.order_status !== 'delivered' && c.order_status !== 'cancelled') {
                const nextInfo = getNextPipelineStep(c.order_status);
                if (nextInfo) {
                    c.order_status = nextInfo.nextId;
                    if (nextInfo.nextId === 'delivered') {
                        c.payment_status = 'escrow_released';
                    }
                    advancedCount++;
                }
            }
            return c;
        });

        if (advancedCount > 0) {
            localStorage.setItem('agrismart_retailer_consignments', JSON.stringify(localConsignments));
            loadOrders();
        } else {
            clearInterval(simulationTimer);
            simulationTimer = null;
            showToast('All active orders reached delivery completion!', 'success');
        }
    }, 3000);
}

async function cancelOrder(orderId) {
    if (!confirm('Are you sure you want to cancel this order? Reserved produce will be released.')) return;
    const orderIdStr = String(orderId);

    if (orderIdStr.startsWith('CONS-')) {
        let localConsignments = JSON.parse(localStorage.getItem('agrismart_retailer_consignments') || '[]');
        localConsignments = localConsignments.map(c => {
            if (String(c.order_id) === orderIdStr) {
                return { ...c, order_status: 'cancelled', payment_status: 'refunded' };
            }
            return c;
        });
        localStorage.setItem('agrismart_retailer_consignments', JSON.stringify(localConsignments));
        showToast('Consignment order cancelled.', 'info');
        loadOrders();
        return;
    }

    try {
        await apiFetch(`/orders/${orderId}/status`, {
            method: 'PUT',
            body: JSON.stringify({ order_status: 'cancelled' })
        });
        showToast('Order cancelled.', 'info');
        loadOrders();
    } catch (err) {
        showToast(err.message || 'Failed to cancel order.', 'error');
    }
}

async function viewOrderDetails(orderId) {
    const orderIdStr = String(orderId);

    // 1. Check if this is a wholesale/retailer consignment in local storage
    const localConsignments = JSON.parse(localStorage.getItem('agrismart_retailer_consignments') || '[]');
    const localMatch = localConsignments.find(c => String(c.order_id) === orderIdStr);

    if (localMatch) {
        renderConsignmentDetails(localMatch);
        return;
    }

    // 2. Otherwise retrieve from server database
    try {
        const res = await apiFetch(`/orders/${orderId}`);
        if (!res || !res.order) {
            showToast('Order details not found.', 'error');
            return;
        }
        renderServerOrderDetails(res.order, res.items || []);
    } catch (err) {
        showToast('Failed to load details: ' + err.message, 'error');
    }
}

function renderConsignmentDetails(c) {
    const nextInfo = getNextPipelineStep(c.order_status);
    const subtotalNum = parseFloat(c.subtotal || 11880);
    const qty = parseFloat(c.quantity_kg || 500);
    const unitPrice = (subtotalNum / qty).toFixed(2);

    const html = `
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:1rem;margin-bottom:1.25rem;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;">
                <div>
                    <span style="font-size:0.75rem;color:#64748b;font-weight:700;text-transform:uppercase;">Wholesale Contract Order</span>
                    <h4 style="margin:0.2rem 0;color:#0f172a;font-size:1.15rem;">Order #${c.order_id}</h4>
                    <div style="font-size:0.8rem;color:#64748b;">Assigned Hub: <strong>${c.hub_name || 'Regional Aggregation Center'}</strong></div>
                </div>
                <div style="text-align:right;">
                    <span class="status-badge ${getOrderBadgeClass(c.order_status)}">${c.order_status.replace(/_/g, ' ').toUpperCase()}</span>
                    <div style="margin-top:0.35rem;font-size:0.75rem;font-weight:700;color:#5b21b6;background:#ede9fe;padding:0.2rem 0.5rem;border-radius:99px;display:inline-block;">
                        🔒 ${c.payment_status.toUpperCase()}
                    </div>
                </div>
            </div>
            <div style="margin-top:0.75rem;padding-top:0.75rem;border-top:1px dashed #cbd5e1;font-size:0.8rem;color:#475569;display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
                <div>📍 <strong>Destination:</strong> ${c.delivery_address || 'Central Supermarket Store'}</div>
                <div>🏷️ <strong>Tracking:</strong> <code>${c.tracking_reference || 'AGRI-WHLS-DIRECT'}</code></div>
            </div>
        </div>

        <h4 style="font-size:0.95rem;margin:1rem 0 0.5rem;color:#1e293b;">Itemized Produce Breakdown</h4>
        <table style="width:100%;border-collapse:collapse;margin-bottom:1.25rem;font-size:0.85rem;">
            <thead>
                <tr style="border-bottom:2px solid #e2e8f0;text-align:left;color:#64748b;font-size:0.75rem;">
                    <th style="padding:0.5rem 0.25rem;">Produce / Variety</th>
                    <th style="padding:0.5rem 0.25rem;">Quality Grade</th>
                    <th style="padding:0.5rem 0.25rem;text-align:center;">Weight</th>
                    <th style="padding:0.5rem 0.25rem;text-align:right;">Rate</th>
                    <th style="padding:0.5rem 0.25rem;text-align:right;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                <tr style="border-bottom:1px solid #f1f5f9;">
                    <td style="padding:0.6rem 0.25rem;">
                        <strong>${c.crop_name || 'Wholesale Farm Produce'}</strong>
                        <div style="font-size:0.75rem;color:#64748b;">Consolidated Harvest Lot</div>
                    </td>
                    <td style="padding:0.6rem 0.25rem;">
                        <span style="background:#dcfce7;color:#166534;font-size:0.7rem;font-weight:700;padding:0.15rem 0.4rem;border-radius:4px;">Grade A Verified</span>
                        <div style="font-size:0.75rem;color:#64748b;margin-top:2px;">Regional Farmer Cluster</div>
                    </td>
                    <td style="padding:0.6rem 0.25rem;text-align:center;font-weight:700;">${qty} kg</td>
                    <td style="padding:0.6rem 0.25rem;text-align:right;">₹${unitPrice}/kg</td>
                    <td style="padding:0.6rem 0.25rem;text-align:right;font-weight:700;color:#0f172a;">₹${c.subtotal}</td>
                </tr>
            </tbody>
        </table>

        <!-- Cost Breakdown Card -->
        <div style="background:#f8fafc;border-radius:8px;padding:0.85rem 1rem;font-size:0.85rem;margin-bottom:1.5rem;">
            <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;color:#475569;">
                <span>Crop Harvest Subtotal</span>
                <strong>₹${c.subtotal}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;color:#475569;">
                <span>Cold-Chain Logistics & Direct Hub Haulage</span>
                <span>₹${c.delivery_fee}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;color:#475569;">
                <span>Hub Quality Inspection & Escrow Assurance</span>
                <span>₹${c.platform_fee}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding-top:0.5rem;border-top:1px solid #e2e8f0;font-size:1.05rem;font-weight:800;color:var(--primary-dark);">
                <span>Total Contract Value</span>
                <span>₹${Number(c.total_amount).toFixed(2)}</span>
            </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;padding-top:0.5rem;border-top:1px solid #f1f5f9;">
            ${nextInfo ? `
                <button class="btn btn-primary btn-sm" onclick="advanceOrderStatus('${c.order_id}'); document.getElementById('generic-details-modal').style.display='none';">
                    ⚡ Advance to "${nextInfo.nextLabel}"
                </button>
            ` : `
                <span style="color:#16a34a;font-size:0.85rem;font-weight:700;">✓ Fulfillment Pipeline Complete</span>
            `}
            <button class="btn btn-outline btn-sm" onclick="document.getElementById('generic-details-modal').style.display='none'">Close</button>
        </div>
    `;

    alertModal(`Order #${c.order_id} Breakdown`, html);
}

function renderServerOrderDetails(o, items) {
    const nextInfo = getNextPipelineStep(o.order_status);

    const html = `
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:1rem;margin-bottom:1.25rem;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.5rem;">
                <div>
                    <span style="font-size:0.75rem;color:#64748b;font-weight:700;text-transform:uppercase;">Order Details</span>
                    <h4 style="margin:0.2rem 0;color:#0f172a;font-size:1.15rem;">Order #${o.order_id}</h4>
                    <div style="font-size:0.8rem;color:#64748b;">Buyer: <strong>${o.buyer_name || 'Verified Buyer'}</strong> (${o.buyer_phone || 'N/A'})</div>
                    <div style="font-size:0.8rem;color:#64748b;">Assigned Hub: <strong>${o.hub_name || 'Regional Hub'}</strong></div>
                </div>
                <div style="text-align:right;">
                    <span class="status-badge ${getOrderBadgeClass(o.order_status)}">${o.order_status.replace(/_/g, ' ').toUpperCase()}</span>
                    <div style="margin-top:0.35rem;font-size:0.75rem;font-weight:700;color:#5b21b6;background:#ede9fe;padding:0.2rem 0.5rem;border-radius:99px;display:inline-block;">
                        🔒 ${(o.payment_status || 'PENDING').toUpperCase()}
                    </div>
                </div>
            </div>
            <div style="margin-top:0.75rem;padding-top:0.75rem;border-top:1px dashed #cbd5e1;font-size:0.8rem;color:#475569;display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
                <div>📍 <strong>Destination:</strong> ${o.delivery_address || 'Customer Delivery Address'}</div>
                <div>🏷️ <strong>Tracking:</strong> <code>${o.tracking_reference || 'AGRI-TRACK-DIRECT'}</code></div>
            </div>
        </div>

        <h4 style="font-size:0.95rem;margin:1rem 0 0.5rem;color:#1e293b;">Itemized Harvest Breakdown</h4>
        <table style="width:100%;border-collapse:collapse;margin-bottom:1.25rem;font-size:0.85rem;">
            <thead>
                <tr style="border-bottom:2px solid #e2e8f0;text-align:left;color:#64748b;font-size:0.75rem;">
                    <th style="padding:0.5rem 0.25rem;">Produce</th>
                    <th style="padding:0.5rem 0.25rem;">Farmer / Origin</th>
                    <th style="padding:0.5rem 0.25rem;text-align:center;">Qty</th>
                    <th style="padding:0.5rem 0.25rem;text-align:right;">Rate</th>
                    <th style="padding:0.5rem 0.25rem;text-align:right;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                ${items.map(i => `
                    <tr style="border-bottom:1px solid #f1f5f9;">
                        <td style="padding:0.6rem 0.25rem;">
                            <strong>${i.crop_name}</strong> (${i.variety_name || 'Standard'})
                        </td>
                        <td style="padding:0.6rem 0.25rem;">
                            <span style="font-size:0.8rem;color:#334155;">${i.farmer_name || i.farm_name || 'Local Farm Partner'}</span>
                        </td>
                        <td style="padding:0.6rem 0.25rem;text-align:center;font-weight:700;">${i.quantity_kg} kg</td>
                        <td style="padding:0.6rem 0.25rem;text-align:right;">₹${parseFloat(i.price_per_kg).toFixed(2)}</td>
                        <td style="padding:0.6rem 0.25rem;text-align:right;font-weight:700;color:#0f172a;">₹${parseFloat(i.subtotal).toFixed(2)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>

        <!-- Cost Breakdown Card -->
        <div style="background:#f8fafc;border-radius:8px;padding:0.85rem 1rem;font-size:0.85rem;margin-bottom:1.5rem;">
            <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;color:#475569;">
                <span>Produce Subtotal</span>
                <strong>₹${parseFloat(o.subtotal).toFixed(2)}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;color:#475569;">
                <span>Delivery & Hub Logistics</span>
                <span>₹${parseFloat(o.delivery_fee).toFixed(2)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;color:#475569;">
                <span>Platform Assurance & Quality Fee</span>
                <span>₹${parseFloat(o.platform_fee).toFixed(2)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding-top:0.5rem;border-top:1px solid #e2e8f0;font-size:1.05rem;font-weight:800;color:var(--primary-dark);">
                <span>Total Amount</span>
                <span>₹${Number(o.total_amount).toFixed(2)}</span>
            </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem;padding-top:0.5rem;border-top:1px solid #f1f5f9;">
            ${nextInfo ? `
                <button class="btn btn-primary btn-sm" onclick="advanceOrderStatus('${o.order_id}'); document.getElementById('generic-details-modal').style.display='none';">
                    ⚡ Advance to "${nextInfo.nextLabel}"
                </button>
            ` : `
                <span style="color:#16a34a;font-size:0.85rem;font-weight:700;">✓ Fulfillment Pipeline Complete</span>
            `}
            <button class="btn btn-outline btn-sm" onclick="document.getElementById('generic-details-modal').style.display='none'">Close</button>
        </div>
    `;

    alertModal(`Order #${o.order_id} Breakdown`, html);
}

function alertModal(title, htmlContent) {
    let modal = document.getElementById('generic-details-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'generic-details-modal';
        modal.className = 'modal-backdrop';
        modal.onclick = (e) => {
            if (e.target === modal) modal.style.display = 'none';
        };
        modal.innerHTML = `
            <div class="modal-content" style="max-width:580px; max-height:90vh; overflow-y:auto;">
                <div class="modal-header">
                    <h3 id="generic-modal-title" style="font-size:1.3rem;">Details</h3>
                    <button class="btn btn-outline btn-sm" onclick="document.getElementById('generic-details-modal').style.display='none'">✕</button>
                </div>
                <div id="generic-modal-body" style="font-size:0.9rem;line-height:1.5;"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById('generic-modal-title').innerText = title;
    document.getElementById('generic-modal-body').innerHTML = htmlContent;
    modal.style.display = 'flex';
}

document.addEventListener('DOMContentLoaded', () => {
    updateCartCount();
    if (document.getElementById('orders-list-container')) {
        loadOrders();
    }
});
