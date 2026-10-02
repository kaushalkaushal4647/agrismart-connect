/**
 * AgriSmart Connect - Super Admin Dashboard Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
    const user = getCurrentUser();
    if (!user) {
        window.location.href = '/login.html';
        return;
    }
    if (user.role !== 'admin') {
        showToast('Access restricted to Super Administrators.', 'error');
        setTimeout(() => window.location.href = '/index.html', 1500);
        return;
    }

    await loadAdminOverview();
    await loadAdminUsers();
    await loadAdminPayouts();
    await loadAdminDriverPayouts();
    await loadAdminReports();
});

// ==========================================
// 1. ADMIN OVERVIEW & KPIS
// ==========================================
async function loadAdminOverview() {
    try {
        const res = await apiFetch('/admin/dashboard');
        const o = res.overview;
        const surplus = res.surplus_alerts || [];

        // Set KPI cards
        document.getElementById('kpi-total-farmers').innerText = o.total_farmers || 0;
        document.getElementById('kpi-total-buyers').innerText = o.total_buyers || 0;
        document.getElementById('kpi-total-orders').innerText = o.total_orders || 0;
        document.getElementById('kpi-today-orders').innerText = o.today_orders || 0;
        document.getElementById('kpi-total-sales').innerText = `₹${Number(o.total_sales || 0).toLocaleString()}`;
        document.getElementById('kpi-platform-rev').innerText = `₹${Number(o.total_platform_revenue || 0).toLocaleString()}`;
        document.getElementById('kpi-pending-payouts').innerText = `₹${Number(o.pending_payouts || 0).toLocaleString()}`;
        document.getElementById('kpi-active-hubs').innerText = o.active_hubs || 0;

        // Render Surplus Alerts
        const surplusContainer = document.getElementById('surplus-alerts-tbody');
        if (surplusContainer) {
            if (!surplus.length) {
                surplusContainer.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:1.5rem;color:var(--slate-400);">No high surplus batches detected. Supply and demand balanced!</td></tr>';
            } else {
                surplusContainer.innerHTML = surplus.map(s => `
                    <tr>
                        <td><strong>${s.crop_name}</strong> (${s.variety_name || 'Standard'})</td>
                        <td><strong>${s.farm_name}</strong></td>
                        <td><strong style="color:var(--accent-amber);">${s.available_quantity_kg} kg</strong></td>
                        <td>₹${s.minimum_price_per_kg} / kg</td>
                        <td>
                            <span class="status-badge badge-matched">Surplus Alert</span>
                        </td>
                    </tr>
                `).join('');
            }
        }

    } catch (err) {
        showToast('Failed to load admin overview: ' + err.message, 'error');
    }
}

// ==========================================
// 2. USER MANAGEMENT
// ==========================================
async function loadAdminUsers() {
    const tbody = document.getElementById('admin-users-tbody');
    if (!tbody) return;

    try {
        const res = await apiFetch('/admin/users');
        const users = res.users || [];

        tbody.innerHTML = users.map(u => {
            const roleClass = {
                'farmer': 'role-tag-farmer',
                'consumer': 'role-tag-consumer',
                'restaurant': 'role-tag-business',
                'retailer': 'role-tag-business',
                'hub_operator': 'role-tag-hub',
                'delivery_partner': 'role-tag-delivery',
                'admin': 'role-tag-admin'
            }[u.role] || 'role-tag-consumer';

            return `
                <tr>
                    <td><strong>${u.name}</strong></td>
                    <td>${u.email}<div style="font-size:0.75rem;color:var(--slate-500);">${u.phone}</div></td>
                    <td><span class="role-tag ${roleClass}">${u.role.toUpperCase()}</span></td>
                    <td>${u.farm_name || u.business_name || '--'}</td>
                    <td>
                        <span class="status-badge ${u.is_active ? 'badge-available' : 'badge-danger'}">
                            ${u.is_active ? 'ACTIVE' : 'SUSPENDED'}
                        </span>
                    </td>
                    <td>
                        <button class="btn btn-outline btn-sm" onclick="toggleUser(${u.user_id})">
                            ${u.is_active ? 'Suspend' : 'Activate'}
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" style="color:var(--status-danger);padding:1.5rem;text-align:center;">Failed to load users: ${err.message}</td></tr>`;
    }
}

async function toggleUser(userId) {
    try {
        const res = await apiFetch(`/admin/users/${userId}/toggle-status`, { method: 'PUT' });
        showToast(res.message, 'info');
        loadAdminUsers();
    } catch (err) {
        showToast(err.message || 'Status toggle failed.', 'error');
    }
}

// ==========================================
// 3. FARMER PAYOUTS SETTLEMENT CONSOLE
// ==========================================
async function loadAdminPayouts() {
    const tbody = document.getElementById('admin-payouts-tbody');
    if (!tbody) return;

    try {
        const res = await apiFetch('/payments/payouts');
        const payouts = res.payouts || [];

        if (!payouts.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--slate-400);">No payout records found.</td></tr>';
            return;
        }

        tbody.innerHTML = payouts.map(p => {
            const isSettled = p.payout_status === 'paid';
            return `
                <tr>
                    <td><strong>#PAY-${p.payout_id}</strong></td>
                    <td>Order #${p.order_id}</td>
                    <td>${p.farm_name} (${p.farmer_name})</td>
                    <td>₹${p.gross_amount}</td>
                    <td>-₹${p.platform_fee}</td>
                    <td><strong style="color:var(--primary-dark);">₹${p.net_amount}</strong></td>
                    <td>
                        <span class="status-badge ${isSettled ? 'badge-available' : 'badge-matched'}">
                            ${p.payout_status.toUpperCase()}
                        </span>
                    </td>
                    <td>
                        ${!isSettled ? `
                            <button class="btn btn-primary btn-sm" onclick="settleFarmerPayout(${p.payout_id})">Disburse ₹${p.net_amount}</button>
                        ` : '<span style="color:var(--status-success);font-weight:700;">✓ Disbursed</span>'}
                    </td>
                </tr>
            `;
        }).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" style="color:var(--status-danger);padding:1.5rem;text-align:center;">Failed to load payouts: ${err.message}</td></tr>`;
    }
}

async function settleFarmerPayout(payoutId) {
    try {
        await apiFetch(`/payments/payouts/${payoutId}/settle`, { method: 'PUT' });
        showToast(`Payout #${payoutId} settled and recorded!`, 'success');
        loadAdminPayouts();
        loadAdminOverview();
    } catch (err) {
        showToast(err.message || 'Settlement failed.', 'error');
    }
}

// 3B. DELIVERY PARTNER PAYOUTS CONSOLE
async function loadAdminDriverPayouts() {
    const tbody = document.getElementById('admin-driver-payouts-tbody');
    if (!tbody) return;

    try {
        const res = await apiFetch('/payments/delivery-payouts');
        const payouts = res.payouts || [];

        if (!payouts.length) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--slate-400);">No driver payout records found.</td></tr>';
            return;
        }

        tbody.innerHTML = payouts.map(p => {
            const isSettled = p.payout_status === 'paid';
            return `
                <tr>
                    <td><strong>#PAY-DRV-${p.payout_id}</strong></td>
                    <td>Order #${p.order_id}</td>
                    <td>
                        <strong>${p.partner_name || 'Delivery Partner'}</strong>
                        <div style="font-size:0.75rem;color:var(--slate-500);">${p.partner_phone || ''}</div>
                    </td>
                    <td>
                        <div style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${p.delivery_address || ''}">
                            ${p.delivery_address || 'Customer Location'}
                        </div>
                    </td>
                    <td>${p.cargo_weight_kg || 0} kg</td>
                    <td><strong style="color:#15803d;">₹${Number(p.total_payout).toFixed(2)}</strong></td>
                    <td>
                        <span class="status-badge ${isSettled ? 'badge-available' : 'badge-matched'}">
                            ${p.payout_status.toUpperCase()}
                        </span>
                    </td>
                    <td>
                        ${!isSettled ? `
                            <button class="btn btn-primary btn-sm" onclick="settleDriverPayout(${p.payout_id})">Disburse ₹${p.total_payout}</button>
                        ` : '<span style="color:var(--status-success);font-weight:700;">✓ Disbursed</span>'}
                    </td>
                </tr>
            `;
        }).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" style="color:var(--status-danger);padding:1.5rem;text-align:center;">Failed to load driver payouts: ${err.message}</td></tr>`;
    }
}

async function settleDriverPayout(payoutId) {
    try {
        await apiFetch(`/payments/delivery-payouts/${payoutId}/settle`, { method: 'PUT' });
        showToast(`Driver Payout #${payoutId} disbursed successfully!`, 'success');
        loadAdminDriverPayouts();
        loadAdminOverview();
    } catch (err) {
        showToast(err.message || 'Settlement failed.', 'error');
    }
}

// ==========================================
// 4. REPORTS & ANALYTICS
// ==========================================
async function loadAdminReports() {
    try {
        const res = await apiFetch('/admin/reports');
        const crops = res.crop_sales || [];
        const hubs = res.hub_performance || [];

        // Crop sales table
        const cropTbody = document.getElementById('report-crops-tbody');
        if (cropTbody) {
            cropTbody.innerHTML = crops.map(c => `
                <tr>
                    <td><strong>${c.crop_name}</strong></td>
                    <td>${c.category}</td>
                    <td>${c.total_orders}</td>
                    <td><strong>${Number(c.total_kg_sold).toLocaleString()} kg</strong></td>
                    <td><strong>₹${Number(c.total_revenue).toFixed(2)}</strong></td>
                </tr>
            `).join('');
        }

        // Hub performance table
        const hubTbody = document.getElementById('report-hubs-tbody');
        if (hubTbody) {
            hubTbody.innerHTML = hubs.map(h => `
                <tr>
                    <td><strong>${h.hub_name}</strong></td>
                    <td>${h.district}</td>
                    <td>${h.capacity_kg} kg</td>
                    <td><strong>${h.total_orders_routed} orders</strong></td>
                    <td><strong>₹${Number(h.total_routed_amount).toFixed(2)}</strong></td>
                </tr>
            `).join('');
        }

    } catch (err) {
        console.error('Failed to load reports:', err);
    }
}
// ==========================================
// 5. TAB SWITCHER
// ==========================================
function switchAdminTab(tabName) {
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

    const targetPanel = document.getElementById(`tab-${tabName}`);
    if (targetPanel) targetPanel.classList.add('active');

    // Match the clicked tab button by its onclick attribute containing the tab name
    document.querySelectorAll('.admin-tab').forEach(t => {
        if (t.getAttribute('onclick') && t.getAttribute('onclick').includes(`'${tabName}'`)) {
            t.classList.add('active');
        }
    });

    // Lazy-load tab data on first open
    if (tabName === 'payouts') {
        loadAdminPayouts();
        loadAdminDriverPayouts();
    }
    if (tabName === 'moderation') loadModerationQueue();
    if (tabName === 'logistics') loadAdminLogisticsData();
    if (tabName === 'demo-images') loadAdminDemoImages();
}

// ==========================================
// 6. PRODUCT MODERATION QUEUE
// ==========================================
async function loadModerationQueue() {
    const tbody = document.getElementById('moderation-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--slate-400);">Loading moderation queue...</td></tr>';

    try {
        const res = await apiFetch('/admin/products');
        const products = res.products || [];

        if (!products.length) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--slate-400);">No products pending review. All listings moderated! ✓</td></tr>';
            return;
        }

        tbody.innerHTML = products.map(p => {
            const statusUpper = (p.status || 'ACTIVE').toUpperCase();
            let statusBadge = 'badge-open';
            if (statusUpper === 'ACTIVE' || statusUpper === 'AVAILABLE') statusBadge = 'badge-available';
            else if (statusUpper === 'PAUSED') statusBadge = 'badge-matched';
            else if (statusUpper === 'DRAFT') statusBadge = 'badge-open';
            else if (statusUpper === 'CANCELLED') statusBadge = 'badge-danger';

            const modStatus = (p.moderation_status || 'APPROVED').toUpperCase();
            let modBadge = 'badge-open';
            if (modStatus === 'APPROVED') modBadge = 'badge-available';
            else if (modStatus === 'PENDING') modBadge = 'badge-matched';
            else if (modStatus === 'REJECTED') modBadge = 'badge-danger';

            const hDate = p.harvest_date ? new Date(p.harvest_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'N/A';

            return `
                <tr>
                    <td>
                        <strong>${p.product_name || p.crop_name}</strong>
                        <div style="font-size:0.75rem;color:var(--slate-500);">${p.crop_name} &bull; ${p.quality_grade || 'Standard'} &bull; ${p.organic_status === 'organic' ? '<span style="color:#15803d;font-weight:700;">Organic</span>' : 'Conventional'}</div>
                    </td>
                    <td>
                        <div>${p.farmer_name || 'Farmer'}</div>
                        <div style="font-size:0.75rem;color:var(--slate-500);">${p.farm_district || 'Tamil Nadu'} <span style="background:#f1f5f9;padding:0.1rem 0.3rem;border-radius:4px;font-size:0.7rem;">DEMO</span></div>
                    </td>
                    <td>
                        <div><strong>${Number(p.available_quantity_kg || 0).toLocaleString()} kg</strong></div>
                        <div style="font-size:0.75rem;color:var(--slate-500);">&#8377;${Number(p.minimum_price_per_kg || 0).toFixed(2)}/kg</div>
                    </td>
                    <td style="font-size:0.85rem;">${hDate}</td>
                    <td><span class="status-badge ${statusBadge}">${statusUpper}</span></td>
                    <td><span class="status-badge ${modBadge}">${modStatus}</span></td>
                    <td>
                        <div style="display:flex;gap:0.35rem;flex-wrap:wrap;">
                            ${statusUpper !== 'ACTIVE' && statusUpper !== 'AVAILABLE' ? `
                                <button class="btn btn-outline btn-sm" style="color:var(--primary);font-size:0.75rem;" onclick="moderateProduct(${p.produce_id}, 'ACTIVE')">
                                    ✓ Approve
                                </button>
                            ` : ''}
                            ${statusUpper !== 'PAUSED' ? `
                                <button class="btn btn-outline btn-sm" style="color:var(--accent-amber);font-size:0.75rem;" onclick="moderateProduct(${p.produce_id}, 'PAUSED')">
                                    ⏸ Pause
                                </button>
                            ` : ''}
                            ${statusUpper !== 'CANCELLED' ? `
                                <button class="btn btn-outline btn-sm" style="color:var(--status-danger);font-size:0.75rem;" onclick="moderateProduct(${p.produce_id}, 'CANCELLED')">
                                    ✕ Reject
                                </button>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" style="color:var(--status-danger);padding:1.5rem;text-align:center;">Failed to load moderation queue: ${err.message}</td></tr>`;
    }
}

async function moderateProduct(produceId, newStatus) {
    const actionLabel = newStatus === 'ACTIVE' ? 'approve' : newStatus === 'PAUSED' ? 'pause' : 'reject';
    if (!confirm(`Are you sure you want to ${actionLabel} this product listing?`)) return;

    try {
        await apiFetch(`/farmers/products/${produceId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status: newStatus })
        });
        showToast(`Product ${actionLabel}d successfully.`, 'success');
        await loadModerationQueue();
    } catch (err) {
        showToast(err.message || `Failed to ${actionLabel} product.`, 'error');
    }
}

// ==========================================
// 7. AI LOGISTICS TAB
// ==========================================
async function loadAdminLogisticsData() {
    await Promise.all([
        loadAdminDemandForecasts(),
        loadAdminInventoryAlerts(),
        loadAdminFarmerRecommendations()
    ]);
}

async function loadAdminDemandForecasts() {
    const container = document.getElementById('admin-demand-list');
    if (!container) return;

    try {
        const res = await apiFetch('/logistics/demand?limit=8');
        const predictions = res.predictions || [];

        if (!predictions.length) {
            container.innerHTML = '<div style="color:var(--slate-400);font-size:0.85rem;padding:0.5rem;">No demand forecast data available.</div>';
            return;
        }

        container.innerHTML = predictions.map(p => {
            const demandLevel = p.predicted_demand_kg > 500 ? 'HIGH' : p.predicted_demand_kg > 200 ? 'MEDIUM' : 'LOW';
            const levelColor = demandLevel === 'HIGH' ? '#15803d' : demandLevel === 'MEDIUM' ? '#d97706' : '#64748b';
            const levelBg = demandLevel === 'HIGH' ? '#dcfce7' : demandLevel === 'MEDIUM' ? '#fef3c7' : '#f1f5f9';

            return `
                <div style="background:var(--white);border:1px solid var(--slate-200);border-radius:var(--radius-md);padding:0.65rem 1rem;display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <div style="font-weight:700;font-size:0.9rem;">${p.crop_name || 'Crop'}</div>
                        <div style="font-size:0.75rem;color:var(--slate-500);">${p.district || 'Tamil Nadu'} &bull; ${p.forecast_period || 'Next 7 days'}</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-weight:800;color:var(--primary-dark);">${Number(p.predicted_demand_kg || 0).toLocaleString()} kg</div>
                        <span style="font-size:0.7rem;font-weight:700;padding:0.1rem 0.4rem;border-radius:4px;background:${levelBg};color:${levelColor};">${demandLevel} ${p.is_simulated ? '· SIMULATED' : ''}</span>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        container.innerHTML = `<div style="color:var(--status-danger);font-size:0.8rem;">Error: ${err.message}</div>`;
    }
}

async function loadAdminInventoryAlerts() {
    const container = document.getElementById('admin-inventory-alerts');
    if (!container) return;

    try {
        const res = await apiFetch('/logistics/inventory-alerts');
        const alerts = res.alerts || [];

        if (!alerts.length) {
            container.innerHTML = '<div style="color:var(--slate-400);font-size:0.85rem;padding:0.5rem;">No inventory alerts. All hubs operating within normal thresholds.</div>';
            return;
        }

        container.innerHTML = alerts.map(a => {
            const urgencyColor = a.urgency === 'HIGH' ? '#dc2626' : a.urgency === 'MEDIUM' ? '#d97706' : '#64748b';
            const urgencyBg = a.urgency === 'HIGH' ? '#fef2f2' : a.urgency === 'MEDIUM' ? '#fef3c7' : '#f8fafc';

            return `
                <div style="background:${urgencyBg};border:1px solid ${urgencyColor}33;border-left:3px solid ${urgencyColor};border-radius:var(--radius-md);padding:0.65rem 1rem;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                        <div>
                            <div style="font-weight:700;font-size:0.88rem;color:var(--slate-900);">${a.hub_name || 'Hub'} &mdash; ${a.crop_name || 'Produce'}</div>
                            <div style="font-size:0.75rem;color:var(--slate-600);">${a.alert_message || a.recommendation || 'Review required'}</div>
                        </div>
                        <span style="font-size:0.7rem;font-weight:800;color:${urgencyColor};white-space:nowrap;margin-left:0.5rem;">${a.urgency || 'INFO'}</span>
                    </div>
                    ${a.days_to_expiry !== undefined ? `<div style="font-size:0.72rem;color:var(--slate-500);margin-top:0.25rem;">Expires in: <strong>${a.days_to_expiry} days</strong></div>` : ''}
                </div>
            `;
        }).join('');

    } catch (err) {
        container.innerHTML = `<div style="color:var(--status-danger);font-size:0.8rem;">Error: ${err.message}</div>`;
    }
}

async function loadAdminFarmerRecommendations() {
    const container = document.getElementById('admin-farmer-recs');
    if (!container) return;

    try {
        const res = await apiFetch('/logistics/recommendations?limit=8');
        const recs = res.recommendations || [];

        if (!recs.length) {
            container.innerHTML = '<div style="color:var(--slate-400);font-size:0.85rem;padding:0.5rem;">No farmer-hub matches available yet.</div>';
            return;
        }

        container.innerHTML = recs.map(r => `
            <div style="background:var(--white);border:1px solid var(--slate-200);border-radius:var(--radius-md);padding:0.65rem 1rem;display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <div style="font-weight:700;font-size:0.88rem;">${r.farmer_name || 'Farmer'}</div>
                    <div style="font-size:0.75rem;color:var(--slate-500);">${r.crop_name || ''} &bull; ${r.farm_district || 'Tamil Nadu'}</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.85rem;font-weight:700;color:var(--primary-dark);">${r.hub_name || 'Hub'}</div>
                    <div style="font-size:0.72rem;color:var(--slate-500);">${r.distance_km ? r.distance_km + ' km' : ''} ${r.match_score ? '· Score: ' + r.match_score : ''}</div>
                </div>
            </div>
        `).join('');

    } catch (err) {
        container.innerHTML = `<div style="color:var(--status-danger);font-size:0.8rem;">Error: ${err.message}</div>`;
    }
}

async function adminRunRouteOptimizer() {
    const resultDiv = document.getElementById('admin-route-result');
    if (!resultDiv) return;

    resultDiv.innerHTML = '<em style="color:var(--slate-500);">&#9889; Running OR-Tools CVRP solver... please wait.</em>';

    try {
        const res = await apiFetch('/logistics/optimize-route', {
            method: 'POST',
            body: JSON.stringify({ hub_id: null, num_vehicles: 3, vehicle_capacity_kg: 500 })
        });

        if (res.status === 'success' && res.routes) {
            const r = res;
            resultDiv.innerHTML = `
                <div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:0.75rem;">
                    <div style="background:#dcfce7;padding:0.5rem 1rem;border-radius:8px;font-size:0.85rem;font-weight:700;color:#15803d;">
                        &#10003; Optimized: ${r.total_distance_km || 0} km total
                    </div>
                    <div style="background:#f0f9ff;padding:0.5rem 1rem;border-radius:8px;font-size:0.85rem;font-weight:700;color:#0369a1;">
                        ${r.routes.length} routes &bull; ${r.total_stops || 0} stops
                    </div>
                    <span style="background:#fef9c3;color:#92400e;padding:0.3rem 0.6rem;border-radius:4px;font-size:0.72rem;font-weight:700;align-self:center;">SIMULATED</span>
                </div>
                ${r.routes.map((route, idx) => `
                    <div style="margin-bottom:0.5rem;padding:0.5rem 0.75rem;background:var(--white);border-radius:6px;border:1px solid var(--slate-200);font-size:0.82rem;">
                        <strong>Vehicle ${idx + 1}:</strong> ${route.stops ? route.stops.join(' &#8594; ') : 'No stops'} &bull; ${route.distance_km || 0} km &bull; Load: ${route.load_kg || 0} kg
                    </div>
                `).join('')}
            `;
        } else {
            resultDiv.innerHTML = `<span style="color:var(--slate-500);">Optimizer returned no feasible routes. Try adjusting vehicle capacity or number of vehicles.</span>`;
        }
    } catch (err) {
        resultDiv.innerHTML = `<span style="color:var(--status-danger);">Route optimization failed: ${err.message}</span>`;
    }
}

// ==========================================
// 8. DEMO PRODUCT IMAGE MANAGEMENT
// ==========================================
let _allDemoImages = [];  // cache for client-side filtering

async function loadAdminDemoImages() {
    const grid = document.getElementById('demo-images-grid');
    if (!grid) return;
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--slate-400);">Loading demo images...</div>';

    try {
        const res = await apiFetch('/admin/demo-images');
        const images = res.images || [];
        _allDemoImages = images;

        // Compute stats
        const uniqueProducts = new Set(images.map(i => i.produce_id)).size;
        const wikimediaCount = images.filter(i => (i.source || '').toLowerCase().includes('wikimedia')).length;
        document.getElementById('dimg-stat-products').textContent = uniqueProducts;
        document.getElementById('dimg-stat-images').textContent = images.length;
        document.getElementById('dimg-stat-wikimedia').textContent = wikimediaCount;

        // Populate crop filter
        const cropSelect = document.getElementById('demo-img-filter-crop');
        if (cropSelect) {
            const crops = [...new Set(images.map(i => i.crop_name).filter(Boolean))].sort();
            cropSelect.innerHTML = '<option value="">All Crops</option>' +
                crops.map(c => `<option value="${c}">${c}</option>`).join('');
        }

        renderDemoImageGrid(images);
    } catch (err) {
        grid.innerHTML = `<div style="grid-column:1/-1;color:var(--status-danger);text-align:center;padding:2rem;">Failed to load demo images: ${err.message}</div>`;
    }
}

function filterDemoImages() {
    const query = (document.getElementById('demo-img-search')?.value || '').toLowerCase();
    const cropFilter = document.getElementById('demo-img-filter-crop')?.value || '';
    const filtered = _allDemoImages.filter(img => {
        const matchCrop = !cropFilter || img.crop_name === cropFilter;
        const matchSearch = !query || (img.crop_name || '').toLowerCase().includes(query)
                            || (img.product_name || '').toLowerCase().includes(query)
                            || (img.attribution || '').toLowerCase().includes(query);
        return matchCrop && matchSearch;
    });
    renderDemoImageGrid(filtered);
}

function renderDemoImageGrid(images) {
    const grid = document.getElementById('demo-images-grid');
    if (!grid) return;

    if (!images.length) {
        grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--slate-400);">No images match your filter.</div>';
        return;
    }

    grid.innerHTML = images.map(img => {
        const isPrimary = img.is_primary;
        const licenseTag = img.license ? `<span style="font-size:0.65rem;background:var(--slate-100);color:var(--slate-600);padding:0.1rem 0.35rem;border-radius:3px;display:block;margin-top:0.2rem;">${img.license}</span>` : '';
        const attribution = img.attribution || img.source || 'Unknown';
        const primaryBadge = isPrimary
            ? '<span style="position:absolute;top:6px;right:6px;background:#16a34a;color:#fff;font-size:0.65rem;font-weight:800;padding:0.15rem 0.4rem;border-radius:4px;">PRIMARY</span>'
            : '';
        return `
            <div style="background:var(--white);border:${isPrimary ? '2px solid var(--primary)' : '1px solid var(--slate-200)'};border-radius:var(--radius-md);overflow:hidden;box-shadow:var(--shadow-sm);position:relative;">
                <div style="height:140px;overflow:hidden;background:var(--slate-100);">
                    <img src="${img.image_url}" alt="${img.crop_name}" loading="lazy"
                         style="width:100%;height:100%;object-fit:cover;"
                         onerror="this.parentElement.innerHTML='<div style=\'width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:2rem;\'>🌾</div>'">
                    ${primaryBadge}
                </div>
                <div style="padding:0.6rem 0.7rem;">
                    <div style="font-weight:700;font-size:0.85rem;color:var(--slate-800);">${img.crop_name || 'Unknown'}</div>
                    <div style="font-size:0.72rem;color:var(--slate-500);margin-bottom:0.2rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${attribution}">${attribution}</div>
                    ${licenseTag}
                    <div style="display:flex;gap:0.4rem;margin-top:0.6rem;">
                        ${!isPrimary ? `<button class="btn btn-outline btn-sm" style="flex:1;font-size:0.72rem;padding:0.25rem;" onclick="adminSetPrimaryDemoImage(${img.image_id}, ${img.produce_id})">★ Set Primary</button>` : '<span style="flex:1;"></span>'}
                        <button class="btn btn-sm" style="flex:1;font-size:0.72rem;padding:0.25rem;background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;border-radius:var(--radius-sm);" onclick="adminDeleteDemoImage(${img.image_id})">🗑 Delete</button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

async function adminSetPrimaryDemoImage(imageId, produceId) {
    try {
        await apiFetch(`/admin/demo-images/${imageId}/set-primary`, {
            method: 'POST',
            body: JSON.stringify({ produce_id: produceId })
        });
        showToast('Primary image updated.', 'success');
        await loadAdminDemoImages();
    } catch (err) {
        showToast('Failed to set primary: ' + err.message, 'error');
    }
}

async function adminDeleteDemoImage(imageId) {
    if (!confirm('Delete this demo image? This cannot be undone.')) return;
    try {
        await apiFetch(`/admin/demo-images/${imageId}`, { method: 'DELETE' });
        showToast('Image deleted.', 'success');
        // Remove from cache and re-render
        _allDemoImages = _allDemoImages.filter(i => i.image_id !== imageId);
        document.getElementById('dimg-stat-images').textContent = _allDemoImages.length;
        filterDemoImages();
    } catch (err) {
        showToast('Failed to delete: ' + err.message, 'error');
    }
}
