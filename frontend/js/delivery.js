/**
 * AgriSmart Connect - Delivery Partner Dashboard Logic
 * Phase 1 & Phase 2: Shift KPIs, Filter Tabs, Navigation, Cargo Manifest & e-POD
 */

let allDeliveries = [];
let currentFilter = 'all';
let activeEpodDeliveryId = null;

// Signature canvas state
let isDrawing = false;
let sigCanvas = null;
let sigCtx = null;
let currentPhotoBase64 = null;

document.addEventListener('DOMContentLoaded', async () => {
    const user = getCurrentUser();
    if (!user) {
        window.location.href = '/login.html';
        return;
    }
    if (user.role !== 'delivery_partner' && user.role !== 'admin') {
        showToast('Access restricted to Delivery Partners.', 'error');
        setTimeout(() => window.location.href = '/index.html', 1500);
        return;
    }

    initSignatureCanvas();
    await loadDeliveries();
});

async function loadDeliveries() {
    const container = document.getElementById('deliveries-container');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--slate-400);">Loading dispatch schedule...</div>';

    try {
        const res = await apiFetch('/deliveries');
        allDeliveries = res.deliveries || [];

        updateKpiMetrics(allDeliveries);
        updateTabCounters(allDeliveries);
        renderFilteredDeliveries();

    } catch (err) {
        container.innerHTML = `<div style="color:var(--status-danger);text-align:center;padding:2rem;">Failed to load deliveries: ${err.message}</div>`;
    }
}

// ==========================================
// 1. KPI SHIFT METRICS & COUNTERS
// ==========================================
function updateKpiMetrics(deliveries) {
    const user = getCurrentUser();
    if (!user) return;

    let activeRuns = 0;
    let completedRuns = 0;
    let cargoWeight = 0;

    deliveries.forEach(d => {
        const isMyJob = d.delivery_partner_id === user.user_id;
        const weight = parseFloat(d.total_weight_kg || 0);

        if (isMyJob) {
            if (['assigned', 'picked_up', 'in_transit'].includes(d.status)) {
                activeRuns++;
                cargoWeight += weight;
            } else if (d.status === 'delivered') {
                completedRuns++;
                cargoWeight += weight;
            }
        }
    });

    // Earnings model: ₹250 per completed run + ₹1.5 per kg hauled
    const earnings = (completedRuns * 250) + Math.round(cargoWeight * 1.5);

    const activeEl = document.getElementById('kpi-active-runs');
    const compEl = document.getElementById('kpi-completed-runs');
    const cargoEl = document.getElementById('kpi-cargo-weight');
    const earnEl = document.getElementById('kpi-shift-earnings');

    if (activeEl) activeEl.textContent = activeRuns;
    if (compEl) compEl.textContent = completedRuns;
    if (cargoEl) cargoEl.textContent = `${cargoWeight.toLocaleString()} kg`;
    if (earnEl) earnEl.textContent = `₹${earnings.toLocaleString()}`;
}

function updateTabCounters(deliveries) {
    const user = getCurrentUser();
    const userId = user ? user.user_id : null;

    let countAll = deliveries.length;
    let countActive = 0;
    let countAvailable = 0;
    let countDelivered = 0;

    deliveries.forEach(d => {
        if (!d.delivery_partner_id) {
            countAvailable++;
        }
        if (d.delivery_partner_id === userId && ['assigned', 'picked_up', 'in_transit'].includes(d.status)) {
            countActive++;
        }
        if (d.status === 'delivered') {
            countDelivered++;
        }
    });

    const elAll = document.getElementById('count-all');
    const elActive = document.getElementById('count-active');
    const elAvail = document.getElementById('count-available');
    const elDel = document.getElementById('count-delivered');

    if (elAll) elAll.textContent = countAll;
    if (elActive) elActive.textContent = countActive;
    if (elAvail) elAvail.textContent = countAvailable;
    if (elDel) elDel.textContent = countDelivered;
}

// ==========================================
// 2. FILTER TABS LOGIC
// ==========================================
function filterDeliveries(filterType) {
    currentFilter = filterType;

    document.querySelectorAll('.filter-tab-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(`tab-${filterType}`);
    if (activeBtn) activeBtn.classList.add('active');

    renderFilteredDeliveries();
}

function renderFilteredDeliveries() {
    const container = document.getElementById('deliveries-container');
    if (!container) return;

    const user = getCurrentUser();
    const userId = user ? user.user_id : null;

    let filtered = allDeliveries;

    if (currentFilter === 'active') {
        filtered = allDeliveries.filter(d => 
            d.delivery_partner_id === userId && ['assigned', 'picked_up', 'in_transit'].includes(d.status)
        );
    } else if (currentFilter === 'available') {
        filtered = allDeliveries.filter(d => !d.delivery_partner_id);
    } else if (currentFilter === 'delivered') {
        filtered = allDeliveries.filter(d => d.status === 'delivered');
    }

    if (!filtered.length) {
        let emptyTitle = 'No Deliveries Found';
        let emptyDesc = 'There are currently no delivery consignments matching this filter.';

        if (currentFilter === 'active') {
            emptyTitle = 'No Active Trips Right Now';
            emptyDesc = 'You do not have any active pickups or in-transit deliveries. Claim an available batch to start your run.';
        } else if (currentFilter === 'available') {
            emptyTitle = 'All Hub Orders Claimed';
            emptyDesc = 'All packed collection hub orders are currently assigned to drivers.';
        } else if (currentFilter === 'delivered') {
            emptyTitle = 'No Completed Deliveries Yet';
            emptyDesc = 'Your successfully fulfilled orders will be archived here.';
        }

        container.innerHTML = `
            <div style="text-align:center;padding:4rem 1rem;background:var(--white);border-radius:var(--radius-lg);border:1px solid var(--slate-200);">
                <div style="font-size:2.5rem;margin-bottom:1rem;">🚚</div>
                <h3 style="font-size:1.35rem;margin-bottom:0.5rem;color:var(--slate-800);">${emptyTitle}</h3>
                <p style="color:var(--slate-500);font-size:0.95rem;max-width:420px;margin:0 auto 1.5rem;">
                    ${emptyDesc}
                </p>
                ${currentFilter !== 'all' ? '<button class="btn btn-outline btn-sm" onclick="filterDeliveries(\'all\')">View All Deliveries</button>' : ''}
            </div>
        `;
        return;
    }

    container.innerHTML = filtered.map(d => renderDeliveryCard(d)).join('');
}

// ==========================================
// 3. DELIVERY CARD RENDERING
// ==========================================
function renderDeliveryCard(d) {
    const user = getCurrentUser();
    const isMyJob = d.delivery_partner_id === user.user_id;

    // Action button based on state
    let actionBtn = '';
    if (!d.delivery_partner_id) {
        actionBtn = `<button class="btn btn-primary btn-sm" onclick="claimRun(${d.delivery_id})">⚡ Claim Delivery Run</button>`;
    } else if (isMyJob || user.role === 'admin') {
        if (d.status === 'assigned') {
            actionBtn = `<button class="btn btn-primary btn-sm" onclick="updateRunStatus(${d.delivery_id}, 'picked_up')">📦 Confirm Hub Pickup</button>`;
        } else if (d.status === 'picked_up') {
            actionBtn = `<button class="btn btn-outline btn-sm" style="border-color:#0284c7;color:#0284c7;" onclick="updateRunStatus(${d.delivery_id}, 'in_transit')">🚀 Start In-Transit</button>`;
        } else if (d.status === 'in_transit') {
            actionBtn = `<button class="btn btn-primary btn-sm" style="background:#16a34a;border-color:#16a34a;" onclick="openEpodModal(${d.delivery_id})">✓ Confirm Delivered & e-POD</button>`;
        } else if (d.status === 'delivered') {
            actionBtn = `
                <div style="display:flex;gap:0.5rem;align-items:center;">
                    <span class="status-badge badge-paid">Delivered & Closed</span>
                    <button class="btn btn-outline btn-sm" style="border-color:#16a34a;color:#15803d;font-weight:700;font-size:0.75rem;" onclick="viewEpodReceipt(${d.delivery_id})">
                        📜 View e-POD
                    </button>
                </div>
            `;
        }
    }

    // Google Maps Navigation Links
    const hubDestination = `${d.hub_name}, ${d.hub_address || ''}, ${d.hub_district || ''}`;
    const hubMapUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(hubDestination)}`;

    const buyerDestination = `${d.delivery_address || ''}`;
    const buyerMapUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(buyerDestination)}`;

    // Weight & item details
    const weightKg = parseFloat(d.total_weight_kg || 0);
    const weightBadge = weightKg > 0 ? `<span class="badge badge-info" style="font-size:0.75rem;">⚖️ ${weightKg} kg Cargo</span>` : '';
    const itemsCount = (d.items && d.items.length) ? d.items.length : (d.items_count || 1);
    const itemsBadge = `<span class="badge" style="background:#f1f5f9;color:#475569;font-size:0.75rem;">📦 ${itemsCount} Produce ${itemsCount > 1 ? 'Batches' : 'Batch'}</span>`;

    // Driver label
    const driverLabel = d.driver_name 
        ? `<span style="font-size:0.8rem;color:var(--slate-500);">Driver: <strong style="color:var(--slate-700);">${isMyJob ? 'You' : d.driver_name}</strong></span>`
        : `<span class="badge badge-warning" style="font-size:0.72rem;">Unassigned / Open</span>`;

    // Visual Step Indicator
    const steps = ['assigned', 'picked_up', 'in_transit', 'delivered'];
    const currentStepIndex = steps.indexOf(d.status);

    const stepBar = `
        <div style="display:flex;align-items:center;justify-content:space-between;background:#f8fafc;padding:0.65rem 1rem;border-radius:var(--radius-md);margin-bottom:1.25rem;border:1px solid #e2e8f0;font-size:0.78rem;">
            <div style="font-weight:${currentStepIndex >= 0 ? '700' : '500'};color:${currentStepIndex >= 0 ? '#16a34a' : '#94a3b8'};">
                ${currentStepIndex >= 0 ? '●' : '○'} 1. Assigned
            </div>
            <span style="color:#cbd5e1;">➔</span>
            <div style="font-weight:${currentStepIndex >= 1 ? '700' : '500'};color:${currentStepIndex >= 1 ? '#16a34a' : '#94a3b8'};">
                ${currentStepIndex >= 1 ? '●' : '○'} 2. Hub Pickup
            </div>
            <span style="color:#cbd5e1;">➔</span>
            <div style="font-weight:${currentStepIndex >= 2 ? '700' : '500'};color:${currentStepIndex >= 2 ? '#0284c7' : '#94a3b8'};">
                ${currentStepIndex >= 2 ? '●' : '○'} 3. In Transit
            </div>
            <span style="color:#cbd5e1;">➔</span>
            <div style="font-weight:${currentStepIndex >= 3 ? '700' : '500'};color:${currentStepIndex >= 3 ? '#16a34a' : '#94a3b8'};">
                ${currentStepIndex >= 3 ? '✓' : '○'} 4. Delivered
            </div>
        </div>
    `;

    // Itemized Cargo Manifest Rows
    const itemsList = d.items || [];
    const manifestRows = itemsList.map(item => `
        <tr>
            <td>
                <strong>${item.crop_name || 'Produce'}</strong>
                <div style="font-size:0.75rem;color:var(--slate-500);">${item.variety_name || 'Standard Variety'}</div>
            </td>
            <td>
                <span class="badge" style="background:#e0f2fe;color:#0369a1;font-size:0.72rem;">${item.quality_grade || 'Grade A'}</span>
            </td>
            <td>
                <span style="color:var(--slate-700);">${item.farm_name || item.farmer_name || 'Regional Farm'}</span>
            </td>
            <td style="font-weight:700;color:var(--slate-900);">
                ${item.quantity_kg || 0} kg
            </td>
            <td style="text-align:right;font-weight:700;color:var(--primary-dark);">
                ₹${Number(item.subtotal || 0).toLocaleString()}
            </td>
        </tr>
    `).join('');

    const manifestSection = `
        <div style="margin-top:1rem;border-top:1px dashed #e2e8f0;padding-top:0.75rem;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <button class="btn btn-outline btn-sm" style="font-size:0.78rem;padding:0.25rem 0.6rem;" onclick="toggleManifest(${d.delivery_id})">
                    📋 View Cargo Manifest (${itemsCount} Items) ▾
                </button>
                <span style="font-size:0.75rem;color:var(--slate-500);">
                    🔐 Handshake Code: <strong>${d.buyer_otp || '••••'}</strong>
                </span>
            </div>

            <div id="manifest-table-${d.delivery_id}" style="display:none;margin-top:0.75rem;background:#f8fafc;padding:0.75rem;border-radius:var(--radius-md);border:1px solid #e2e8f0;">
                <table class="manifest-table">
                    <thead>
                        <tr>
                            <th>Crop / Variety</th>
                            <th>Grade</th>
                            <th>Source Farm</th>
                            <th>Weight</th>
                            <th style="text-align:right;">Subtotal</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${manifestRows || '<tr><td colspan="5" style="text-align:center;padding:1rem;color:var(--slate-400);">No specific item rows found.</td></tr>'}
                    </tbody>
                </table>
                <div style="display:flex;gap:1rem;font-size:0.75rem;color:#16a34a;margin-top:0.6rem;font-weight:600;padding-top:0.4rem;border-top:1px dashed #cbd5e1;">
                    <span>✓ Crates Verified & Counted</span>
                    <span>✓ Quality Graded at Hub</span>
                    <span>✓ Tamper-evident Seal Intact</span>
                </div>
            </div>
        </div>
    `;

    return `
        <div class="auth-card" style="width:100%;max-width:none;margin-bottom:1.5rem;padding:1.75rem;box-shadow:var(--shadow-sm);border:1px solid var(--slate-200);border-radius:var(--radius-lg);">
            <!-- Top Header -->
            <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem;margin-bottom:1rem;border-bottom:1px solid var(--slate-100);padding-bottom:1rem;">
                <div>
                    <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;margin-bottom:0.35rem;">
                        <h3 style="font-size:1.25rem;margin:0;color:var(--slate-900);">Delivery #${d.delivery_id}</h3>
                        <span style="font-size:0.85rem;color:var(--slate-500);">(Order #${d.order_id})</span>
                        <span class="status-badge ${getDeliveryBadgeClass(d.status)}">${d.status.toUpperCase()}</span>
                        ${weightBadge}
                        ${itemsBadge}
                    </div>
                    <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;font-size:0.85rem;color:var(--slate-500);">
                        <span>Tracking: <code>${d.tracking_reference || 'TRK-' + d.delivery_id}</code></span>
                        <span>•</span>
                        ${driverLabel}
                    </div>
                </div>

                <div>
                    ${actionBtn}
                </div>
            </div>

            <!-- Visual Progress Step Bar -->
            ${stepBar}

            <!-- 2-Column Hub Pickup & Buyer Delivery Route Grid -->
            <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(300px, 1fr));gap:1.25rem;margin-bottom:0.75rem;font-size:0.9rem;">
                <!-- Pickup Facility -->
                <div style="background:#f8fafc;padding:1.15rem;border-radius:var(--radius-md);border:1px solid #e2e8f0;display:flex;flex-direction:column;justify-content:space-between;">
                    <div>
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;">
                            <span style="font-size:0.75rem;font-weight:700;color:#c2410c;text-transform:uppercase;letter-spacing:0.5px;">
                                🏭 1. Pickup Collection Hub
                            </span>
                            <span style="font-size:0.75rem;color:var(--slate-500);">${d.hub_district || ''}</span>
                        </div>
                        <div style="font-weight:700;color:var(--slate-900);font-size:1.05rem;margin-bottom:0.25rem;">
                            ${d.hub_name}
                        </div>
                        <div style="color:var(--slate-600);font-size:0.85rem;line-height:1.4;margin-bottom:0.75rem;">
                            ${d.hub_address || 'Regional Agro Collection Hub'}
                        </div>
                    </div>

                    <div style="display:flex;gap:0.5rem;flex-wrap:wrap;border-top:1px solid #e2e8f0;padding-top:0.75rem;">
                        <a href="${hubMapUrl}" target="_blank" class="btn-nav-map">
                            🗺️ Navigate to Hub
                        </a>
                    </div>
                </div>

                <!-- Destination Buyer -->
                <div style="background:#f0fdf4;padding:1.15rem;border-radius:var(--radius-md);border:1px solid #bbf7d0;display:flex;flex-direction:column;justify-content:space-between;">
                    <div>
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;">
                            <span style="font-size:0.75rem;font-weight:700;color:#15803d;text-transform:uppercase;letter-spacing:0.5px;">
                                🏠 2. Delivery Destination
                            </span>
                            <span style="font-size:0.75rem;color:#15803d;font-weight:700;">₹${Number(d.total_amount || 0).toLocaleString()} Value</span>
                        </div>
                        <div style="font-weight:700;color:var(--slate-900);font-size:1.05rem;margin-bottom:0.25rem;">
                            ${d.business_name ? `${d.business_name} (${d.buyer_name})` : d.buyer_name}
                        </div>
                        <div style="color:var(--slate-600);font-size:0.85rem;line-height:1.4;margin-bottom:0.75rem;">
                            📍 ${d.delivery_address || 'Address provided at order time'}
                        </div>
                    </div>

                    <div style="display:flex;gap:0.5rem;flex-wrap:wrap;border-top:1px solid #bbf7d0;padding-top:0.75rem;">
                        <a href="${buyerMapUrl}" target="_blank" class="btn-nav-map" style="color:#15803d;background:#dcfce7;border-color:#86efac;">
                            🗺️ Navigate to Buyer
                        </a>
                        ${d.buyer_phone ? `
                            <a href="tel:${d.buyer_phone}" class="btn-call-buyer">
                                📞 Call (${d.buyer_phone})
                            </a>
                        ` : ''}
                    </div>
                </div>
            </div>

            <!-- Expandable Cargo Manifest Section -->
            ${manifestSection}
        </div>
    `;
}

function getDeliveryBadgeClass(status) {
    switch (status) {
        case 'assigned': return 'badge-open';
        case 'picked_up': return 'badge-warning';
        case 'in_transit': return 'badge-matched';
        case 'delivered': return 'badge-paid';
        default: return 'badge-open';
    }
}

function toggleManifest(deliveryId) {
    const el = document.getElementById(`manifest-table-${deliveryId}`);
    if (el) {
        el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }
}

// ==========================================
// 4. CLAIM & STATUS ACTIONS
// ==========================================
async function claimRun(deliveryId) {
    try {
        await apiFetch(`/deliveries/${deliveryId}/claim`, { method: 'PUT' });
        showToast('Delivery run successfully claimed!', 'success');
        await loadDeliveries();
    } catch (err) {
        showToast(err.message || 'Failed to claim run.', 'error');
    }
}

async function updateRunStatus(deliveryId, newStatus) {
    try {
        await apiFetch(`/deliveries/${deliveryId}/status`, {
            method: 'PUT',
            body: JSON.stringify({ status: newStatus })
        });
        showToast(`Delivery updated: ${newStatus.replace('_', ' ').toUpperCase()}`, 'success');
        await loadDeliveries();
    } catch (err) {
        showToast(err.message || 'Failed to update delivery status.', 'error');
    }
}

// ==========================================
// 5. DIGITAL PROOF OF DELIVERY (e-POD)
// ==========================================
function openEpodModal(deliveryId) {
    const d = allDeliveries.find(item => item.delivery_id === deliveryId);
    if (!d) return;

    activeEpodDeliveryId = deliveryId;
    document.getElementById('pod-modal-delivery-id').textContent = d.delivery_id;
    document.getElementById('pod-modal-order-id').textContent = d.order_id;

    // Reset fields
    document.getElementById('pod-otp-input').value = '';
    document.getElementById('pod-notes-input').value = '';
    document.getElementById('pod-photo-file').value = '';
    document.getElementById('pod-photo-preview-wrap').style.display = 'none';
    currentPhotoBase64 = null;

    // Show friendly demo hint with OTP
    const hintEl = document.getElementById('pod-otp-hint');
    if (hintEl) {
        hintEl.textContent = `(Buyer Code: ${d.buyer_otp || '••••'})`;
    }

    clearSignaturePad();

    const modal = document.getElementById('epod-modal');
    if (modal) modal.style.display = 'flex';
}

function closeEpodModal() {
    const modal = document.getElementById('epod-modal');
    if (modal) modal.style.display = 'none';
    activeEpodDeliveryId = null;
}

// Signature Canvas implementation
function initSignatureCanvas() {
    sigCanvas = document.getElementById('pod-signature-canvas');
    if (!sigCanvas) return;
    sigCtx = sigCanvas.getContext('2d');

    // Drawing styles
    sigCtx.lineWidth = 2.5;
    sigCtx.lineCap = 'round';
    sigCtx.lineJoin = 'round';
    sigCtx.strokeStyle = '#0f172a';

    function getCoords(e) {
        const rect = sigCanvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        const scaleX = sigCanvas.width / rect.width;
        const scaleY = sigCanvas.height / rect.height;
        return {
            x: (clientX - rect.left) * scaleX,
            y: (clientY - rect.top) * scaleY
        };
    }

    function startDraw(e) {
        isDrawing = true;
        const { x, y } = getCoords(e);
        sigCtx.beginPath();
        sigCtx.moveTo(x, y);
    }

    function draw(e) {
        if (!isDrawing) return;
        e.preventDefault();
        const { x, y } = getCoords(e);
        sigCtx.lineTo(x, y);
        sigCtx.stroke();
    }

    function stopDraw() {
        isDrawing = false;
    }

    // Mouse events
    sigCanvas.addEventListener('mousedown', startDraw);
    sigCanvas.addEventListener('mousemove', draw);
    window.addEventListener('mouseup', stopDraw);

    // Touch events
    sigCanvas.addEventListener('touchstart', startDraw, { passive: false });
    sigCanvas.addEventListener('touchmove', draw, { passive: false });
    window.addEventListener('touchend', stopDraw);
}

function clearSignaturePad() {
    if (sigCtx && sigCanvas) {
        sigCtx.clearRect(0, 0, sigCanvas.width, sigCanvas.height);
    }
}

function isSignatureBlank() {
    if (!sigCanvas) return true;
    const blank = document.createElement('canvas');
    blank.width = sigCanvas.width;
    blank.height = sigCanvas.height;
    return sigCanvas.toDataURL() === blank.toDataURL();
}

// Photo select handler
function handlePodPhotoSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        currentPhotoBase64 = e.target.result;
        const img = document.getElementById('pod-preview-img');
        const wrap = document.getElementById('pod-photo-preview-wrap');
        if (img && wrap) {
            img.src = currentPhotoBase64;
            wrap.style.display = 'block';
        }
    };
    reader.readAsDataURL(file);
}

// Submit e-POD verification
async function submitEpodDelivery() {
    if (!activeEpodDeliveryId) return;

    const otpInput = document.getElementById('pod-otp-input');
    const otp = otpInput ? otpInput.value.trim() : '';

    if (!otp || otp.length !== 4) {
        showToast('Please enter the 4-digit Handshake OTP provided by the buyer.', 'error');
        if (otpInput) otpInput.focus();
        return;
    }

    const notes = document.getElementById('pod-notes-input').value.trim();
    const signature = !isSignatureBlank() ? sigCanvas.toDataURL('image/png') : null;

    const submitBtn = document.getElementById('epod-submit-btn');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Verifying Handshake...';

    try {
        const res = await apiFetch(`/deliveries/${activeEpodDeliveryId}/status`, {
            method: 'PUT',
            body: JSON.stringify({
                status: 'delivered',
                pod: {
                    otp: otp,
                    notes: notes,
                    signature: signature,
                    photo: currentPhotoBase64
                }
            })
        });

        if (res && res.status === 'success') {
            showToast('✓ Delivery confirmed with Digital Proof of Delivery! Payouts unlocked.', 'success');
            closeEpodModal();
            await loadDeliveries();
        }
    } catch (err) {
        showToast(err.message || 'OTP verification failed.', 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// View e-POD receipt
function viewEpodReceipt(deliveryId) {
    const d = allDeliveries.find(item => item.delivery_id === deliveryId);
    if (!d) return;

    const body = document.getElementById('epod-view-body');
    const epod = d.epod || {};

    const signatureImg = epod.signature 
        ? `<div style="margin-top:0.75rem;"><span style="font-size:0.75rem;font-weight:700;color:var(--slate-500);text-transform:uppercase;">Recipient Signature:</span><div style="background:#fff;border:1px solid #cbd5e1;border-radius:6px;padding:0.4rem;text-align:center;margin-top:0.25rem;"><img src="${epod.signature}" style="max-height:80px;"></div></div>`
        : '<div style="color:var(--slate-400);font-size:0.8rem;margin-top:0.5rem;">Signature: Captured upon handover</div>';

    const photoImg = epod.photo 
        ? `<div style="margin-top:0.75rem;"><span style="font-size:0.75rem;font-weight:700;color:var(--slate-500);text-transform:uppercase;">Delivered Crates Photo Proof:</span><div style="background:#fff;border:1px solid #cbd5e1;border-radius:6px;padding:0.4rem;text-align:center;margin-top:0.25rem;"><img src="${epod.photo}" style="max-height:140px;border-radius:4px;"></div></div>`
        : '';

    body.innerHTML = `
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:var(--radius-md);padding:1rem;margin-bottom:1rem;">
            <div style="display:flex;justify-content:space-between;margin-bottom:0.5rem;">
                <span style="color:var(--slate-500);">Delivery Ref:</span>
                <strong>#${d.delivery_id} (Order #${d.order_id})</strong>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.5rem;">
                <span style="color:var(--slate-500);">Delivered To:</span>
                <strong>${d.business_name || d.buyer_name}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.5rem;">
                <span style="color:var(--slate-500);">Verification Status:</span>
                <strong style="color:#16a34a;">✓ 4-Digit Handshake Verified (PIN ${epod.otp || d.buyer_otp || '••••'})</strong>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.5rem;">
                <span style="color:var(--slate-500);">Completed At:</span>
                <span>${epod.verified_at || new Date(d.delivery_time || d.updated_at).toLocaleString()}</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--slate-500);">Cargo Hauled:</span>
                <strong>${d.total_weight_kg || 0} kg • ₹${Number(d.total_amount || 0).toLocaleString()} Value</strong>
            </div>
        </div>

        ${epod.notes ? `
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:var(--radius-md);padding:0.75rem;margin-bottom:0.75rem;">
                <span style="font-size:0.75rem;font-weight:700;color:#15803d;text-transform:uppercase;">Driver Handoff Notes:</span>
                <p style="margin:0.25rem 0 0;font-size:0.85rem;color:#166534;">${epod.notes}</p>
            </div>
        ` : ''}

        ${signatureImg}
        ${photoImg}
    `;

    const modal = document.getElementById('epod-view-modal');
    if (modal) modal.style.display = 'flex';
}

function closeEpodViewModal() {
    const modal = document.getElementById('epod-view-modal');
    if (modal) modal.style.display = 'none';
}

// ─────────────────────────────────────────────────────────────────────────────
// DRIVER PAYOUTS & WALLET
// ─────────────────────────────────────────────────────────────────────────────

async function openDriverPayoutsModal() {
    const modal = document.getElementById('driver-payouts-modal');
    if (!modal) return;

    modal.style.display = 'flex';
    const listEl = document.getElementById('driver-payouts-list');
    listEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--slate-400);">Loading your earnings ledger...</div>';

    try {
        const res = await apiFetch('/delivery/my-payouts');
        const payouts = res.payouts || [];
        const metrics = res.metrics || { total_earned: 0, pending_disbursement: 0 };

        document.getElementById('payout-total-paid').textContent = `₹${Number(metrics.total_earned).toFixed(2)}`;
        document.getElementById('payout-pending-disb').textContent = `₹${Number(metrics.pending_disbursement).toFixed(2)}`;

        if (!payouts.length) {
            listEl.innerHTML = `
                <div style="text-align:center;padding:2rem;background:#f8fafc;border-radius:8px;border:1px dashed #cbd5e1;">
                    <div style="font-size:1.8rem;margin-bottom:0.5rem;">📦</div>
                    <strong style="color:var(--slate-700);">No trip payouts yet</strong>
                    <p style="font-size:0.8rem;color:var(--slate-500);margin:0.25rem 0 0;">Complete and verify deliveries to earn trip allowances and km bonuses.</p>
                </div>
            `;
            return;
        }

        listEl.innerHTML = `
            <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
                <thead>
                    <tr style="border-bottom:2px solid #e2e8f0;text-align:left;color:#64748b;font-size:0.75rem;">
                        <th style="padding:0.5rem 0.25rem;">Payout ID</th>
                        <th style="padding:0.5rem 0.25rem;">Order / Run</th>
                        <th style="padding:0.5rem 0.25rem;">Cargo</th>
                        <th style="padding:0.5rem 0.25rem;text-align:right;">Amount</th>
                        <th style="padding:0.5rem 0.25rem;text-align:center;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${payouts.map(p => {
                        const isPaid = p.payout_status === 'paid';
                        const badgeStyle = isPaid 
                            ? 'background:#dcfce7;color:#166534;' 
                            : 'background:#fef3c7;color:#92400e;';
                        const dateStr = p.created_at ? new Date(p.created_at).toLocaleDateString('en-IN', { day:'numeric', month:'short' }) : '--';

                        return `
                            <tr style="border-bottom:1px solid #f1f5f9;">
                                <td style="padding:0.6rem 0.25rem;">
                                    <strong>#PAY-${p.payout_id}</strong>
                                    <div style="font-size:0.7rem;color:#64748b;">${dateStr}</div>
                                </td>
                                <td style="padding:0.6rem 0.25rem;">
                                    <div>Order #${p.order_id}</div>
                                    <div style="font-size:0.7rem;color:#64748b;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${p.delivery_address || 'Handoff point'}</div>
                                </td>
                                <td style="padding:0.6rem 0.25rem;">${p.cargo_weight_kg || 0} kg</td>
                                <td style="padding:0.6rem 0.25rem;text-align:right;font-weight:700;color:#15803d;">₹${Number(p.total_payout).toFixed(2)}</td>
                                <td style="padding:0.6rem 0.25rem;text-align:center;">
                                    <span style="font-size:0.7rem;font-weight:700;padding:0.15rem 0.45rem;border-radius:99px;${badgeStyle}">
                                        ${(p.payout_status || 'PENDING').toUpperCase()}
                                    </span>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;

    } catch (err) {
        listEl.innerHTML = `<div style="color:var(--status-danger);padding:1.5rem;text-align:center;">Failed to load payouts: ${err.message}</div>`;
    }
}

function closeDriverPayoutsModal() {
    const modal = document.getElementById('driver-payouts-modal');
    if (modal) modal.style.display = 'none';
}
