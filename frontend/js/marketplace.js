/**
 * AgriSmart Connect - Marketplace Frontend Controller
 */

let userLocation = { lat: null, lon: null };

document.addEventListener('DOMContentLoaded', async () => {
    await initFilterOptions();
    await fetchMarketplaceListings();
    initFilterListeners();
});

// ==========================================
// 1. POPULATE FILTER DROPDOWNS
// ==========================================
async function initFilterOptions() {
    try {
        const [cropsRes, hubsRes] = await Promise.all([
            apiFetch('/crops'),
            apiFetch('/hubs')
        ]);

        const cropSelect = document.getElementById('filter-crop');
        const hubSelect = document.getElementById('filter-hub');

        if (cropSelect) {
            cropsRes.crops.forEach(c => {
                cropSelect.innerHTML += `<option value="${c.crop_id}">${c.crop_name}</option>`;
            });
        }

        if (hubSelect) {
            hubsRes.hubs.forEach(h => {
                hubSelect.innerHTML += `<option value="${h.hub_id}">${h.hub_name}</option>`;
            });
        }

    } catch (err) {
        console.error('Error loading filter options:', err);
    }
}

// ==========================================
// 2. FETCH MARKETPLACE LISTINGS
// ==========================================
async function fetchMarketplaceListings() {
    const grid = document.getElementById('marketplace-grid');
    const resultCount = document.getElementById('results-count');
    if (!grid) return;

    grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:3rem; color:var(--slate-400);">Loading fresh farm supply...</div>';

    const params = new URLSearchParams();

    const cropId = document.getElementById('filter-crop')?.value;
    const hubId = document.getElementById('filter-hub')?.value;
    const district = document.getElementById('filter-district')?.value;
    const maxPrice = document.getElementById('filter-max-price')?.value;
    const grade = document.getElementById('filter-grade')?.value;
    const organic = document.getElementById('filter-organic')?.value;
    const sortBy = document.getElementById('filter-sort-by')?.value || 'date_asc';
    const maxDistance = document.getElementById('filter-max-distance')?.value;

    if (cropId) params.append('crop_id', cropId);
    if (hubId) params.append('hub_id', hubId);
    if (district) params.append('district', district);
    if (maxPrice) params.append('max_price', maxPrice);
    if (grade) params.append('grade', grade);
    if (organic) params.append('organic', organic);
    if (sortBy) params.append('sort_by', sortBy);

    if (userLocation.lat && userLocation.lon) {
        params.append('lat', userLocation.lat);
        params.append('lon', userLocation.lon);
        if (maxDistance) params.append('max_distance_km', maxDistance);
    }

    try {
        const res = await apiFetch(`/marketplace?${params.toString()}`);
        const items = res.produce || [];

        if (resultCount) {
            resultCount.innerText = `${items.length} Available Batch${items.length === 1 ? '' : 'es'}`;
        }

        if (!items.length) {
            grid.innerHTML = `
                <div style="grid-column:1/-1; text-align:center; padding:4rem 1rem; background:var(--white); border-radius:var(--radius-lg); border:1px solid var(--slate-200);">
                    <div style="font-size:2.5rem; margin-bottom:1rem;">🌾</div>
                    <h3 style="font-size:1.35rem; margin-bottom:0.5rem;">No Produce Matched Your Filters</h3>
                    <p style="color:var(--slate-500); font-size:0.95rem; max-width:450px; margin:0 auto 1.5rem;">
                        Try broadening your search or adjusting your price and distance radius.
                    </p>
                    <button class="btn btn-outline btn-sm" onclick="resetFilters()">Reset All Filters</button>
                </div>
            `;
            return;
        }

        grid.innerHTML = items.map(p => {
            const hDate = p.harvest_date ? new Date(p.harvest_date).toLocaleDateString('en-IN', {
                day: 'numeric',
                month: 'short'
            }) : 'Immediate';

            const distanceBadge = p.distance_km !== null && p.distance_km !== undefined
                ? `<span style="font-size:0.75rem; background:var(--primary-50); color:var(--primary-dark); padding:0.2rem 0.5rem; border-radius:var(--radius-full); font-weight:700;">📍 ${p.distance_km} km away</span>`
                : '';

            const organicBadge = p.organic_status === 'organic'
                ? `<span style="font-size:0.7rem;background:#dcfce7;color:#15803d;padding:0.15rem 0.5rem;border-radius:var(--radius-full);font-weight:700;">🌿 ORGANIC</span>`
                : '';

            const displayTitle = p.product_name || p.crop_name;
            const productUrl = `/product-detail.html?id=${p.produce_id}`;

            const fallbackPhoto = (typeof getCropFallbackPhoto === 'function')
                ? getCropFallbackPhoto(p.crop_name)
                : '/uploads/products/demo/tomato/tomato_hybrid_harvest.jpg';
            const imgUrl = p.primary_image_url || fallbackPhoto;

            const imageHtml = `<div style="width:100%;height:160px;overflow:hidden;border-bottom:1px solid var(--slate-100);cursor:pointer;" onclick="window.location='${productUrl}'">
                       <img src="${imgUrl}" alt="${displayTitle}" loading="lazy"
                            style="width:100%;height:100%;object-fit:cover;transition:transform 0.3s ease;"
                            onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'"
                            onerror="if(this.src!=='${fallbackPhoto}'){this.src='${fallbackPhoto}';}">
                   </div>`;

            return `
                <div class="produce-card" style="cursor:default;">
                    ${imageHtml}
                    <div class="produce-card-header">
                        <div style="flex:1;">
                            <div style="display:flex;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.3rem;">
                                <span class="produce-category-pill">${p.crop_category || 'Produce'}</span>
                                ${organicBadge}
                            </div>
                            <h3 class="produce-title" style="cursor:pointer;" onclick="window.location='${productUrl}'">${displayTitle}</h3>
                            <div class="produce-variety">${p.variety_name || 'Commercial Variety'} &bull; ${p.farm_district || 'Tamil Nadu'}</div>
                        </div>
                        <div class="produce-price">
                            <span class="currency">₹</span><span class="amount">${Number(p.minimum_price_per_kg).toFixed(2)}</span>
                            <span class="unit">/ ${p.unit || 'kg'}</span>
                        </div>
                    </div>

                    <div class="produce-card-body">
                        <div class="produce-detail-row">
                            <span>Available Supply</span>
                            <strong style="color:var(--primary-dark); font-size:1.05rem;">${Number(p.available_quantity_kg).toLocaleString()} kg</strong>
                        </div>
                        <div class="produce-detail-row">
                            <span>Harvest Target</span>
                            <strong>${hDate}</strong>
                        </div>
                        <div class="produce-detail-row">
                            <span>Quality Grade</span>
                            <span class="grade-badge">${p.quality_grade || 'Standard'}</span>
                        </div>
                        <div class="produce-detail-row">
                            <span>Collection Hub</span>
                            <span style="font-size:0.85rem; color:var(--slate-700);">${p.hub_name || 'Nearest Hub'}</span>
                        </div>
                    </div>

                    <div class="produce-card-footer">
                        <div class="farmer-info">
                            <div class="farmer-avatar">🌾</div>
                            <div>
                                <div class="farmer-name">${p.farm_name || p.farmer_name || 'Verified Farmer'}</div>
                                <div class="farmer-location">${p.farm_village ? p.farm_village + ', ' : ''}${p.farm_district || 'Tamil Nadu'} <span style="font-size:0.7rem;background:#f1f5f9;padding:0.1rem 0.35rem;border-radius:4px;margin-left:4px;">✓ DEMO</span></div>
                            </div>
                        </div>
                        <div style="margin-top:0.5rem;">
                            ${distanceBadge}
                        </div>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-top:0.85rem;">
                            <button class="btn btn-outline btn-sm" onclick="window.location='${productUrl}'">
                                View Details
                            </button>
                            <button class="btn btn-primary btn-sm" onclick="openDemandModal(${p.produce_id}, '${(displayTitle).replace(/'/g,"\\'")}'  , '${(p.variety_name || '').replace(/'/g,"\\'")}'  , ${p.minimum_price_per_kg}, ${p.available_quantity_kg})">
                                Order Now
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        grid.innerHTML = `<div style="grid-column:1/-1; color:var(--status-danger); text-align:center; padding:2rem;">Failed to load marketplace: ${err.message}</div>`;
    }
}

// ==========================================
// 3. FILTER LISTENERS & GEOLOCATION
// ==========================================
function initFilterListeners() {
    const inputs = ['filter-crop', 'filter-district', 'filter-hub', 'filter-max-price', 'filter-grade', 'filter-organic', 'filter-sort-by', 'filter-max-distance'];
    inputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', fetchMarketplaceListings);
        }
    });
    // Also trigger on price input (debounced)
    const priceEl = document.getElementById('filter-max-price');
    if (priceEl) {
        let debounceTimer;
        priceEl.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchMarketplaceListings, 600);
        });
    }

    const locBtn = document.getElementById('btn-use-location');
    if (locBtn) {
        locBtn.addEventListener('click', () => {
            if (!navigator.geolocation) {
                showToast('Geolocation not supported.', 'error');
                return;
            }
            locBtn.innerText = 'Detecting...';
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    userLocation.lat = pos.coords.latitude;
                    userLocation.lon = pos.coords.longitude;
                    locBtn.innerText = '📍 Location Active';
                    locBtn.classList.add('btn-primary');
                    locBtn.classList.remove('btn-outline');
                    showToast('Showing produce sorted by proximity to you!', 'success');
                    fetchMarketplaceListings();
                },
                (err) => {
                    showToast('Location error: ' + err.message, 'error');
                    locBtn.innerText = 'Use My Location 📍';
                }
            );
        });
    }
}

function resetFilters() {
    ['filter-crop', 'filter-district', 'filter-hub', 'filter-max-price', 'filter-grade', 'filter-organic', 'filter-max-distance'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    const sortEl = document.getElementById('filter-sort-by');
    if (sortEl) sortEl.value = 'date_asc';
    fetchMarketplaceListings();
}

// Demand / Direct Order Modal
function openDemandModal(produceId, cropName, varietyName, price, availKg) {
    const user = getCurrentUser();
    if (!user) {
        showToast('Please sign in to place an order or create demand.', 'info');
        setTimeout(() => window.location.href = '/login.html', 1200);
        return;
    }

    let modal = document.getElementById('marketplace-order-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'marketplace-order-modal';
        modal.className = 'modal-backdrop';
        modal.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(15,23,42,0.6);backdrop-filter:blur(4px);z-index:2000;align-items:center;justify-content:center;padding:1rem;';
        modal.innerHTML = `
            <div class="modal-content" style="background:var(--white);border-radius:var(--radius-lg);width:100%;max-width:500px;padding:2rem;box-shadow:var(--shadow-xl);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.25rem;border-bottom:1px solid var(--slate-200);padding-bottom:0.75rem;">
                    <h3 id="modal-order-title" style="font-size:1.35rem;">Order Farm Produce</h3>
                    <button class="btn btn-outline btn-sm" onclick="document.getElementById('marketplace-order-modal').style.display='none'">✕</button>
                </div>
                <div id="modal-order-body"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    const defaultAddress = (user.profile && user.profile.address) ? user.profile.address : '';

    document.getElementById('modal-order-title').innerText = `Order ${cropName} (${varietyName || 'Fresh'})`;
    document.getElementById('modal-order-body').innerHTML = `
        <div style="margin-bottom:1rem;background:var(--slate-50);padding:0.75rem 1rem;border-radius:var(--radius-md);font-size:0.9rem;">
            <div>Price Rate: <strong>₹${price} / kg</strong></div>
            <div>Available Supply: <strong>${availKg} kg</strong></div>
        </div>

        <div class="form-group" style="margin-bottom:1rem;">
            <label class="form-label" for="modal-req-qty">Quantity Needed (kg) *</label>
            <input type="number" id="modal-req-qty" class="form-control" min="1" max="${availKg}" value="${Math.min(10, availKg)}" step="1" oninput="updateModalTotals(${price})">
        </div>

        <div class="form-group" style="margin-bottom:1.25rem;">
            <label class="form-label" for="modal-del-address">Delivery Address *</label>
            <textarea id="modal-del-address" class="form-control" rows="2" placeholder="Street, building, area">${defaultAddress}</textarea>
        </div>

        <div style="background:var(--slate-50);border-radius:var(--radius-md);padding:0.85rem 1rem;margin-bottom:1.5rem;font-size:0.88rem;">
            <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
                <span>Subtotal:</span>
                <strong id="modal-subtotal">₹${(price * Math.min(10, availKg)).toFixed(2)}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
                <span>Delivery & Hub Logistics:</span>
                <strong>₹65.00</strong>
            </div>
            <div style="display:flex;justify-content:space-between;border-top:1px solid var(--slate-200);padding-top:0.4rem;font-size:1rem;color:var(--slate-900);">
                <strong>Total Amount:</strong>
                <strong id="modal-total" style="color:var(--primary-dark);">₹${(price * Math.min(10, availKg) + 65.0 + (price * Math.min(10, availKg) * 0.05)).toFixed(2)}</strong>
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;">
            <button class="btn btn-outline" onclick="addModalItemToCart(${produceId}, '${cropName}', '${varietyName || ''}', ${price}, ${availKg})">
                + Add to Cart
            </button>
            <button class="btn btn-primary" onclick="submitDirectOrder(${produceId}, ${price})">
                Place Order Now
            </button>
        </div>
    `;

    modal.style.display = 'flex';
}

function updateModalTotals(price) {
    const qty = parseFloat(document.getElementById('modal-req-qty').value) || 0;
    const subtotal = qty * price;
    const platformFee = subtotal * 0.05;
    const delivery = 65.0;
    const total = subtotal + platformFee + delivery;

    document.getElementById('modal-subtotal').innerText = `₹${subtotal.toFixed(2)}`;
    document.getElementById('modal-total').innerText = `₹${total.toFixed(2)}`;
}

function addModalItemToCart(produceId, cropName, varietyName, price, availKg) {
    const qty = parseFloat(document.getElementById('modal-req-qty').value);
    if (!qty || qty <= 0) {
        showToast('Please enter a valid quantity.', 'error');
        return;
    }
    addToCart({
        produce_id: produceId,
        crop_name: cropName,
        variety_name: varietyName,
        minimum_price_per_kg: price,
        available_quantity_kg: availKg
    }, qty);

    document.getElementById('marketplace-order-modal').style.display = 'none';
}

async function submitDirectOrder(produceId, price) {
    const qty = parseFloat(document.getElementById('modal-req-qty').value);
    const address = document.getElementById('modal-del-address').value.trim();

    if (!qty || qty <= 0) {
        showToast('Please enter a valid quantity.', 'error');
        return;
    }
    if (!address) {
        showToast('Please provide your delivery address.', 'error');
        return;
    }

    try {
        const res = await apiFetch('/orders', {
            method: 'POST',
            body: JSON.stringify({
                delivery_address: address,
                items: [{
                    produce_id: produceId,
                    quantity_kg: qty,
                    price_per_kg: price
                }]
            })
        });

        showToast('Order confirmed! Inventory successfully reserved.', 'success');
        document.getElementById('marketplace-order-modal').style.display = 'none';
        setTimeout(() => {
            window.location.href = '/orders.html';
        }, 1200);

    } catch (err) {
        showToast(err.message || 'Failed to place order.', 'error');
    }
}
