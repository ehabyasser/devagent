/** frontend/forgot-password.js */
(async () => {
  await window.devauth.requireGuest('/');

  const form      = document.getElementById('forgotForm');
  const alertEl   = document.getElementById('alert');
  const emailEl   = document.getElementById('email');
  const emailErr  = document.getElementById('emailError');
  const submitBtn = document.getElementById('submitBtn');
  const viewForm  = document.getElementById('viewForm');
  const viewSent  = document.getElementById('viewSent');

  emailEl.addEventListener('input', () => {
    window.authUI.clearFieldError(emailEl, emailErr);
    window.authUI.hideAlert(alertEl);
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = emailEl.value.trim();

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      window.authUI.showFieldError(emailEl, emailErr, 'Please enter a valid email address.');
      return;
    }

    window.authUI.setLoading(submitBtn, true);

    try {
      await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      // Always show "sent" view regardless of response (prevent email enumeration)
      viewForm.style.display = 'none';
      viewSent.style.display = 'block';
    } catch {
      window.authUI.showAlert(alertEl, 'Connection error. Please try again.', 'error');
    } finally {
      window.authUI.setLoading(submitBtn, false);
    }
  });
})();
