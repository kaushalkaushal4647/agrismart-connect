/**
 * AgriSmart Connect - Hub Operator Dashboard Logic
 */

let activeHubId = 1;

document.addEventListener('DOMContentLoaded', async () => {
    const user = getCurrentUser();
    if (!user) {
        window.location.href = '/login.html';
        return;
    }
    if (user.role !== 'hub_operator' && user.role !== 'admin') {
        showToast('Access restricted to Hub Operators.', 'error');
        setTimeout(() => window.location.href = '/index.html', 1500);
        return;
    }

    await loadHubsSelector();
    await loadHubQueues();
    initQualityCheckForm();
});

// ==========================================
// 1. HUB SELECTOR
// ==========================================
async function loadHubsSelector() {
    try {
        const res = await apiFetch('/hubs');
        const hubs = res.hubs || [];
        const select = document.getElementById('hub-select');
        if (!select || !hubs.length) return;

        select.innerHTML = hubs.map(h => `
            <option value="${h.hub_id}">${h.hub_name} (${h.district})</option>
        `).join('');

        activeHubId = hubs[0].hub_id;

        select.addEventListener('change', () => {
            activeHubId = select.value;
            loadHubQueues();
        });

    } catch (err) {
        console.error('Failed to load hubs:', err);
    }
}

// ==========================================
// 2. LOAD OPERATIONAL QUEUES
// ==========================================
async function loadHubQueues() {
    try {
        const res = await apiFetch(`/quality-checks/${activeHubId}/queue`);

        renderIncomingProduce(res.incoming_produce || []);
        renderOrdersQueue(res.orders_queue || []);
        renderRecentChecks(res.recent_quality_checks || []);

    } catch (err) {
        showToast('Failed to load hub queues: ' + err.message, 'error');
    }
}

function renderIncomingProduce(list) {
    const tbody = document.getElementById('incoming-produce-tbody');
    if (!tbody) return;

    if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--slate-400);">No incoming farmer produce scheduled.</td></tr>';
        return;
    }

    tbody.innerHTML = list.map(item => `
        <tr>
            <td>
                <strong>${item.crop_name}</strong>
                <div style="font-size:0.75rem;color:var(--slate-500);">${item.variety_name || 'Commercial'}</div>
            </td>
            <td>
                <strong>${item.farm_name}</strong>
                <div style="font-size:0.75rem;color:var(--slate-500);">${item.farmer_name} (${item.farmer_phone})</div>
            </td>
            <td><strong style="color:var(--primary-dark);">${item.available_quantity_kg} kg</strong></td>
            <td>${new Date(item.harvest_date).toLocaleDateString('en-IN', { day:'numeric', month:'short' })}</td>
            <td><span class="status-badge badge-open">${item.quality_grade}</span></td>
            <td>
                <button class="btn btn-outline btn-sm" onclick="openInspectionModal(${item.produce_id}, null, '${item.crop_name}', ${item.available_quantity_kg})">
                    ⚖️ Weigh & Inspect
                </button>
            </td>
        </tr>
    `).join('');
}

function renderOrdersQueue(list) {
    const tbody = document.getElementById('orders-queue-tbody');
    if (!tbody) return;

    if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--slate-400);">No pending orders in hub queue.</td></tr>';
        return;
    }

    tbody.innerHTML = list.map(o => {
        let actionBtn = '';
        if (o.order_status === 'at_hub' || o.order_status === 'collecting') {
            actionBtn = `<button class="btn btn-outline btn-sm" onclick="openInspectionModal(null, ${o.order_id}, 'Order #${o.order_id}', 0)">Inspect QA</button>`;
        } else if (o.order_status === 'quality_checked') {
            actionBtn = `<button class="btn btn-primary btn-sm" onclick="markOrderPacked(${o.order_id})">📦 Pack Order</button>`;
        } else if (o.order_status === 'packed') {
            actionBtn = `<span class="status-badge badge-available">Ready for Driver</span>`;
        }

        return `
            <tr>
                <td><strong>Order #${o.order_id}</strong></td>
                <td>
                    ${o.business_name || o.buyer_name}
                    <div style="font-size:0.75rem;color:var(--slate-500);">${o.buyer_phone}</div>
                </td>
                <td><strong>₹${Number(o.total_amount).toFixed(2)}</strong></td>
                <td><span class="status-badge badge-matched">${o.order_status.replace('_', ' ').toUpperCase()}</span></td>
                <td>${o.tracking_reference || '--'}</td>
                <td>${actionBtn}</td>
            </tr>
        `;
    }).join('');
}

function renderRecentChecks(list) {
    const tbody = document.getElementById('recent-qc-tbody');
    if (!tbody) return;

    if (!list.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--slate-400);">No quality inspections recorded today.</td></tr>';
        return;
    }

    tbody.innerHTML = list.map(q => `
        <tr>
            <td><strong>#QC-${q.quality_check_id}</strong></td>
            <td><strong>${q.actual_weight_kg} kg</strong></td>
            <td><span class="status-badge badge-available">${q.quality_grade}</span></td>
            <td style="color:${q.rejected_quantity_kg > 0 ? 'var(--status-danger)' : 'var(--slate-400)'};">${q.rejected_quantity_kg} kg</td>
            <td>${q.inspector_name || 'Inspector'}</td>
        </tr>
    `).join('');
}

// ==========================================
// 3. QUALITY CHECK MODAL & SUBMIT
// ==========================================
let currentQCTarget = { produceId: null, orderId: null };

function openInspectionModal(produceId, orderId, name, weight) {
    currentQCTarget = { produceId, orderId };
    document.getElementById('modal-qc-target-name').innerText = name;
    document.getElementById('qc-weight').value = weight || '';
    document.getElementById('qc-rejected').value = '0';
    document.getElementById('qc-remarks').value = '';
    document.getElementById('qc-modal').style.display = 'flex';
}

function initQualityCheckForm() {
    const form = document.getElementById('qc-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;

        const payload = {
            hub_id: activeHubId,
            produce_id: currentQCTarget.produceId,
            order_id: currentQCTarget.orderId,
            actual_weight_kg: parseFloat(document.getElementById('qc-weight').value),
            quality_grade: document.getElementById('qc-grade').value,
            rejected_quantity_kg: parseFloat(document.getElementById('qc-rejected').value) || 0.0,
            remarks: document.getElementById('qc-remarks').value.trim()
        };

        try {
            await apiFetch('/quality-checks', {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            showToast('Quality inspection recorded successfully!', 'success');
            document.getElementById('qc-modal').style.display = 'none';
            await loadHubQueues();

        } catch (err) {
            showToast(err.message || 'Inspection recording failed.', 'error');
        } finally {
            submitBtn.disabled = false;
        }
    });
}

async function markOrderPacked(orderId) {
    try {
        await apiFetch(`/quality-checks/orders/${orderId}/pack`, { method: 'PUT' });
        showToast(`Order #${orderId} marked as packed and ready for dispatch!`, 'success');
        await loadHubQueues();
    } catch (err) {
        showToast(err.message || 'Failed to update order packing state.', 'error');
    }
}
