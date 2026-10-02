/**
 * AgriSmart Connect - Farmer Dashboard Logic
 */

document.addEventListener('DOMContentLoaded', async () => {
    const user = getCurrentUser();
    if (!user) {
        window.location.href = '/login.html';
        return;
    }
    if (user.role !== 'farmer' && user.role !== 'admin') {
        showToast('Access restricted to Farmers.', 'error');
        setTimeout(() => window.location.href = '/index.html', 1500);
        return;
    }

    await loadFarmerProfile();
    await loadCropsAndHubs();
    await loadFarmerProduce();
    initProduceForm();
    initFarmerPrecisionTools();
});

// ==========================================
// 1. LOAD FARMER PROFILE & METRICS
// ==========================================
async function loadFarmerProfile() {
    try {
        const res = await apiFetch('/farmers/profile');
        const p = res.profile;
        const s = res.summary;

        // Populate header & farm details
        document.getElementById('farmer-name-display').innerText = p.name;
        document.getElementById('farm-name-display').innerText = p.farm_name || 'My Agro Farm';
        document.getElementById('farm-location-display').innerText = `${p.village ? p.village + ', ' : ''}${p.district || ''} (${p.state || ''})`;
        document.getElementById('farm-size-display').innerText = p.farm_size ? `${p.farm_size} Acres` : 'N/A';
        if (p.district) farmerDistrict = p.district;

        // Summary Metric Cards
        document.getElementById('stat-listings').innerText = s.total_listings || 0;
        document.getElementById('stat-available-kg').innerText = `${Number(s.total_available_kg || 0).toLocaleString()} kg`;
        document.getElementById('stat-reserved-kg').innerText = `${Number(s.total_reserved_kg || 0).toLocaleString()} kg`;
        document.getElementById('stat-paid-earnings').innerText = `₹${Number(s.paid_earnings || 0).toLocaleString()}`;
        document.getElementById('stat-pending-earnings').innerText = `₹${Number(s.pending_earnings || 0).toLocaleString()}`;

    } catch (err) {
        showToast('Failed to load profile details: ' + err.message, 'error');
    }
}

// ==========================================
// 2. LOAD CROPS & HUBS FOR FORM
// ==========================================
let farmerDistrict = 'Namakkal'; // default fallback

async function loadCropsAndHubs() {
    try {
        const [cropsRes, hubsRes] = await Promise.all([
            apiFetch('/crops'),
            apiFetch('/hubs')
        ]);

        const cropSelect = document.getElementById('produce-crop-select');
        const hubSelect = document.getElementById('produce-hub-select');

        // Populate crops
        cropSelect.innerHTML = '<option value="">-- Select Crop --</option>';
        (cropsRes.crops || []).forEach(c => {
            cropSelect.innerHTML += `<option value="${c.crop_id}" data-name="${c.crop_name}" data-category="${c.category || 'Vegetables'}">${c.crop_name} (${c.category || 'Produce'})</option>`;
        });

        // Dynamic varieties and AI Price Insight on crop change
        cropSelect.addEventListener('change', async () => {
            const cropId = cropSelect.value;
            const selectedOpt = cropSelect.options[cropSelect.selectedIndex];
            const cropName = selectedOpt ? selectedOpt.getAttribute('data-name') : '';
            const category = selectedOpt ? selectedOpt.getAttribute('data-category') : 'Vegetables';

            const varietySelect = document.getElementById('produce-variety-select');
            varietySelect.innerHTML = '<option value="">-- Select Variety --</option>';

            const categorySelect = document.getElementById('produce-category-select');
            if (categorySelect && category) {
                categorySelect.value = category;
            }

            const titleInput = document.getElementById('produce-product-name');
            if (titleInput && cropName && !titleInput.value) {
                titleInput.value = `Fresh ${cropName} (${farmerDistrict || 'Tamil Nadu'})`;
            }

            if (!cropId) {
                document.getElementById('ai-price-insight-banner').style.display = 'none';
                return;
            }

            // Fetch varieties
            try {
                const varRes = await apiFetch(`/crops/${cropId}/varieties`);
                (varRes.varieties || []).forEach(v => {
                    varietySelect.innerHTML += `<option value="${v.variety_id}" data-name="${v.variety_name}">${v.variety_name}</option>`;
                });
            } catch (err) {
                console.error('Error fetching varieties:', err);
            }

            // Fetch AI Price Insight
            await updatePriceInsight(cropName);

            // Fetch AI Hub Recommendation
            await updateHubRecommendation(cropId);
        });

        // Populate hubs
        hubSelect.innerHTML = '<option value="">-- Select Preferred Hub --</option>';
        (hubsRes.hubs || []).forEach(h => {
            hubSelect.innerHTML += `<option value="${h.hub_id}">${h.hub_name} (${h.district || ''})</option>`;
        });

    } catch (err) {
        console.error('Error loading crops or hubs:', err);
    }
}

async function updatePriceInsight(cropName) {
    const banner = document.getElementById('ai-price-insight-banner');
    const rangeDisplay = document.getElementById('price-range-display');
    const fairDisplay = document.getElementById('price-fair-display');
    const priceInput = document.getElementById('produce-min-price');

    if (!banner || !cropName) return;

    try {
        const res = await apiFetch(`/farmers/price-insight?crop_name=${encodeURIComponent(cropName)}&district=${encodeURIComponent(farmerDistrict)}`);
        if (res && res.status === 'success') {
            banner.style.display = 'block';
            if (rangeDisplay) rangeDisplay.innerText = res.recent_marketplace_range;
            if (fairDisplay) fairDisplay.innerText = res.estimated_fair_range;

            // If price input empty, suggest fair average
            if (priceInput && (!priceInput.value || priceInput.value == '0')) {
                priceInput.value = res.average_price || 35.0;
            }
        }
    } catch (e) {
        console.warn('AI Price Insight notice:', e.message);
    }
}

async function updateHubRecommendation(cropId) {
    const recBadge = document.getElementById('ai-hub-rec-badge');
    const hubSelect = document.getElementById('produce-hub-select');
    if (!recBadge || !hubSelect) return;

    try {
        const res = await apiFetch(`/logistics/recommend-hub?crop_id=${cropId}&district=${encodeURIComponent(farmerDistrict)}`);
        if (res && res.recommended_hub) {
            recBadge.innerText = `💡 Recommended: ${res.recommended_hub.hub_name} (${res.recommended_hub.distance_km || 'Nearby'} km)`;
            // Auto select if no manual selection yet
            if (!hubSelect.value) {
                hubSelect.value = res.recommended_hub.hub_id;
            }
        }
    } catch (e) {
        recBadge.innerText = '';
    }
}

// ==========================================
// 2B. AI PRODUCT ASSISTANT (DESCRIPTION & CHECKLIST)
// ==========================================
async function triggerFarmerAIAssist() {
    const cropSelect = document.getElementById('produce-crop-select');
    const selectedOpt = cropSelect.options[cropSelect.selectedIndex];
    const cropName = selectedOpt ? selectedOpt.getAttribute('data-name') : '';

    if (!cropName) {
        showToast('Please select a crop first.', 'warning');
        return;
    }

    const varietySelect = document.getElementById('produce-variety-select');
    const varietyOpt = varietySelect.options[varietySelect.selectedIndex];
    const varietyName = varietyOpt && varietyOpt.value ? varietyOpt.getAttribute('data-name') : '';
    const grade = document.getElementById('produce-grade-select').value || 'Grade A';

    const descInput = document.getElementById('produce-description');
    const checklistDiv = document.getElementById('ai-assist-checklist');

    try {
        const res = await apiFetch('/farmers/ai-assist', {
            method: 'POST',
            body: JSON.stringify({
                crop_name: cropName,
                variety: varietyName,
                quality_grade: grade,
                district: farmerDistrict
            })
        });

        if (res && res.status === 'success' && res.assistant) {
            const a = res.assistant;
            if (descInput) descInput.value = a.desc || '';
            if (checklistDiv && a.checklist) {
                checklistDiv.style.display = 'block';
                checklistDiv.innerHTML = `<strong>AI Checklist:</strong> ${a.checklist.map(c => `<span>✓ ${c}</span>`).join(' &bull; ')}`;
            }
            showToast('AI Description & recommendations generated!', 'success');
        }
    } catch (err) {
        showToast('AI assist note: ' + err.message, 'info');
    }
}

// ==========================================
// 3. LOAD FARMER PRODUCE LISTINGS
// ==========================================
async function loadFarmerProduce() {
    const tableBody = document.getElementById('produce-table-body');
    if (!tableBody) return;

    try {
        const res = await apiFetch('/farmers/products');
        const produceList = res.products || res.produce || [];

        if (!produceList.length) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align:center;padding:2.5rem;color:var(--slate-400);">
                        No produce listed yet. Click <strong>+ List New Produce</strong> to register your harvest!
                    </td>
                </tr>
            `;
            return;
        }

        tableBody.innerHTML = produceList.map(item => {
            const statusUpper = (item.status || 'ACTIVE').toUpperCase();
            let badgeClass = 'badge-open';
            let badgeText = statusUpper;

            if (statusUpper === 'ACTIVE' || statusUpper === 'AVAILABLE') {
                badgeClass = 'badge-available';
                badgeText = 'ACTIVE';
            } else if (statusUpper === 'PAUSED') {
                badgeClass = 'badge-matched';
                badgeText = 'PAUSED';
            } else if (statusUpper === 'DRAFT') {
                badgeClass = 'badge-open';
                badgeText = 'DRAFT';
            } else if (statusUpper === 'SOLD_OUT' || statusUpper === 'SOLD') {
                badgeClass = 'badge-paid';
                badgeText = 'SOLD OUT';
            } else if (statusUpper === 'CANCELLED') {
                badgeClass = 'badge-danger';
                badgeText = 'CANCELLED';
            }

            const harvestDateFormatted = item.harvest_date ? new Date(item.harvest_date).toLocaleDateString('en-IN', {
                day: 'numeric',
                month: 'short',
                year: 'numeric'
            }) : 'Immediate';

            const displayTitle = item.product_name || `${item.crop_name} (${item.variety_name || 'Standard'})`;

            return `
                <tr>
                    <td>
                        <div style="display:flex;align-items:center;gap:0.75rem;">
                            ${item.primary_image_url ? `
                                <img src="${item.primary_image_url}" alt="Produce" style="width:40px;height:40px;border-radius:6px;object-fit:cover;border:1px solid var(--slate-200);">
                            ` : `
                                <div style="width:40px;height:40px;border-radius:6px;background:var(--slate-100);display:flex;align-items:center;justify-content:center;font-size:1.1rem;color:var(--slate-400);">🌱</div>
                            `}
                            <div>
                                <strong style="color:var(--slate-900);font-size:0.95rem;">${displayTitle}</strong>
                                <div style="font-size:0.75rem;color:var(--slate-500);">${item.crop_name} &bull; ${item.quality_grade || 'Standard'} &bull; ${item.organic_status === 'organic' ? '<span style="color:#15803d;font-weight:700;">Organic</span>' : 'Conventional'}</div>
                            </div>
                        </div>
                    </td>
                    <td>
                        <div><strong style="color:var(--primary-dark);">${Number(item.available_quantity_kg).toLocaleString()} kg</strong></div>
                        <div style="font-size:0.75rem;color:var(--slate-500);">MOQ: ${item.min_order_quantity_kg || 1} kg</div>
                    </td>
                    <td>
                        <strong>₹${Number(item.minimum_price_per_kg).toFixed(2)}</strong> / kg
                    </td>
                    <td>
                        <div>${harvestDateFormatted}</div>
                        <div style="font-size:0.75rem;color:var(--slate-500);">${item.quality_grade}</div>
                    </td>
                    <td>
                        <div>${item.hub_name || 'Direct / Any Hub'}</div>
                        <div style="font-size:0.75rem;color:var(--slate-500);">${item.hub_district || ''}</div>
                    </td>
                    <td>
                        <span class="status-badge ${badgeClass}">${badgeText}</span>
                    </td>
                    <td>
                        <div style="display:flex;gap:0.35rem;flex-wrap:wrap;">
                            <button class="btn btn-outline btn-sm" onclick="openImageStudio(${item.produce_id}, '${displayTitle.replace(/'/g, "\\'")}')" title="Manage Photos & Studio">
                                📷 Photos
                            </button>
                            ${(statusUpper === 'ACTIVE' || statusUpper === 'AVAILABLE') ? `
                                <button class="btn btn-outline btn-sm" style="color:var(--status-warning);" onclick="toggleProductStatus(${item.produce_id}, 'PAUSED')">
                                    Pause
                                </button>
                            ` : (statusUpper === 'PAUSED' || statusUpper === 'DRAFT') ? `
                                <button class="btn btn-outline btn-sm" style="color:var(--primary);" onclick="toggleProductStatus(${item.produce_id}, 'ACTIVE')">
                                    Publish
                                </button>
                            ` : ''}
                            ${statusUpper !== 'CANCELLED' ? `
                                <button class="btn btn-outline btn-sm" style="color:var(--status-danger);border-color:var(--slate-300);" onclick="cancelProduceListing(${item.produce_id})">
                                    ✕
                                </button>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

    } catch (err) {
        showToast('Error loading produce listings: ' + err.message, 'error');
    }
}

async function toggleProductStatus(produceId, newStatus) {
    try {
        await apiFetch(`/farmers/products/${produceId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status: newStatus })
        });
        showToast(`Product status updated to ${newStatus}`, 'success');
        await loadFarmerProduce();
    } catch (err) {
        showToast(err.message || 'Failed to update product status.', 'error');
    }
}

// ==========================================
// 4. ADD / DRAFT PRODUCE FORM HANDLERS
// ==========================================
function initProduceForm() {
    const form = document.getElementById('add-produce-form');
    if (!form) return;

    // Set default harvest date to tomorrow
    const harvestInput = document.getElementById('produce-harvest-date');
    if (harvestInput) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        harvestInput.value = tomorrow.toISOString().split('T')[0];
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await submitProductForm('ACTIVE');
    });
}

async function saveProductAsDraft() {
    await submitProductForm('DRAFT');
}

async function submitProductForm(targetStatus = 'ACTIVE') {
    const form = document.getElementById('add-produce-form');
    if (!form) return;

    const crop_id = document.getElementById('produce-crop-select').value;
    const variety_id = document.getElementById('produce-variety-select').value || null;
    const product_name = document.getElementById('produce-product-name').value || '';
    const available_quantity_kg = parseFloat(document.getElementById('produce-available-qty').value);
    const minimum_price_per_kg = parseFloat(document.getElementById('produce-min-price').value);
    const harvest_date = document.getElementById('produce-harvest-date').value;
    const quality_grade = document.getElementById('produce-grade-select').value;
    const preferred_hub_id = document.getElementById('produce-hub-select').value || null;
    const description = document.getElementById('produce-description').value || '';
    const min_order_quantity_kg = parseFloat(document.getElementById('produce-moq').value) || 1.0;
    const organic_status = document.getElementById('produce-organic-select').value || 'conventional';
    const initialImgInput = document.getElementById('produce-initial-img');

    if (!crop_id || !available_quantity_kg || !minimum_price_per_kg || !harvest_date) {
        showToast('Please fill in all mandatory fields (Crop, Quantity, Price, Harvest Date).', 'error');
        return;
    }

    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn ? submitBtn.innerHTML : 'Save';
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = targetStatus === 'DRAFT' ? 'Saving Draft...' : 'Listing Product...';
    }

    try {
        const res = await apiFetch('/farmers/products', {
            method: 'POST',
            body: JSON.stringify({
                crop_id,
                variety_id,
                product_name,
                available_quantity_kg,
                minimum_price_per_kg,
                harvest_date,
                quality_grade,
                preferred_hub_id,
                description,
                min_order_quantity_kg,
                organic_status,
                status: targetStatus
            })
        });

        const newProductId = res.product ? res.product.produce_id : null;

        // If an initial image is selected, upload it immediately
        if (newProductId && initialImgInput && initialImgInput.files && initialImgInput.files[0]) {
            const file = initialImgInput.files[0];
            const reader = new FileReader();
            reader.onload = async (ev) => {
                try {
                    await apiFetch(`/farmers/products/${newProductId}/images`, {
                        method: 'POST',
                        body: JSON.stringify({
                            image: ev.target.result,
                            is_primary: true
                        })
                    });
                    await loadFarmerProduce();
                } catch (imgErr) {
                    console.error('Initial image upload note:', imgErr);
                }
            };
            reader.readAsDataURL(file);
        }

        showToast(targetStatus === 'DRAFT' ? 'Draft saved successfully!' : 'Product listed on marketplace!', 'success');
        form.reset();
        closeModal('add-produce-modal');

        await loadFarmerProfile();
        await loadFarmerProduce();

    } catch (err) {
        showToast(err.message || 'Failed to register product.', 'error');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    }
}

// ==========================================
// 5. CANCEL PRODUCE
// ==========================================
async function cancelProduceListing(produceId) {
    if (!confirm('Are you sure you want to cancel / archive this produce listing?')) return;

    try {
        await apiFetch(`/farmers/products/${produceId}`, { method: 'DELETE' });
        showToast('Produce listing archived.', 'info');
        await loadFarmerProfile();
        await loadFarmerProduce();
    } catch (err) {
        showToast(err.message || 'Failed to cancel listing.', 'error');
    }
}

// ==========================================
// 5B. HTML5 CANVAS IMAGE STUDIO
// ==========================================
let currentStudioProduceId = null;
let studioOriginalImg = null;
let studioCanvasState = {
    rotationDeg: 0,
    brightness: 100,
    contrast: 100,
    isSquareCropped: false
};

async function openImageStudio(produceId, productName) {
    currentStudioProduceId = produceId;
    const titleEl = document.getElementById('image-studio-subtitle');
    if (titleEl) {
        titleEl.innerText = `Editing photos for: ${productName || 'Product #' + produceId}`;
    }

    resetStudioCanvas();
    openModal('image-studio-modal');
    await loadStudioGallery(produceId);
}

async function loadStudioGallery(produceId) {
    const galleryList = document.getElementById('studio-gallery-list');
    if (!galleryList) return;

    galleryList.innerHTML = '<div style="color:var(--slate-400);font-size:0.85rem;">Loading gallery...</div>';

    try {
        const res = await apiFetch(`/farmers/products/${produceId}`);
        const images = (res.product && res.product.images) ? res.product.images : [];

        if (!images.length) {
            galleryList.innerHTML = '<div style="color:var(--slate-400);font-size:0.85rem;padding:1rem;text-align:center;">No photos uploaded yet. Select a file on the left to enhance and upload!</div>';
            return;
        }

        galleryList.innerHTML = images.map(img => `
            <div style="display:flex;align-items:center;justify-content:space-between;background:var(--white);padding:0.6rem;border-radius:var(--radius-md);border:1px solid var(--slate-200);gap:0.75rem;">
                <div style="display:flex;align-items:center;gap:0.6rem;">
                    <img src="${img.image_url}" alt="Product" style="width:48px;height:48px;border-radius:4px;object-fit:cover;border:1px solid var(--slate-200);">
                    <div>
                        <div style="font-size:0.8rem;font-weight:700;color:var(--slate-800);">
                            ${img.is_primary ? '⭐ Primary Display' : 'Gallery Photo'}
                        </div>
                        <div style="font-size:0.7rem;color:var(--slate-400);">ID: ${img.image_id}</div>
                    </div>
                </div>
                <div style="display:flex;gap:0.35rem;">
                    ${!img.is_primary ? `
                        <button class="btn btn-outline btn-sm" onclick="setPrimaryImage(${produceId}, ${img.image_id})" style="font-size:0.75rem;padding:0.2rem 0.5rem;">
                            Set Primary
                        </button>
                    ` : '<span style="color:#15803d;font-size:0.75rem;font-weight:700;padding:0 0.5rem;">✓ Active</span>'}
                    <button class="btn btn-outline btn-sm" onclick="deleteStudioImage(${produceId}, ${img.image_id})" style="color:var(--status-danger);border-color:var(--slate-200);font-size:0.75rem;padding:0.2rem 0.5rem;">
                        ✕
                    </button>
                </div>
            </div>
        `).join('');

    } catch (e) {
        galleryList.innerHTML = `<div style="color:var(--status-danger);font-size:0.8rem;">Error loading gallery: ${e.message}</div>`;
    }
}

async function setPrimaryImage(produceId, imageId) {
    try {
        await apiFetch(`/farmers/products/${produceId}/images/${imageId}`, {
            method: 'PUT',
            body: JSON.stringify({ is_primary: true })
        });
        showToast('Primary product image updated!', 'success');
        await loadStudioGallery(produceId);
        await loadFarmerProduce();
    } catch (e) {
        showToast(e.message || 'Failed to update primary image.', 'error');
    }
}

async function deleteStudioImage(produceId, imageId) {
    if (!confirm('Are you sure you want to delete this photo?')) return;
    try {
        await apiFetch(`/farmers/products/${produceId}/images/${imageId}`, { method: 'DELETE' });
        showToast('Photo removed from gallery.', 'info');
        await loadStudioGallery(produceId);
        await loadFarmerProduce();
    } catch (e) {
        showToast(e.message || 'Failed to delete photo.', 'error');
    }
}

function handleStudioFileSelect(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    if (!file.type.match('image.*')) {
        showToast('Please select a valid image file (PNG, JPG, WebP).', 'error');
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            studioOriginalImg = img;
            studioCanvasState = { rotationDeg: 0, brightness: 100, contrast: 100, isSquareCropped: false };
            document.getElementById('studio-brightness').value = 100;
            document.getElementById('studio-contrast').value = 100;
            document.getElementById('bright-val').innerText = '100%';
            document.getElementById('contrast-val').innerText = '100%';
            document.getElementById('studio-empty-msg').style.display = 'none';
            renderStudioCanvas();
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function renderStudioCanvas() {
    if (!studioOriginalImg) return;

    const canvas = document.getElementById('studio-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const deg = studioCanvasState.rotationDeg % 360;
    const isSideways = (deg === 90 || deg === 270);

    let srcW = studioOriginalImg.width;
    let srcH = studioOriginalImg.height;

    // Determine crop if square crop active
    let sx = 0, sy = 0, sw = srcW, sh = srcH;
    if (studioCanvasState.isSquareCropped) {
        const side = Math.min(srcW, srcH);
        sx = (srcW - side) / 2;
        sy = (srcH - side) / 2;
        sw = side;
        sh = side;
    }

    // Set canvas dimensions
    const destW = isSideways ? sh : sw;
    const destH = isSideways ? sw : sh;

    // Scale down for preview if excessively large
    const maxDimension = 600;
    const scale = Math.min(1, maxDimension / Math.max(destW, destH));

    canvas.width = destW * scale;
    canvas.height = destH * scale;

    ctx.save();
    // Apply CSS filters for brightness and contrast
    ctx.filter = `brightness(${studioCanvasState.brightness}%) contrast(${studioCanvasState.contrast}%)`;

    // Handle rotation around center
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((deg * Math.PI) / 180);

    const drawW = (isSideways ? destH : destW) * scale;
    const drawH = (isSideways ? destW : destH) * scale;

    ctx.drawImage(studioOriginalImg, sx, sy, sw, sh, -drawW / 2, -drawH / 2, drawW, drawH);
    ctx.restore();
}

function rotateStudioCanvas(deg) {
    if (!studioOriginalImg) {
        showToast('Please select an image first.', 'info');
        return;
    }
    studioCanvasState.rotationDeg = (studioCanvasState.rotationDeg + deg) % 360;
    renderStudioCanvas();
}

function cropSquareCanvas() {
    if (!studioOriginalImg) {
        showToast('Please select an image first.', 'info');
        return;
    }
    studioCanvasState.isSquareCropped = !studioCanvasState.isSquareCropped;
    showToast(studioCanvasState.isSquareCropped ? '1:1 Square Crop Applied' : 'Crop Reset to Original Aspect', 'info');
    renderStudioCanvas();
}

function resetStudioCanvas() {
    studioOriginalImg = null;
    studioCanvasState = { rotationDeg: 0, brightness: 100, contrast: 100, isSquareCropped: false };
    const canvas = document.getElementById('studio-canvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    const emptyMsg = document.getElementById('studio-empty-msg');
    if (emptyMsg) emptyMsg.style.display = 'block';

    const fileInput = document.getElementById('studio-file-input');
    if (fileInput) fileInput.value = '';

    const bright = document.getElementById('studio-brightness');
    const contrast = document.getElementById('studio-contrast');
    if (bright) bright.value = 100;
    if (contrast) contrast.value = 100;
    const bVal = document.getElementById('bright-val');
    const cVal = document.getElementById('contrast-val');
    if (bVal) bVal.innerText = '100%';
    if (cVal) cVal.innerText = '100%';
}

function applyCanvasFilters() {
    const bright = document.getElementById('studio-brightness').value;
    const contrast = document.getElementById('studio-contrast').value;
    document.getElementById('bright-val').innerText = `${bright}%`;
    document.getElementById('contrast-val').innerText = `${contrast}%`;

    studioCanvasState.brightness = parseInt(bright, 10);
    studioCanvasState.contrast = parseInt(contrast, 10);
    renderStudioCanvas();
}

async function uploadStudioEditedImage() {
    if (!studioOriginalImg || !currentStudioProduceId) {
        showToast('Please select an image to edit and upload.', 'warning');
        return;
    }

    const canvas = document.getElementById('studio-canvas');
    if (!canvas) return;

    const dataUrl = canvas.toDataURL('image/jpeg', 0.88);

    try {
        showToast('Uploading processed photo...', 'info');
        await apiFetch(`/farmers/products/${currentStudioProduceId}/images`, {
            method: 'POST',
            body: JSON.stringify({
                image: dataUrl,
                is_primary: false
            })
        });

        showToast('Photo uploaded and added to product gallery!', 'success');
        resetStudioCanvas();
        await loadStudioGallery(currentStudioProduceId);
        await loadFarmerProduce();
    } catch (err) {
        showToast(err.message || 'Failed to upload photo.', 'error');
    }
}

// Modal Helpers
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'flex';
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'none';
}

// ==========================================
// 6. FARMER PRECISION TOOLS (AI & IOT)
// ==========================================
let farmerIotState = { pump_status: 'OFF', mode: 'AUTO', soil_moisture_pct: 0, auto_threshold_pct: 35 };

function initFarmerPrecisionTools() {
    loadFarmerIotStatus();
    loadFarmerAiStatus();
    // Poll IoT readings periodically
    setInterval(loadFarmerIotStatus, 8000);

    const input = document.getElementById('farmer-ai-quick-input');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleFarmerQuickAI();
            }
        });
    }
}

async function loadFarmerIotStatus() {
    try {
        const res = await apiFetch('/iot/status');
        if (!res || res.status !== 'success' || !res.live) return;

        const live = res.live;
        farmerIotState = live;

        const moisture = parseFloat(live.soil_moisture_pct || 0);
        const moistureEl = document.getElementById('farmer-iot-moisture-val');
        const barEl = document.getElementById('farmer-iot-moisture-bar');
        const statusEl = document.getElementById('farmer-iot-moisture-status');

        if (moistureEl) moistureEl.textContent = `${moisture.toFixed(1)}%`;
        if (barEl) barEl.style.width = `${Math.min(100, Math.max(0, moisture))}%`;

        if (statusEl) {
            if (moisture < (live.auto_threshold_pct || 35)) {
                statusEl.textContent = 'Soil Dry';
                statusEl.style.color = '#dc2626';
            } else if (moisture > 75) {
                statusEl.textContent = 'Saturated';
                statusEl.style.color = '#0284c7';
            } else {
                statusEl.textContent = 'Optimal Moisture';
                statusEl.style.color = '#16a34a';
            }
        }

        const tempEl = document.getElementById('farmer-iot-temp-val');
        if (tempEl) tempEl.textContent = `${parseFloat(live.temperature_c || 28).toFixed(1)}°C`;

        const modeEl = document.getElementById('farmer-iot-mode-val');
        if (modeEl) modeEl.textContent = live.mode || 'AUTO';

        const threshEl = document.getElementById('farmer-iot-thresh-val');
        if (threshEl) threshEl.textContent = live.auto_threshold_pct || 35;

        // Pump badge and toggle button
        const pumpBadge = document.getElementById('farmer-iot-pump-badge');
        const pumpBtn = document.getElementById('farmer-pump-toggle-btn');

        if (live.pump_status === 'ON') {
            if (pumpBadge) {
                pumpBadge.textContent = '💧 Pump RUNNING';
                pumpBadge.style.background = '#dcfce7';
                pumpBadge.style.color = '#15803d';
            }
            if (pumpBtn) {
                pumpBtn.innerHTML = '🛑 Stop Water Pump';
                pumpBtn.className = 'btn btn-sm btn-outline';
                pumpBtn.style.color = '#dc2626';
                pumpBtn.style.borderColor = '#fca5a5';
                pumpBtn.style.background = '#fef2f2';
            }
        } else {
            if (pumpBadge) {
                pumpBadge.textContent = '⏹️ Pump Standby (OFF)';
                pumpBadge.style.background = '#f1f5f9';
                pumpBadge.style.color = '#475569';
            }
            if (pumpBtn) {
                pumpBtn.innerHTML = '⚡ Turn Pump ON';
                pumpBtn.className = 'btn btn-sm btn-primary';
                pumpBtn.style.color = '#fff';
                pumpBtn.style.borderColor = '';
                pumpBtn.style.background = '';
            }
        }

        const devEl = document.getElementById('farmer-iot-device-label');
        if (devEl && live.device_id) devEl.textContent = `Device: ${live.device_id}`;

    } catch (err) {
        console.warn('IoT telemetry sync note:', err.message);
    }
}

async function toggleFarmerPump() {
    const nextStatus = farmerIotState.pump_status === 'ON' ? 'OFF' : 'ON';
    try {
        const res = await apiFetch('/iot/pump-control', {
            method: 'POST',
            body: JSON.stringify({ 
                pump_status: nextStatus,
                mode: 'MANUAL'
            })
        });
        if (res && res.status === 'success') {
            showToast(`Pump switched to ${nextStatus} (MANUAL mode)`, 'success');
            await loadFarmerIotStatus();
        }
    } catch (err) {
        showToast('Pump switch failed: ' + err.message, 'error');
    }
}

async function toggleFarmerMode() {
    const nextMode = farmerIotState.mode === 'AUTO' ? 'MANUAL' : 'AUTO';
    try {
        const res = await apiFetch('/iot/pump-control', {
            method: 'POST',
            body: JSON.stringify({ mode: nextMode })
        });
        if (res && res.status === 'success') {
            showToast(`Irrigation mode switched to ${nextMode}`, 'info');
            await loadFarmerIotStatus();
        }
    } catch (err) {
        showToast('Mode switch failed: ' + err.message, 'error');
    }
}

async function loadFarmerAiStatus() {
    const badge = document.getElementById('farmer-ai-status-badge');
    if (!badge) return;

    try {
        const res = await apiFetch('/ai/status');
        if (res.ollama && res.ollama.online) {
            badge.textContent = `● AI Ready (${res.ollama.active_model || 'LLaVA'})`;
            badge.style.background = '#dcfce7';
            badge.style.color = '#15803d';
        } else {
            badge.textContent = '● Ollama Standby';
            badge.style.background = '#fef3c7';
            badge.style.color = '#92400e';
        }
    } catch (err) {
        badge.textContent = '● Ollama Standby';
        badge.style.background = '#f1f5f9';
        badge.style.color = '#64748b';
    }
}

async function handleFarmerQuickAI() {
    const input = document.getElementById('farmer-ai-quick-input');
    const responseBox = document.getElementById('farmer-ai-quick-response');
    const btn = document.getElementById('farmer-ai-quick-btn');

    const prompt = input ? input.value.trim() : '';
    if (!prompt) return;

    btn.disabled = true;
    btn.textContent = 'Thinking...';
    responseBox.style.display = 'block';
    responseBox.innerHTML = '<em>🌱 Analyzing agronomy question with local AI...</em>';

    try {
        const res = await apiFetch('/ai/chat', {
            method: 'POST',
            body: JSON.stringify({ message: prompt })
        });
        const aiText = res.response || 'No response received.';
        responseBox.innerHTML = `<strong>AI Agronomist:</strong><br>${aiText.replace(/\n/g, '<br>')}`;
        if (window.AgriVoice && res.response) {
            window.AgriVoice.injectChatListenButton(responseBox, res.response);
        }
    } catch (err) {
        responseBox.innerHTML = `<span style="color:#b91c1c;">AI error: ${err.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Ask AI';
    }
}
