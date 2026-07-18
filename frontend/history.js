/**
 * frontend/history.js
 *
 * Review History module — slide-over drawer with stats, entry list,
 * and restore-to-review functionality.
 *
 * Public API (called by app.js tab switcher):
 *   openHistoryDrawer()   — open the drawer and refresh data
 *   closeHistoryDrawer()  — close the drawer
 *
 * Internal flows:
 *   loadHistory()         — GET /api/history → render list
 *   loadStats()           — GET /api/history/stats → render stats bar
 *   openEntry(id)         — GET /api/history/:id → restore review into results panel
 *   deleteEntry(id)       — DELETE /api/history/:id → remove from list
 */

'use strict';

const HISTORY_API = '/api/history';

/* ── Drawer state ─────────────────────────────────────────────────────────── */
let _drawerOpen   = false;
let _historyCache = [];   // HistorySummary[]

/* ── Open / Close ─────────────────────────────────────────────────────────── */
function openHistoryDrawer() {
  document.getElementById('historyDrawer')?.classList.add('open');
  document.getElementById('historyBackdrop')?.classList.add('visible');
  document.getElementById('tab-history')?.classList.add('active');
  document.getElementById('tab-history')?.setAttribute('aria-selected', 'true');
  _drawerOpen = true;
  loadHistory();
  loadStats();
}

function closeHistoryDrawer() {
  document.getElementById('historyDrawer')?.classList.remove('open');
  document.getElementById('historyBackdrop')?.classList.remove('visible');
  document.getElementById('tab-history')?.classList.remove('active');
  document.getElementById('tab-history')?.setAttribute('aria-selected', 'false');
  _drawerOpen = false;
}

/* ── Stats bar ────────────────────────────────────────────────────────────── */
async function loadStats() {
  try {
    const res   = await fetch(`${HISTORY_API}/stats`);
    if (!res.ok) return;
    const stats = await res.json();

    _setText('hstatTotal',      stats.total_reviews);
    _setText('hstatAvg',        stats.avg_score_overall ? `${Math.round(stats.avg_score_overall)}` : '—');
    _setText('hstatApproved',   stats.approved_count);
    _setText('hstatViolations', stats.total_violations);
    _setText('hstatWeek',       stats.reviews_last_7_days);

    const hotspot = document.getElementById('historyHotspot');
    if (stats.most_violated_category && hotspot) {
      document.getElementById('historyHotspotCat').textContent =
        _formatCategory(stats.most_violated_category);
      hotspot.style.display = 'flex';
    }
  } catch (_) { /* stats are non-critical */ }
}

/* ── List ─────────────────────────────────────────────────────────────────── */
async function loadHistory() {
  const list = document.getElementById('historyList');
  if (!list) return;

  // Show skeleton
  list.innerHTML = `
    <div class="hist-skeleton">
      ${Array.from({length: 4}).map(() => '<div class="hist-skel-card"></div>').join('')}
    </div>`;

  try {
    const res = await fetch(`${HISTORY_API}?limit=50`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _historyCache = await res.json();
    _renderList(_historyCache);
  } catch (err) {
    list.innerHTML = `<div class="hist-error">Failed to load history: ${err.message}</div>`;
  }
}

function _renderList(entries) {
  const list = document.getElementById('historyList');
  if (!list) return;

  if (!entries.length) {
    list.innerHTML = `
      <div class="history-empty" id="historyEmptyState">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="20" stroke="rgba(99,102,241,0.3)" stroke-width="1.5"/>
          <path d="M24 14v10l5 5" stroke="rgba(99,102,241,0.5)" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <p>No reviews yet</p>
        <span>Run a code review — it will appear here automatically</span>
      </div>`;
    return;
  }

  list.innerHTML = entries.map(e => _buildEntryCard(e)).join('');
}

function _buildEntryCard(e) {
  const scoreClass = e.score_overall >= 80 ? 'score-good'
                   : e.score_overall >= 60 ? 'score-ok'
                   : 'score-bad';
  const date = _relativeDate(e.reviewed_at);
  const lang = e.language ? `<span class="hist-lang-badge">${_esc(e.language)}</span>` : '';
  const badge = e.approved
    ? '<span class="hist-status-badge approved">✓ Approved</span>'
    : e.violation_count > 0
      ? `<span class="hist-status-badge changes">${e.violation_count} violation${e.violation_count > 1 ? 's' : ''}</span>`
      : '<span class="hist-status-badge clean">Clean</span>';

  return `
<div class="hist-entry-card" data-id="${_esc(e.id)}" role="button" tabindex="0" aria-label="Review ${_esc(e.pr_title)}">
  <div class="hist-entry-main" onclick="openHistoryEntry('${_esc(e.id)}')">
    <div class="hist-entry-score ${scoreClass}">
      <span class="hist-score-num">${e.score_overall}</span>
      <span class="hist-score-lbl">score</span>
    </div>
    <div class="hist-entry-body">
      <div class="hist-entry-title">${_esc(e.pr_title)}</div>
      <div class="hist-entry-meta">
        <span class="hist-date">${date}</span>
        ${lang}
        ${badge}
      </div>
      ${e.diff_preview ? `<div class="hist-diff-preview">${_esc(e.diff_preview.slice(0,80))}…</div>` : ''}
    </div>
  </div>
  <button class="hist-delete-btn" onclick="event.stopPropagation(); deleteHistoryEntry('${_esc(e.id)}')"
          aria-label="Delete this review" title="Delete">
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path d="M2 4h10M5 4V2.5h4V4M5.5 6v4M8.5 6v4M3 4l.8 7h6.4l.8-7" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </button>
</div>`;
}

/* ── Open entry → restore review ──────────────────────────────────────────── */
async function openHistoryEntry(id) {
  // Highlight the card as loading
  const card = document.querySelector(`.hist-entry-card[data-id="${id}"]`);
  card?.classList.add('loading');

  try {
    const res = await fetch(`${HISTORY_API}/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const entry = await res.json();

    // Reconstruct a ReviewResult-compatible object
    const reviewResult = {
      review_id:          entry.id,
      pr_title:           entry.pr_title,
      reviewed_at:        entry.reviewed_at,
      model_used:         entry.model_used,
      active_rules_count: entry.active_rules,
      scores: {
        overall:             entry.score_overall,
        security:            entry.score_security,
        architecture:        entry.score_architecture,
        performance:         entry.score_performance,
        maintainability:     entry.score_maintainability,
        readability:         entry.score_readability,
        testing:             entry.score_testing,
        production_readiness: entry.score_production,
      },
      violations:     entry.violations,
      summary:        entry.summary,
      approved:       entry.approved,
      approved_reason: entry.approved_reason,
    };

    // Store in global so Export works
    window._lastCRResult = reviewResult;

    // Close the drawer and switch to Code Review tab to show results
    closeHistoryDrawer();

    // Switch to Code Review mode (uses existing app.js function)
    if (typeof switchMode === 'function') {
      switchMode('codereview');
    }

    // Trigger result rendering (defined in rules_manager.js)
    if (typeof renderCodeReviewResult === 'function') {
      renderCodeReviewResult(reviewResult);
    }

    // Show a toast
    _showToast(`Loaded: ${entry.pr_title}`);

  } catch (err) {
    _showToast(`Failed to load review: ${err.message}`, 'error');
  } finally {
    card?.classList.remove('loading');
  }
}

/* ── Delete entry ─────────────────────────────────────────────────────────── */
async function deleteHistoryEntry(id) {
  if (!confirm('Delete this review from history? This cannot be undone.')) return;

  try {
    const res = await fetch(`${HISTORY_API}/${id}`, { method: 'DELETE' });
    if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);

    // Optimistic remove from cache + re-render
    _historyCache = _historyCache.filter(e => e.id !== id);
    _renderList(_historyCache);

    // Refresh stats
    loadStats();
    _showToast('Review deleted from history');
  } catch (err) {
    _showToast(`Delete failed: ${err.message}`, 'error');
  }
}

/* ── Toast notification ───────────────────────────────────────────────────── */
function _showToast(msg, type = 'success') {
  // Reuse existing toast if available, else create one
  let toast = document.getElementById('historyToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'historyToast';
    toast.className = 'history-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className   = `history-toast ${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3200);
}

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function _setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '—';
}

function _esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function _formatCategory(cat) {
  return (cat || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function _relativeDate(iso) {
  try {
    const d    = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000; // seconds
    if (diff < 60)    return 'just now';
    if (diff < 3600)  return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff/86400)}d ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch (_) { return iso; }
}

/* ── Init ─────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Close button
  document.getElementById('historyCloseBtn')?.addEventListener('click', closeHistoryDrawer);

  // Backdrop click closes drawer
  document.getElementById('historyBackdrop')?.addEventListener('click', closeHistoryDrawer);

  // Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _drawerOpen) closeHistoryDrawer();
  });
});

// Expose for HTML onclick and app.js tab switcher
window.openHistoryDrawer  = openHistoryDrawer;
window.closeHistoryDrawer = closeHistoryDrawer;
window.openHistoryEntry   = openHistoryEntry;
window.deleteHistoryEntry = deleteHistoryEntry;
window._showHistoryToast  = _showToast;   // used by rules_manager.js after code review
