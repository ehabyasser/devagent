/**
 * frontend/auth.js
 *
 * Shared authentication module — used by all pages (auth + main app).
 *
 * Responsibilities:
 *   - Token storage (sessionStorage)
 *   - Silent token refresh via refresh cookie
 *   - requireAuth()  — redirects to /login.html if not authenticated
 *   - fetchWithAuth() — wraps fetch with Authorization header, auto-refreshes on 401
 *   - logout()        — calls /api/auth/logout, clears state, redirects
 *
 * The access token is stored in sessionStorage (cleared on tab close).
 * The refresh token is an HttpOnly cookie (never accessible to JS).
 */

const DA_TOKEN_KEY  = 'da_access_token';
const DA_USER_KEY   = 'da_user';
const DA_EXPIRY_KEY = 'da_token_expiry';

const _auth = {
  // ── Token storage ──────────────────────────────────────────────────────────

  getToken() {
    return sessionStorage.getItem(DA_TOKEN_KEY);
  },

  setToken(token, expiresInSeconds) {
    sessionStorage.setItem(DA_TOKEN_KEY, token);
    const expiry = Date.now() + (expiresInSeconds * 1000);
    sessionStorage.setItem(DA_EXPIRY_KEY, String(expiry));
  },

  clearToken() {
    sessionStorage.removeItem(DA_TOKEN_KEY);
    sessionStorage.removeItem(DA_EXPIRY_KEY);
    sessionStorage.removeItem(DA_USER_KEY);
  },

  isTokenExpired() {
    const expiry = sessionStorage.getItem(DA_EXPIRY_KEY);
    if (!expiry) return true;
    // Consider expired 30 seconds early to prevent edge-case 401s
    return Date.now() > (parseInt(expiry, 10) - 30_000);
  },

  // ── User profile cache ─────────────────────────────────────────────────────

  getUser() {
    const raw = sessionStorage.getItem(DA_USER_KEY);
    try { return raw ? JSON.parse(raw) : null; } catch { return null; }
  },

  setUser(user) {
    sessionStorage.setItem(DA_USER_KEY, JSON.stringify(user));
  },

  // ── Silent token refresh ───────────────────────────────────────────────────

  _refreshPromise: null,

  async silentRefresh() {
    // Deduplicate concurrent refresh calls
    if (this._refreshPromise) return this._refreshPromise;

    this._refreshPromise = (async () => {
      try {
        const res = await fetch('/api/auth/refresh', {
          method: 'POST',
          credentials: 'include',   // send the HttpOnly refresh cookie
        });
        if (!res.ok) return false;
        const data = await res.json();
        this.setToken(data.access_token, data.expires_in);
        return true;
      } catch {
        return false;
      } finally {
        this._refreshPromise = null;
      }
    })();

    return this._refreshPromise;
  },

  // ── requireAuth() — Call at top of every protected page ───────────────────
  // Returns true if the user is (now) authenticated, false if redirect happened.

  async requireAuth(redirectTo = '/login.html') {
    const token = this.getToken();

    if (!token) {
      // No token at all — try silent refresh
      const ok = await this.silentRefresh();
      if (!ok) {
        window.location.replace(redirectTo);
        return false;
      }
      return true;
    }

    if (this.isTokenExpired()) {
      const ok = await this.silentRefresh();
      if (!ok) {
        this.clearToken();
        window.location.replace(redirectTo);
        return false;
      }
    }

    return true;
  },

  // ── requireGuest() — redirect authenticated users away from auth pages ─────

  async requireGuest(redirectTo = '/') {
    const token = this.getToken();
    if (token && !this.isTokenExpired()) {
      window.location.replace(redirectTo);
      return false;
    }
    // Try silent refresh — if it works, user is still logged in
    if (await this.silentRefresh()) {
      window.location.replace(redirectTo);
      return false;
    }
    return true;
  },

  // ── fetchWithAuth() — fetch wrapper with automatic token refresh ───────────

  async fetchWithAuth(url, options = {}) {
    const doRequest = async () => {
      const token = this.getToken();
      const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      };
      return fetch(url, { ...options, headers, credentials: 'include' });
    };

    // Proactively refresh if token is close to expiry
    if (this.isTokenExpired()) {
      await this.silentRefresh();
    }

    let res = await doRequest();

    // If 401, try one refresh + retry
    if (res.status === 401) {
      const refreshed = await this.silentRefresh();
      if (refreshed) {
        res = await doRequest();
      } else {
        this.clearToken();
        window.location.replace('/login.html');
        return res;
      }
    }

    return res;
  },

  // ── Load and cache user profile ────────────────────────────────────────────

  async loadUser() {
    const cached = this.getUser();
    if (cached) return cached;

    try {
      const res = await this.fetchWithAuth('/api/auth/me');
      if (!res.ok) return null;
      const user = await res.json();
      this.setUser(user);
      return user;
    } catch {
      return null;
    }
  },

  // ── logout() ───────────────────────────────────────────────────────────────

  async logout() {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
    } catch { /* best effort */ }
    this.clearToken();
    window.location.replace('/login.html');
  },
};

// Expose globally as window.devauth
window.devauth = _auth;

// ── DOM helpers shared across auth pages ──────────────────────────────────────

window.authUI = {
  showAlert(el, message, type = 'error') {
    if (!el) return;
    el.textContent = message;
    el.className = `auth-alert ${type} visible`;
  },

  hideAlert(el) {
    if (!el) return;
    el.className = 'auth-alert';
  },

  setLoading(btn, loading) {
    if (!btn) return;
    btn.classList.toggle('loading', loading);
    btn.disabled = loading;
  },

  showFieldError(inputEl, errorEl, message) {
    if (inputEl) inputEl.classList.add('error');
    if (errorEl) { errorEl.textContent = message; errorEl.classList.add('visible'); }
  },

  clearFieldError(inputEl, errorEl) {
    if (inputEl) inputEl.classList.remove('error');
    if (errorEl) { errorEl.textContent = ''; errorEl.classList.remove('visible'); }
  },

  passwordStrength(password) {
    let score = 0;
    if (password.length >= 8)  score++;
    if (password.length >= 12) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    const levels = [
      { label: 'Very weak', color: '#ef4444', pct: 20 },
      { label: 'Weak',      color: '#f97316', pct: 40 },
      { label: 'Fair',      color: '#eab308', pct: 60 },
      { label: 'Good',      color: '#22c55e', pct: 80 },
      { label: 'Strong',    color: '#10b981', pct: 100 },
    ];
    return { score, ...levels[Math.min(score, 4)] };
  },

  setupPasswordToggle(inputId, toggleId) {
    const input  = document.getElementById(inputId);
    const toggle = document.getElementById(toggleId);
    if (!input || !toggle) return;
    toggle.addEventListener('click', () => {
      const isText = input.type === 'text';
      input.type = isText ? 'password' : 'text';
      toggle.innerHTML = isText
        ? `<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`
        : `<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
    });
  },
};
