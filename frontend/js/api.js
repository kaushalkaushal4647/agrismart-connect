/**
 * AgriSmart Connect - Core API Client & Utilities
 */

// Auto-load Multilingual Regional Language Support (Tamil, Hindi, Malayalam, Telugu, English)
if (typeof window !== 'undefined' && !document.querySelector('script[src*="i18n.js"]')) {
    const i18nScript = document.createElement('script');
    i18nScript.src = '/js/i18n.js';
    i18nScript.async = false;
    document.head.appendChild(i18nScript);
}

const isLocalhost = (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname === ''
);
const API_BASE = isLocalhost
    ? (window.location.port === '5000' ? `${window.location.origin}/api` : 'http://localhost:5000/api')
    : `${window.location.origin}/api`;

// Realistic photograph catalog fallbacks by crop name
const CROP_FALLBACK_IMAGES = {
    'Tomato': '/uploads/products/demo/tomato/tomato_hybrid_harvest.jpg',
    'Potato': '/uploads/products/demo/potato/potato_kufri_jyoti.jpg',
    'Onion': '/uploads/products/demo/onion/onion_bellary_red.jpg',
    'Moringa': '/uploads/products/demo/moringa/moringa_pkm1_drumsticks.jpg',
    'Drumstick': '/uploads/products/demo/moringa/moringa_pkm1_drumsticks.jpg',
    'Banana': '/uploads/products/demo/banana/banana_grand_naine.jpg',
    'Coconut': '/uploads/products/demo/coconut/coconut_west_coast_tall.jpg',
    'Mango': '/uploads/products/demo/mango/mango_alphonso_ratnagiri.jpg',
    'Brinjal': '/uploads/products/demo/brinjal/brinjal_purple_round.jpg',
    'Carrot': '/uploads/products/demo/carrot/carrot_kuroda_nantes.jpg',
    'Green Chilli': '/uploads/products/demo/green_chilli/green_chilli_g4_spicy.jpg',
    'Chilli': '/uploads/products/demo/green_chilli/green_chilli_g4_spicy.jpg',
    'Rice': '/uploads/products/demo/rice/rice_bpt_samba_masuri.jpg',
    'Paddy': '/uploads/products/demo/rice/rice_bpt_samba_masuri.jpg',
    'Turmeric': '/uploads/products/demo/turmeric/turmeric_erode_gopichettipalayam.jpg',
    'Sugarcane': '/uploads/products/demo/sugarcane/sugarcane_co_86032.jpg',
    'Groundnut': '/uploads/products/demo/groundnut/groundnut_kadiri_6.jpg',
    'Cabbage': '/uploads/products/demo/cabbage/cabbage_golden_acre.jpg'
};

function getCropFallbackPhoto(cropName) {
    if (!cropName) return '/uploads/products/demo/tomato/tomato_hybrid_harvest.jpg';
    for (const [key, val] of Object.entries(CROP_FALLBACK_IMAGES)) {
        if (cropName.toLowerCase().includes(key.toLowerCase())) {
            return val;
        }
    }
    return '/uploads/products/demo/tomato/tomato_hybrid_harvest.jpg';
}

const STORAGE_KEYS = {
    TOKEN: 'agrismart_token',
    USER: 'agrismart_user'
};

// ==========================================
// Authentication Token & User Management
// ==========================================
function getToken() {
    return localStorage.getItem(STORAGE_KEYS.TOKEN);
}

function setToken(token) {
    if (token) {
        localStorage.setItem(STORAGE_KEYS.TOKEN, token);
    } else {
        localStorage.removeItem(STORAGE_KEYS.TOKEN);
    }
}

function getCurrentUser() {
    const raw = localStorage.getItem(STORAGE_KEYS.USER);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function setCurrentUser(user) {
    if (user) {
        localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(user));
    } else {
        localStorage.removeItem(STORAGE_KEYS.USER);
    }
}

function logout() {
    localStorage.removeItem(STORAGE_KEYS.TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USER);
    window.location.href = '/login.html';
}

// ==========================================
// Central Fetch Wrapper
// ==========================================
async function apiFetch(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;

    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {})
    };

    const token = getToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            // If token expired / unauthorized, clear session
            if (response.status === 401 && !url.includes('/auth/login')) {
                setToken(null);
                setCurrentUser(null);
                showToast('Session expired. Please log in again.', 'error');
            }
            const errorMsg = data.message || data.error || `HTTP ${response.status} error`;
            throw new Error(errorMsg);
        }

        return data;
    } catch (err) {
        console.error(`API error on ${endpoint}:`, err);
        throw err;
    }
}

// ==========================================
// System Health Checks
// ==========================================
async function checkSystemHealth() {
    try {
        return await apiFetch('/health');
    } catch (e) {
        return { status: 'offline', error: e.message };
    }
}

async function checkDatabaseHealth() {
    try {
        return await apiFetch('/db-test');
    } catch (e) {
        return { status: 'error', error: e.message };
    }
}

// ==========================================
// Toast Notification Helper
// ==========================================
function showToast(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
    toast.innerHTML = `<span><strong>${icon}</strong></span> <span>${message}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Update Header on Page Load
document.addEventListener('DOMContentLoaded', () => {
    const user = getCurrentUser();
    const authActionsContainer = document.getElementById('nav-auth-actions');
    
    if (authActionsContainer) {
        if (user) {
            const roleBadge = `<span class="brand-badge" style="background:#e0f2fe;color:#0369a1;">${user.role.toUpperCase()}</span>`;
            authActionsContainer.innerHTML = `
                <div style="display:flex;align-items:center;gap:0.75rem;">
                    <span style="font-weight:600;font-size:0.9rem;">Hello, ${user.name}</span>
                    ${roleBadge}
                    <button class="btn btn-outline btn-sm" onclick="logout()">Log Out</button>
                </div>
            `;
        } else {
            authActionsContainer.innerHTML = `
                <a href="/login.html" class="btn btn-outline btn-sm">Sign In</a>
                <a href="/register.html" class="btn btn-primary btn-sm">Get Started</a>
            `;
        }
    }
});
