/**
 * frontend/signup.js — Create account page logic
 */
(async () => {
  await window.devauth.requireGuest('/');

  const form      = document.getElementById('signupForm');
  const alertEl   = document.getElementById('alert');
  const nameEl    = document.getElementById('fullName');
  const emailEl   = document.getElementById('email');
  const passEl    = document.getElementById('password');
  const nameErr   = document.getElementById('nameError');
  const emailErr  = document.getElementById('emailError');
  const passErr   = document.getElementById('passwordError');
  const submitBtn = document.getElementById('submitBtn');
  const pwStrength     = document.getElementById('pwStrength');
  const pwStrengthFill = document.getElementById('pwStrengthFill');
  const pwStrengthLbl  = document.getElementById('pwStrengthLabel');

  window.authUI.setupPasswordToggle('password', 'pwToggle');

  // Password strength meter
  passEl.addEventListener('input', () => {
    window.authUI.clearFieldError(passEl, passErr);
    const val = passEl.value;
    if (!val) { pwStrength.classList.remove('visible'); return; }
    pwStrength.classList.add('visible');
    const { label, color, pct } = window.authUI.passwordStrength(val);
    pwStrengthFill.style.width = pct + '%';
    pwStrengthFill.style.background = color;
    pwStrengthLbl.textContent = label;
  });

  // Clear errors on input
  [emailEl, nameEl].forEach(el => {
    el.addEventListener('input', () => {
      window.authUI.clearFieldError(el, el === emailEl ? emailErr : nameErr);
      window.authUI.hideAlert(alertEl);
    });
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    window.authUI.hideAlert(alertEl);

    const fullName = nameEl.value.trim();
    const email    = emailEl.value.trim();
    const password = passEl.value;

    let valid = true;

    if (!email) {
      window.authUI.showFieldError(emailEl, emailErr, 'Email is required.');
      valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      window.authUI.showFieldError(emailEl, emailErr, 'Please enter a valid email address.');
      valid = false;
    }

    if (!password) {
      window.authUI.showFieldError(passEl, passErr, 'Password is required.');
      valid = false;
    } else if (password.length < 8) {
      window.authUI.showFieldError(passEl, passErr, 'Password must be at least 8 characters.');
      valid = false;
    } else if (!/\d/.test(password)) {
      window.authUI.showFieldError(passEl, passErr, 'Password must include at least one number.');
      valid = false;
    }

    if (!valid) return;

    window.authUI.setLoading(submitBtn, true);

    try {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, full_name: fullName }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 409) {
          window.authUI.showFieldError(emailEl, emailErr,
            'An account with this email already exists.');
        } else {
          const detail = data.detail;
          if (Array.isArray(detail)) {
            // Pydantic validation errors
            detail.forEach(err => {
              const field = err.loc?.[err.loc.length - 1];
              const msg = err.msg || 'Invalid value.';
              if (field === 'password') window.authUI.showFieldError(passEl, passErr, msg);
              else if (field === 'email') window.authUI.showFieldError(emailEl, emailErr, msg);
              else window.authUI.showAlert(alertEl, msg, 'error');
            });
          } else {
            window.authUI.showAlert(alertEl, detail || 'Sign up failed. Please try again.', 'error');
          }
        }
        return;
      }

      // Success — show message, redirect to login
      window.authUI.showAlert(alertEl, data.message, 'success');

      // Wait 2 seconds then redirect to login (pre-fill email for convenience)
      setTimeout(() => {
        window.location.replace(`/login.html?email=${encodeURIComponent(email)}`);
      }, 2000);

    } catch (err) {
      window.authUI.showAlert(alertEl, 'Connection error. Please try again.', 'error');
    } finally {
      window.authUI.setLoading(submitBtn, false);
    }
  });
})();
