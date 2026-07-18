/**
 * frontend/verify-email.js
 */
(async () => {
  const params = new URLSearchParams(window.location.search);
  const token  = params.get('token');
  const email  = params.get('email');   // pre-fill resend form

  const stateLoading = document.getElementById('stateLoading');
  const stateSuccess = document.getElementById('stateSuccess');
  const stateError   = document.getElementById('stateError');
  const errorMsg     = document.getElementById('errorMessage');
  const resendEmail  = document.getElementById('resendEmail');
  const resendBtn    = document.getElementById('resendBtn');
  const resendAlert  = document.getElementById('resendAlert');

  if (email) resendEmail.value = email;

  function show(state) {
    stateLoading.style.display = state === 'loading' ? 'block' : 'none';
    stateSuccess.style.display = state === 'success' ? 'block' : 'none';
    stateError.style.display   = state === 'error'   ? 'block' : 'none';
  }

  // If no token in URL — show resend form immediately
  if (!token) {
    errorMsg.textContent = 'No verification token found. Please use the link from your email or request a new one.';
    show('error');
    return;
  }

  // Verify the token
  try {
    const res = await fetch('/api/auth/verify-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });

    if (res.ok) {
      show('success');
      // Auto-redirect to login after 3 seconds
      setTimeout(() => window.location.replace('/login.html'), 3000);
    } else {
      const data = await res.json();
      errorMsg.textContent = data.detail || 'This verification link is invalid or has expired.';
      show('error');
    }
  } catch {
    errorMsg.textContent = 'Connection error. Please try again.';
    show('error');
  }

  // Resend button
  resendBtn.addEventListener('click', async () => {
    const emailVal = resendEmail.value.trim();
    if (!emailVal) {
      window.authUI.showAlert(resendAlert, 'Please enter your email address.', 'error');
      return;
    }

    window.authUI.setLoading(resendBtn, true);
    window.authUI.hideAlert(resendAlert);

    try {
      await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailVal }),
      });
      // Always show success message (backend never reveals if email exists)
      window.authUI.showAlert(resendAlert,
        'If your email is registered and unverified, a new link has been sent. Check your inbox.',
        'success'
      );
    } catch {
      window.authUI.showAlert(resendAlert, 'Connection error. Please try again.', 'error');
    } finally {
      window.authUI.setLoading(resendBtn, false);
    }
  });
})();
