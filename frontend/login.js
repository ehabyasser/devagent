/**
 * frontend/login.js — Sign in page logic
 */
(async () => {
  // If already authenticated, send to app
  await window.devauth.requireGuest('/');

  const form     = document.getElementById('loginForm');
  const alertEl  = document.getElementById('alert');
  const emailEl  = document.getElementById('email');
  const passEl   = document.getElementById('password');
  const emailErr = document.getElementById('emailError');
  const passErr  = document.getElementById('passwordError');
  const submitBtn = document.getElementById('submitBtn');

  window.authUI.setupPasswordToggle('password', 'pwToggle');

  // Clear errors on input
  emailEl.addEventListener('input', () => {
    window.authUI.clearFieldError(emailEl, emailErr);
    window.authUI.hideAlert(alertEl);
  });
  passEl.addEventListener('input', () => {
    window.authUI.clearFieldError(passEl, passErr);
    window.authUI.hideAlert(alertEl);
  });

  // Pre-fill email if coming from signup
  const params = new URLSearchParams(window.location.search);
  if (params.get('email')) {
    emailEl.value = decodeURIComponent(params.get('email'));
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Client-side validation
    let valid = true;
    const email = emailEl.value.trim();
    const password = passEl.value;

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
    }

    if (!valid) return;

    window.authUI.setLoading(submitBtn, true);
    window.authUI.hideAlert(alertEl);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',   // important: allows the refresh cookie to be set
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        const msg = data.detail || 'Sign in failed. Please try again.';

        if (res.status === 403 && msg.includes('verify')) {
          window.authUI.showAlert(alertEl,
            `${msg} <a href="/verify-email.html" style="color:#c4b5fd;">Resend verification email</a>`,
            'info'
          );
          alertEl.innerHTML = `
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="flex-shrink:0;margin-top:1px">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>${msg} <a href="/verify-email.html?email=${encodeURIComponent(email)}" style="color:#c4b5fd;">Resend verification email →</a></span>
          `;
          alertEl.className = 'auth-alert info visible';
        } else {
          window.authUI.showAlert(alertEl, msg, 'error');
        }
        return;
      }

      // Success — store access token and user
      window.devauth.setToken(data.access_token, data.expires_in);
      window.devauth.setUser(data.user);

      // Redirect to app (or the page they were trying to reach)
      const next = params.get('next') || '/';
      window.location.replace(next);

    } catch (err) {
      window.authUI.showAlert(alertEl, 'Connection error. Please check your internet and try again.', 'error');
    } finally {
      window.authUI.setLoading(submitBtn, false);
    }
  });
})();
