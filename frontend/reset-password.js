/** frontend/reset-password.js */
(async () => {
  const params = new URLSearchParams(window.location.search);
  const token  = params.get('token');

  const viewForm    = document.getElementById('viewForm');
  const viewSuccess = document.getElementById('viewSuccess');
  const viewInvalid = document.getElementById('viewInvalid');

  if (!token) {
    viewForm.style.display    = 'none';
    viewInvalid.style.display = 'block';
    return;
  }

  const form      = document.getElementById('resetForm');
  const alertEl   = document.getElementById('alert');
  const passEl    = document.getElementById('password');
  const confirmEl = document.getElementById('confirm');
  const passErr   = document.getElementById('passwordError');
  const confErr   = document.getElementById('confirmError');
  const submitBtn = document.getElementById('submitBtn');
  const pwStrength     = document.getElementById('pwStrength');
  const pwStrengthFill = document.getElementById('pwStrengthFill');
  const pwStrengthLbl  = document.getElementById('pwStrengthLabel');

  window.authUI.setupPasswordToggle('password', 'pwToggle');

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
  confirmEl.addEventListener('input', () => window.authUI.clearFieldError(confirmEl, confErr));

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    window.authUI.hideAlert(alertEl);

    const password = passEl.value;
    const confirm  = confirmEl.value;
    let valid = true;

    if (password.length < 8) {
      window.authUI.showFieldError(passEl, passErr, 'Password must be at least 8 characters.');
      valid = false;
    } else if (!/\d/.test(password)) {
      window.authUI.showFieldError(passEl, passErr, 'Password must include at least one number.');
      valid = false;
    }
    if (password !== confirm) {
      window.authUI.showFieldError(confirmEl, confErr, 'Passwords do not match.');
      valid = false;
    }
    if (!valid) return;

    window.authUI.setLoading(submitBtn, true);

    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      });

      if (res.ok) {
        viewForm.style.display    = 'none';
        viewSuccess.style.display = 'block';
      } else {
        const data = await res.json();
        if (res.status === 400) {
          viewForm.style.display    = 'none';
          viewInvalid.style.display = 'block';
        } else {
          window.authUI.showAlert(alertEl, data.detail || 'Reset failed. Please try again.', 'error');
        }
      }
    } catch {
      window.authUI.showAlert(alertEl, 'Connection error. Please try again.', 'error');
    } finally {
      window.authUI.setLoading(submitBtn, false);
    }
  });
})();
