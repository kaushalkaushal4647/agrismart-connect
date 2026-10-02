/**
 * AgriSmart Connect - Authentication & Registration Handlers
 */

document.addEventListener('DOMContentLoaded', () => {
    initLoginForm();
    initRegisterForm();
    initRoleSwitcher();
});

// ==========================================
// 1. LOGIN FORM HANDLER
// ==========================================
function initLoginForm() {
    const loginForm = document.getElementById('login-form');
    if (!loginForm) return;

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = loginForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;

        const identifier = document.getElementById('login-identifier').value.trim();
        const password = document.getElementById('login-password').value;

        if (!identifier || !password) {
            showToast('Please enter both identifier and password.', 'error');
            return;
        }

        try {
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Signing In...';

            const res = await apiFetch('/auth/login', {
                method: 'POST',
                body: JSON.stringify({ identifier, password })
            });

            setToken(res.token);
            setCurrentUser(res.user);
            showToast(`Welcome back, ${res.user.name}!`, 'success');

            setTimeout(() => {
                redirectByRole(res.user.role);
            }, 1000);

        } catch (err) {
            showToast(err.message || 'Login failed. Please check your credentials.', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    });
}

// ==========================================
// 2. REGISTRATION FORM HANDLER
// ==========================================
function initRegisterForm() {
    const regForm = document.getElementById('register-form');
    if (!regForm) return;

    // Location detection button
    const detectLocBtn = document.getElementById('btn-detect-location');
    if (detectLocBtn) {
        detectLocBtn.addEventListener('click', () => {
            if (!navigator.geolocation) {
                showToast('Geolocation is not supported by your browser.', 'error');
                return;
            }
            detectLocBtn.innerHTML = 'Detecting...';
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    const latInput = document.getElementById('reg-latitude');
                    const lonInput = document.getElementById('reg-longitude');
                    if (latInput) latInput.value = pos.coords.latitude.toFixed(6);
                    if (lonInput) lonInput.value = pos.coords.longitude.toFixed(6);
                    showToast('Coordinates detected successfully!', 'success');
                    detectLocBtn.innerHTML = 'Location Detected ✓';
                },
                (err) => {
                    showToast('Unable to retrieve location: ' + err.message, 'error');
                    detectLocBtn.innerHTML = 'Detect My Location 📍';
                }
            );
        });
    }

    regForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const submitBtn = regForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;

        const roleInput = document.querySelector('input[name="role"]:checked');
        if (!roleInput) {
            showToast('Please select your role.', 'error');
            return;
        }
        const role = roleInput.value;

        const name = document.getElementById('reg-name').value.trim();
        const phone = document.getElementById('reg-phone').value.trim();
        const email = document.getElementById('reg-email').value.trim();
        const password = document.getElementById('reg-password').value;

        const payload = {
            role,
            name,
            phone,
            email,
            password
        };

        // Role-specific fields
        if (role === 'farmer') {
            payload.farm_name = document.getElementById('reg-farm-name')?.value.trim() || `${name}'s Farm`;
            payload.village = document.getElementById('reg-village')?.value.trim() || '';
            payload.district = document.getElementById('reg-district')?.value.trim() || '';
            payload.state = document.getElementById('reg-state')?.value.trim() || '';
            payload.farm_size = parseFloat(document.getElementById('reg-farm-size')?.value) || null;
            payload.latitude = parseFloat(document.getElementById('reg-latitude')?.value) || null;
            payload.longitude = parseFloat(document.getElementById('reg-longitude')?.value) || null;
            payload.address = document.getElementById('reg-address')?.value.trim() || '';
        } else if (['consumer', 'restaurant', 'retailer'].includes(role)) {
            payload.business_name = document.getElementById('reg-business-name')?.value.trim() || (role === 'consumer' ? name : `${name} Business`);
            payload.village = document.getElementById('reg-village')?.value.trim() || '';
            payload.district = document.getElementById('reg-district')?.value.trim() || '';
            payload.latitude = parseFloat(document.getElementById('reg-latitude')?.value) || null;
            payload.longitude = parseFloat(document.getElementById('reg-longitude')?.value) || null;
            payload.address = document.getElementById('reg-address')?.value.trim() || '';
        }

        try {
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Creating Account...';

            const res = await apiFetch('/auth/register', {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            setToken(res.token);
            setCurrentUser(res.user);
            showToast('Registration successful! Redirecting...', 'success');

            setTimeout(() => {
                redirectByRole(res.user.role);
            }, 1200);

        } catch (err) {
            showToast(err.message || 'Registration failed.', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    });
}

// ==========================================
// 3. DYNAMIC ROLE FIELD SWITCHER
// ==========================================
function initRoleSwitcher() {
    const roleRadios = document.querySelectorAll('input[name="role"]');
    if (!roleRadios.length) return;

    const farmerFields = document.getElementById('farmer-specific-fields');
    const buyerFields = document.getElementById('buyer-specific-fields');

    function updateFields() {
        const selected = document.querySelector('input[name="role"]:checked')?.value;
        if (!selected) return;

        if (farmerFields) {
            farmerFields.style.display = (selected === 'farmer') ? 'block' : 'none';
        }
        if (buyerFields) {
            buyerFields.style.display = ['consumer', 'restaurant', 'retailer'].includes(selected) ? 'block' : 'none';
        }
    }

    roleRadios.forEach(radio => {
        radio.addEventListener('change', updateFields);
    });

    updateFields();
}

// ==========================================
// 4. QUICK DEMO ACCOUNT FILLER
// ==========================================
function fillDemoLogin(role) {
    const idInput = document.getElementById('login-identifier');
    const pwdInput = document.getElementById('login-password');
    if (!idInput || !pwdInput) return;

    const demoMap = {
        farmer: { id: 'farmer@demo.com', pwd: 'Password@123' },
        consumer: { id: 'consumer@demo.com', pwd: 'Password@123' },
        restaurant: { id: 'restaurant@demo.com', pwd: 'Password@123' },
        retailer: { id: 'retailer@demo.com', pwd: 'Password@123' },
        hub: { id: 'hub@demo.com', pwd: 'Password@123' },
        delivery: { id: 'delivery@demo.com', pwd: 'Password@123' },
        admin: { id: 'admin@demo.com', pwd: 'Password@123' }
    };

    if (demoMap[role]) {
        idInput.value = demoMap[role].id;
        pwdInput.value = demoMap[role].pwd;
        showToast(`Filled credentials for ${role.toUpperCase()}`, 'info');
    }
}

// ==========================================
// 5. ROLE ROUTING
// ==========================================
function redirectByRole(role) {
    switch (role) {
        case 'farmer':
            window.location.href = '/farmer.html';
            break;
        case 'consumer':
            window.location.href = '/consumer.html';
            break;
        case 'restaurant':
            window.location.href = '/restaurant.html';
            break;
        case 'retailer':
            window.location.href = '/retailer.html';
            break;
        case 'hub_operator':
            window.location.href = '/hub.html';
            break;
        case 'admin':
            window.location.href = '/admin.html';
            break;
        case 'delivery_partner':
            window.location.href = '/delivery.html';
            break;
        default:
            window.location.href = '/index.html';
    }
}
