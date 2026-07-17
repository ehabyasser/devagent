/**
 * app.js — DevAgent Frontend
 *
 * 1. Mode switching (Test Gen / PR Review)
 * 2. Agent loop stage visualiser
 * 3. FastAPI endpoint calls
 * 4. Rich result rendering
 * 5. Example chips for offline demo
 * 6. Copy-to-clipboard, keyboard shortcuts
 */
'use strict';

/* ── Config ──────────────────────────────────────────────────────────────── */
/* Use relative URLs — works on localhost AND on Render/any deployment */
const API_BASE = '';
const ENDPOINTS = {
  testGen:  API_BASE + '/api/agent/test-gen',
  prReview: API_BASE + '/api/agent/pr-review',
  health:   API_BASE + '/health',
};

/* ── State ───────────────────────────────────────────────────────────────── */
let currentMode   = 'testgen';
let lastTestSuite = null;
let lastPRReview  = null;
let activeStageFn = null;

/* ── DOM refs ────────────────────────────────────────────────────────────── */
const getEl = (id) => document.getElementById(id);

const DOM = {
  tabTestGen:      getEl('tab-testgen'),
  panelTestGen:    getEl('panel-testgen'),
  ticketId:        getEl('ticketId'),
  featureDesc:     getEl('featureDescription'),
  runTestGen:      getEl('runTestGen'),
  copyTestSuite:   getEl('copyTestSuite'),
  emptyState:      getEl('emptyState'),
  loadingState:    getEl('loadingState'),
  loadingMessage:  getEl('loadingMessage'),
  testSuiteResult: getEl('testSuiteResult'),
  errorState:      getEl('errorState'),
  errorMessage:    getEl('errorMessage'),
  testSuiteMeta:   getEl('testSuiteMeta'),
  testSuiteStats:  getEl('testSuiteStats'),
  testCasesList:   getEl('testCasesList'),
  coverageNotes:   getEl('coverageNotes'),
  statusDot:       getEl('statusDot'),
  statusText:      getEl('statusText'),
};

/* ── Agent loop stages ───────────────────────────────────────────────────── */
const STAGE_ORDER = ['understand', 'plan', 'tool', 'validate', 'respond'];
const STAGE_MSGS  = {
  understand: 'Parsing your input…',
  plan:       'Planning tool calls…',
  tool:       'Running tools (Jira / diff parser / secrets)…',
  validate:   'Validating outputs…',
  respond:    'Calling LLM for response…',
};

function animateStages() {
  let idx = 0;
  clearStageAnimation();

  function advance() {
    if (idx > 0) {
      const prev = getEl('stage-' + STAGE_ORDER[idx - 1]);
      if (prev) { prev.classList.remove('active'); prev.classList.add('done'); }
    }
    if (idx < STAGE_ORDER.length) {
      const el = getEl('stage-' + STAGE_ORDER[idx]);
      if (el) el.classList.add('active');
      DOM.loadingMessage.textContent = STAGE_MSGS[STAGE_ORDER[idx]] || 'Processing…';
      idx++;
      const delays = [600, 700, 2200, 600, 400];
      activeStageFn = setTimeout(advance, delays[idx - 1] !== undefined ? delays[idx - 1] : 800);
    }
  }
  advance();
}

function clearStageAnimation() {
  if (activeStageFn) { clearTimeout(activeStageFn); activeStageFn = null; }
  STAGE_ORDER.forEach(function(s) {
    const el = getEl('stage-' + s);
    if (el) { el.classList.remove('active', 'done'); }
  });
}

/* ── UI state machine ───────────────────────────────────────────────────────────── */
function showState(state) {
  var states = ['emptyState', 'loadingState', 'testSuiteResult', 'errorState', 'panel-codereview-output'];
  states.forEach(function(s) {
    var el = getEl(s);
    if (el) el.classList.add('hidden');
  });
  if (state && getEl(state)) getEl(state).classList.remove('hidden');
}

function setLoading(on, btn) {
  if (!btn) return;
  btn.disabled = on;
  var text = btn.querySelector('.btn-text');
  if (text) {
    if (on) {
      text.textContent = btn === DOM.runTestGen ? 'Generating…' : 'Reviewing…';
    } else {
      text.textContent = btn === DOM.runTestGen ? 'Generate Test Suite' : 'Review Pull Request';
    }
  }
  if (on) btn.classList.add('loading');
  else btn.classList.remove('loading');
}

/* ── Health check ────────────────────────────────────────────────────────── */
async function checkHealth() {
  var ctrl  = new AbortController();
  var timer = setTimeout(function() { ctrl.abort(); }, 5000);
  try {
    var r = await fetch('/health', { method: 'GET', signal: ctrl.signal });
    clearTimeout(timer);
    var dot  = document.getElementById('statusDot');
    var text = document.getElementById('statusText');
    if (r.ok) {
      if (dot)  dot.className   = 'status-dot online';
      if (text) text.textContent = 'Backend online';
    } else {
      throw new Error('HTTP ' + r.status);
    }
  } catch (err) {
    clearTimeout(timer);
    var dot  = document.getElementById('statusDot');
    var text = document.getElementById('statusText');
    if (dot)  dot.className   = 'status-dot error';
    if (text) text.textContent = 'Backend offline';
    if (err.name !== 'AbortError') console.warn('[DevAgent] Health check:', err.message);
  }
}


/* ── Mode switch ─────────────────────────────────────────────────────────── */
function switchMode(mode) {
  currentMode = mode;

  // All tabs
  document.querySelectorAll('.mode-tab').forEach(function(t) {
    var isActive = t.dataset.mode === mode;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', String(isActive));
  });

  // Left input panels
  ['testgen','codereview'].forEach(function(m) {
    var p = document.getElementById('panel-' + m);
    if (p) p.classList.toggle('hidden', mode !== m);
  });

  // Right output area
  var mainOut = document.querySelector('.output-panel[aria-label="Results"]');
  var rulesFull = document.getElementById('panel-rules-full');

  if (mode === 'rules') {
    if (mainOut) mainOut.classList.add('hidden');
    if (rulesFull) rulesFull.classList.remove('hidden');
    if (typeof loadRulesManager === 'function') loadRulesManager();
  } else {
    if (mainOut) mainOut.classList.remove('hidden');
    if (rulesFull) rulesFull.classList.add('hidden');
    clearStageAnimation();
    showState('emptyState');
    if (mode === 'codereview' && typeof loadActiveRuleCount === 'function') loadActiveRuleCount();
  }
}

document.querySelectorAll('.mode-tab').forEach(function(tab) {
  tab.addEventListener('click', function() { switchMode(tab.dataset.mode); });
});

/* ── Error display ───────────────────────────────────────────────────────── */
function showError(msg) {
  clearStageAnimation();
  DOM.errorMessage.textContent = msg;
  showState('errorState');
}

window.clearError = function() { showState('emptyState'); };

/* ── Copy JSON ───────────────────────────────────────────────────────────── */
function copyJSON(data, btn) {
  navigator.clipboard.writeText(JSON.stringify(data, null, 2)).then(function() {
    var orig = btn.textContent;
    btn.textContent = '✓ Copied!';
    setTimeout(function() { btn.textContent = orig; }, 2000);
  });
}
DOM.copyTestSuite.addEventListener('click', function() { if (lastTestSuite) copyJSON(lastTestSuite, DOM.copyTestSuite); });
DOM.copyPRReview.addEventListener('click', function()  { if (lastPRReview)  copyJSON(lastPRReview,  DOM.copyPRReview); });

/* ── Utility ─────────────────────────────────────────────────────────────── */
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function fmtTime(isoStr) {
  try {
    return new Date(isoStr).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch (_) { return isoStr || ''; }
}

/* ─────────────────────────────────────────────────────────────────────────
   RUN TEST GEN
   ─────────────────────────────────────────────────────────────────────── */
DOM.runTestGen.addEventListener('click', async function() {
  var ticketId    = DOM.ticketId.value.trim();
  var description = DOM.featureDesc.value.trim();
  if (!ticketId && !description) { showError('Enter a Jira Ticket ID or a feature description.'); return; }

  setLoading(true, DOM.runTestGen);
  showState('loadingState');
  animateStages();

  try {
    var body = {};
    if (ticketId) body.ticket_id = ticketId;
    if (description) body.description = description;

    var res = await fetch(ENDPOINTS.testGen, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    clearStageAnimation();
    STAGE_ORDER.forEach(function(s) {
      var el = getEl('stage-' + s);
      if (el) { el.classList.remove('active'); el.classList.add('done'); }
    });

    if (!res.ok) {
      var err = await res.json().catch(function() { return { detail: res.statusText }; });
      throw new Error(err.detail || 'HTTP ' + res.status);
    }

    var data = await res.json();
    lastTestSuite = data;
    renderTestSuite(data);

  } catch (err) {
    showError(err.message || 'An unexpected error occurred.');
  } finally {
    setLoading(false, DOM.runTestGen);
  }
});

/* ─────────────────────────────────────────────────────────────────────────
   RUN PR REVIEW
   ─────────────────────────────────────────────────────────────────────── */
DOM.runPRReview.addEventListener('click', async function() {
  var diff    = DOM.diffInput.value.trim();
  var prTitle = DOM.prTitle.value.trim() || 'Untitled PR';
  if (!diff) { showError('Paste a git diff to review.'); return; }

  setLoading(true, DOM.runPRReview);
  showState('loadingState');
  animateStages();

  try {
    var res = await fetch(ENDPOINTS.prReview, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pr_title: prTitle, diff: diff }),
    });

    clearStageAnimation();
    STAGE_ORDER.forEach(function(s) {
      var el = getEl('stage-' + s);
      if (el) { el.classList.remove('active'); el.classList.add('done'); }
    });

    if (!res.ok) {
      var err = await res.json().catch(function() { return { detail: res.statusText }; });
      throw new Error(err.detail || 'HTTP ' + res.status);
    }

    var data = await res.json();
    lastPRReview = data;
    renderPRReview(data);

  } catch (err) {
    showError(err.message || 'An unexpected error occurred.');
  } finally {
    setLoading(false, DOM.runPRReview);
  }
});

/* ─────────────────────────────────────────────────────────────────────────
   RENDER: TEST SUITE
   ─────────────────────────────────────────────────────────────────────── */
function renderTestSuite(suite) {
  // Clean up old filter row if any
  var oldFilter = DOM.testCasesList.parentNode.querySelector('.issue-filters');
  if (oldFilter) oldFilter.remove();

  DOM.testSuiteMeta.innerHTML =
    '<span>🎫 ' + esc(suite.ticket_id) + '</span>' +
    '<span>🤖 ' + esc(suite.model_used) + '</span>' +
    '<span>🕐 ' + fmtTime(suite.generated_at) + '</span>';

  var cats = ['happy_path', 'negative', 'boundary', 'regression'];
  var catCounts = {};
  cats.forEach(function(c) { catCounts[c] = 0; });
  (suite.cases || []).forEach(function(tc) { if (catCounts[tc.category] !== undefined) catCounts[tc.category]++; });

  var catIcons = { happy_path: '✅', negative: '❌', boundary: '⚡', regression: '🔁' };
  var statsHtml = '<div class="stat-card"><div class="stat-value">' + suite.total_cases + '</div><div class="stat-label">Total Cases</div></div>';
  cats.forEach(function(c) {
    statsHtml += '<div class="stat-card"><div class="stat-value">' + catCounts[c] + '</div><div class="stat-label">' + catIcons[c] + ' ' + c.replace('_', ' ') + '</div></div>';
  });
  DOM.testSuiteStats.innerHTML = statsHtml;

  // Category filter
  var uniqCats = Array.from(new Set((suite.cases || []).map(function(tc) { return tc.category; })));
  var filterDiv = document.createElement('div');
  filterDiv.className = 'issue-filters';
  filterDiv.style.marginBottom = '12px';
  var filterHtml = '<button class="filter-btn active" data-cat="all">All (' + suite.total_cases + ')</button>';
  uniqCats.forEach(function(c) {
    filterHtml += '<button class="filter-btn" data-cat="' + c + '">' + c.replace('_', ' ') + ' (' + catCounts[c] + ')</button>';
  });
  filterDiv.innerHTML = filterHtml;
  DOM.testCasesList.before(filterDiv);

  function renderCases(filter) {
    var cases = filter === 'all'
      ? (suite.cases || [])
      : (suite.cases || []).filter(function(tc) { return tc.category === filter; });
    DOM.testCasesList.innerHTML = cases.map(renderTestCase).join('');
    DOM.testCasesList.querySelectorAll('.test-case-header').forEach(function(h) {
      h.addEventListener('click', function() { h.closest('.test-case-card').classList.toggle('expanded'); });
    });
  }

  filterDiv.querySelectorAll('.filter-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      filterDiv.querySelectorAll('.filter-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      renderCases(btn.dataset.cat);
    });
  });
  renderCases('all');

  DOM.coverageNotes.textContent = suite.coverage_notes || '';
  if (suite.coverage_notes) DOM.coverageNotes.classList.remove('hidden');
  else DOM.coverageNotes.classList.add('hidden');

  showState('testSuiteResult');
}

function renderTestCase(tc) {
  var precHtml = '';
  if (tc.preconditions && tc.preconditions.length) {
    precHtml = '<p class="tc-section-label">Preconditions</p><ul class="tc-preconditions">' +
      tc.preconditions.map(function(p) { return '<li>' + esc(p) + '</li>'; }).join('') + '</ul>';
  }
  var stepsHtml = (tc.steps || []).map(function(s) {
    return '<li class="tc-step"><div class="tc-step-num">' + s.step_number + '</div>' +
      '<div class="tc-step-action">' + esc(s.action) + '</div>' +
      '<div class="tc-step-result">→ ' + esc(s.expected_result) + '</div></li>';
  }).join('');
  var tagsHtml = (tc.tags || []).map(function(t) { return '<span class="tc-tag">' + esc(t) + '</span>'; }).join('');

  return '<div class="test-case-card" data-id="' + esc(tc.id) + '" data-category="' + esc(tc.category) + '">' +
    '<div class="test-case-header">' +
      '<span class="test-case-id">' + esc(tc.id) + '</span>' +
      '<span class="test-case-title">' + esc(tc.title) + '</span>' +
      '<span class="category-badge ' + tc.category + '">' + tc.category.replace('_', ' ') + '</span>' +
      '<span class="priority-badge ' + tc.priority + '">' + esc(tc.priority) + '</span>' +
      '<svg class="test-case-chevron" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
        '<path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>' +
    '</div>' +
    '<div class="test-case-body">' +
      precHtml +
      '<p class="tc-section-label">Steps</p>' +
      '<ol class="tc-steps">' + stepsHtml + '</ol>' +
      '<p class="tc-section-label">Expected Outcome</p>' +
      '<div class="tc-outcome">' + esc(tc.expected_outcome) + '</div>' +
      (tagsHtml ? '<div class="tc-tags">' + tagsHtml + '</div>' : '') +
    '</div>' +
  '</div>';
}

/* ─────────────────────────────────────────────────────────────────────────
   RENDER: PR REVIEW
   ─────────────────────────────────────────────────────────────────────── */
function renderPRReview(review) {
  DOM.prReviewMeta.innerHTML =
    '<span>📄 ' + esc(review.pr_title) + '</span>' +
    '<span>🤖 ' + esc(review.model_used) + '</span>' +
    '<span>🕐 ' + fmtTime(review.reviewed_at) + '</span>';

  var recIcons  = { approve: '✅', request_changes: '🚫', comment: '💬' };
  var recLabels = { approve: 'Approve', request_changes: 'Request Changes', comment: 'Comment' };
  var rec = review.merge_recommendation || 'comment';
  DOM.mergeRec.className = 'merge-rec ' + rec;
  DOM.mergeRec.innerHTML = '<span class="merge-rec-icon">' + (recIcons[rec] || '💬') + '</span><span>' + (recLabels[rec] || rec) + '</span>';

  DOM.prSummary.textContent = review.summary || '';

  // Secret scan banner
  var secrets = review.secret_scan;
  if (secrets && secrets.found) {
    DOM.secretBanner.classList.remove('hidden');
    var items = (secrets.occurrences || []).map(function(o) {
      return '<br>• ' + esc(o.rule) + ' in <code>' + esc(o.file) + '</code> line ' + o.line + ' — <code>' + esc(o.masked_value) + '</code>';
    }).join('');
    DOM.secretBanner.innerHTML = '<strong>⚠️ SECRETS DETECTED</strong> — Potential credentials found in diff:' + items;
  } else {
    DOM.secretBanner.classList.add('hidden');
  }

  // Stats
  var sevColors = { critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#3b82f6', info: '#64748b' };
  var sevCounts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  (review.issues || []).forEach(function(i) { if (sevCounts[i.severity] !== undefined) sevCounts[i.severity]++; });

  var statsHtml =
    '<div class="stat-card"><div class="stat-value" style="color:var(--brand-from)">' + review.files_changed + '</div><div class="stat-label">Files</div></div>' +
    '<div class="stat-card"><div class="stat-value" style="color:#22c55e">+' + review.lines_added + '</div><div class="stat-label">Added</div></div>' +
    '<div class="stat-card"><div class="stat-value" style="color:#ef4444">-' + review.lines_removed + '</div><div class="stat-label">Removed</div></div>' +
    '<div class="stat-card"><div class="stat-value">' + review.total_issues + '</div><div class="stat-label">Issues</div></div>';
  Object.keys(sevCounts).forEach(function(sev) {
    if (sevCounts[sev] > 0) {
      statsHtml += '<div class="stat-card"><div class="stat-value" style="color:' + sevColors[sev] + '">' + sevCounts[sev] + '</div><div class="stat-label">' + sev + '</div></div>';
    }
  });
  DOM.prStats.innerHTML = statsHtml;

  // Filters
  var uniqSevs = Array.from(new Set((review.issues || []).map(function(i) { return i.severity; })));
  var uniqCats = Array.from(new Set((review.issues || []).map(function(i) { return i.category; })));
  var filterHtml = '<button class="filter-btn active" data-filter="all">All (' + review.total_issues + ')</button>';
  uniqSevs.forEach(function(sev) {
    filterHtml += '<button class="filter-btn" data-filter="sev:' + sev + '" style="border-color:' + (sevColors[sev] || '#888') + '44">' + sev + ' (' + sevCounts[sev] + ')</button>';
  });
  uniqCats.forEach(function(cat) {
    filterHtml += '<button class="filter-btn" data-filter="cat:' + cat + '">' + cat.replace('_', ' ') + '</button>';
  });
  DOM.issueFilters.innerHTML = filterHtml;

  function renderIssues(filter) {
    var issues = (review.issues || []).slice();
    if (filter !== 'all') {
      if (filter.indexOf('sev:') === 0) {
        var sev = filter.slice(4);
        issues = issues.filter(function(i) { return i.severity === sev; });
      } else if (filter.indexOf('cat:') === 0) {
        var cat = filter.slice(4);
        issues = issues.filter(function(i) { return i.category === cat; });
      }
    }
    var sevOrder = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    issues.sort(function(a, b) { return (sevOrder[a.severity] !== undefined ? sevOrder[a.severity] : 5) - (sevOrder[b.severity] !== undefined ? sevOrder[b.severity] : 5); });
    DOM.issuesList.innerHTML = issues.map(renderIssueCard).join('');
    DOM.issuesList.querySelectorAll('.issue-header').forEach(function(h) {
      h.addEventListener('click', function() { h.closest('.issue-card').classList.toggle('expanded'); });
    });
  }

  DOM.issueFilters.querySelectorAll('.filter-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      DOM.issueFilters.querySelectorAll('.filter-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      renderIssues(btn.dataset.filter);
    });
  });
  renderIssues('all');

  showState('prReviewResult');
}

function renderIssueCard(issue) {
  var loc = issue.location;
  var locHtml = '';
  if (loc) {
    var lineRange = loc.start_line ? ' : L' + loc.start_line : '';
    if (loc.end_line && loc.end_line !== loc.start_line) lineRange += '–' + loc.end_line;
    locHtml = '<div class="issue-location">📁 ' + esc(loc.file_path) + lineRange + '</div>';
    if (loc.snippet) locHtml += '<pre class="issue-snippet">' + esc(loc.snippet) + '</pre>';
  }
  var refs = (issue.references || []).map(function(r) {
    return '<a class="issue-ref-link" href="' + esc(r) + '" target="_blank" rel="noopener">' + esc(r) + '</a>';
  }).join('');

  return '<div class="issue-card" data-severity="' + esc(issue.severity) + '">' +
    '<div class="issue-header">' +
      '<span class="issue-id">' + esc(issue.id) + '</span>' +
      '<span class="issue-title">' + esc(issue.title) + '</span>' +
      '<span class="category-tag ' + issue.category + '">' + issue.category.replace('_', ' ') + '</span>' +
      '<span class="severity-badge ' + issue.severity + '">' + issue.severity + '</span>' +
      '<svg class="test-case-chevron" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">' +
        '<path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>' +
    '</div>' +
    '<div class="issue-body">' +
      '<p class="issue-description">' + esc(issue.description) + '</p>' +
      locHtml +
      '<div class="issue-suggestion">' + esc(issue.suggestion) + '</div>' +
      (refs ? '<div class="issue-refs">' + refs + '</div>' : '') +
    '</div>' +
  '</div>';
}

/* ─────────────────────────────────────────────────────────────────────────
   EXAMPLE CHIPS
   ─────────────────────────────────────────────────────────────────────── */
var EXAMPLES = {
  'testgen-login': {
    type: 'testgen',
    description: 'As a user, I want to log in using Face ID so that I can access the app securely.\n\nAcceptance Criteria:\n- Face ID prompt appears on first app launch after successful password login\n- Successful auth grants access within 2 seconds\n- After 3 failed Face ID attempts, fall back to password entry\n- Settings toggle to enable/disable Face ID\n- If the device does not support Face ID, the option is hidden\n- Session invalidated after 15 minutes of inactivity',
  },
  'testgen-checkout': {
    type: 'testgen',
    description: 'Users can complete a purchase using Apple Pay, credit card, or PayPal.\n\nAcceptance Criteria:\n- Show payment sheet with all available methods\n- Validate billing address before processing\n- Display order summary with item count, subtotal, tax, and total\n- On success, show confirmation with order ID\n- On payment failure, show error and allow retry without losing cart\n- Declined cards show a human-readable error\n- 3D Secure supported for EU credit cards',
  },
  'testgen-search': {
    type: 'testgen',
    description: 'Users can search products with full-text search and filter by category, price range, and availability.\n\nAcceptance Criteria:\n- Results appear within 300ms\n- Filters persist when navigating back\n- No-results state shows alternatives\n- Price range slider: min must be less than max\n- Query highlighted in result titles\n- Sort by: relevance, price asc/desc, newest',
  },
  'prreview-auth': {
    type: 'prreview',
    pr_title: 'feat: Add Face ID authentication (LAContext)',
    diff: 'diff --git a/Sources/Auth/AuthManager.swift b/Sources/Auth/AuthManager.swift\nindex 1a2b3c..4d5e6f 100644\n--- a/Sources/Auth/AuthManager.swift\n+++ b/Sources/Auth/AuthManager.swift\n@@ -1,7 +1,42 @@\n import Foundation\n+import LocalAuthentication\n+import os.log\n \n-class AuthManager {\n-    func login(password: String) -> Bool {\n-        return password == "admin123"\n-    }\n+@MainActor\n+class AuthManager: ObservableObject {\n+    static let shared = AuthManager()\n+    @Published var isAuthenticated = false\n+    private let context = LAContext()\n+    private let logger = Logger(subsystem: "com.myapp", category: "auth")\n+    private init() {}\n+\n+    func authenticateWithBiometrics() async throws {\n+        var error: NSError?\n+        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {\n+            logger.warning("Biometrics unavailable")\n+            throw AuthError.biometricsUnavailable\n+        }\n+        do {\n+            try await context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: "Sign in")\n+            isAuthenticated = true\n+        } catch {\n+            throw AuthError.authenticationFailed(error)\n+        }\n+    }\n+\n+    func signOut() {\n+        isAuthenticated = false\n+        // TODO: clear keychain\n+    }\n }\n+\n+enum AuthError: LocalizedError {\n+    case biometricsUnavailable\n+    case authenticationFailed(Error)\n+    var errorDescription: String? {\n+        switch self {\n+        case .biometricsUnavailable: return "Biometrics not available."\n+        case .authenticationFailed(let e): return "Auth failed: \\(e.localizedDescription)"\n+        }\n+    }\n+}',
  },
  'prreview-network': {
    type: 'prreview',
    pr_title: 'refactor: async/await networking layer',
    diff: 'diff --git a/Sources/Networking/APIClient.swift b/Sources/Networking/APIClient.swift\nindex abc123..def456 100644\n--- a/Sources/Networking/APIClient.swift\n+++ b/Sources/Networking/APIClient.swift\n@@ -1,10 +1,48 @@\n import Foundation\n \n-class APIClient {\n-    static let shared = APIClient()\n-    let baseURL = "https://api.myapp.com"\n+struct APIClient {\n+    private let session: URLSession\n+    private let decoder: JSONDecoder\n+    private let baseURL: URL\n+\n+    init(baseURL: URL, session: URLSession = .shared) {\n+        self.baseURL = baseURL\n+        self.session = session\n+        self.decoder = JSONDecoder()\n+        self.decoder.keyDecodingStrategy = .convertFromSnakeCase\n+        self.decoder.dateDecodingStrategy = .iso8601\n+    }\n+\n+    func get<T: Decodable>(_ path: String) async throws -> T {\n+        let url = baseURL.appendingPathComponent(path)\n+        var request = URLRequest(url: url)\n+        request.setValue("application/json", forHTTPHeaderField: "Accept")\n+        let (data, response) = try await session.data(for: request)\n+        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {\n+            throw NetworkError.httpError\n+        }\n+        return try decoder.decode(T.self, from: data)\n+    }\n }\n+\n+enum NetworkError: LocalizedError {\n+    case invalidURL, httpError\n+    var errorDescription: String? { "Network error" }\n+}',
  },
  'prreview-secret': {
    type: 'prreview',
    pr_title: 'chore: Add analytics configuration',
    diff: 'diff --git a/Sources/Analytics/Config.swift b/Sources/Analytics/Config.swift\nnew file mode 100644\n--- /dev/null\n+++ b/Sources/Analytics/Config.swift\n@@ -0,0 +1,12 @@\n+import Foundation\n+\n+struct AnalyticsConfig {\n+    static let amplitudeAPIKey     = "abc123secretkey9876543210abcdef"\n+    static let mixpanelToken       = "mp_live_token_ABCDEF1234567890"\n+    static let stripePublishableKey = "pk_live_51AbCdEfGhIjKl"\n+    static let firebaseProjectId   = "my-app-prod"\n+\n+    static func configure() {\n+        // TODO: init SDKs\n+    }\n+}',
  },
};

document.querySelectorAll('.chip[data-example]').forEach(function(chip) {
  chip.addEventListener('click', function() {
    var key = chip.dataset.example;
    var ex = EXAMPLES[key];
    if (!ex) return;
    if (ex.type === 'testgen') {
      switchMode('testgen');
      DOM.featureDesc.value = ex.description;
      DOM.ticketId.value = '';
      DOM.featureDesc.focus();
    } else {
      switchMode('prreview');
      DOM.prTitle.value   = ex.pr_title || '';
      DOM.diffInput.value = ex.diff || '';
      DOM.diffInput.focus();
    }
  });
});

/* ── Keyboard shortcuts ─────────────────────────────────────────────────── */
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    if (currentMode === 'testgen') DOM.runTestGen.click();
    else DOM.runPRReview.click();
  }
  if (e.key === 'Escape') {
    var errState = getEl('errorState');
    if (errState && !errState.classList.contains('hidden')) window.clearError();
  }
});

/* ── Init ────────────────────────────────────────────────────────────────── */
(function init() {
  showState('emptyState');
  // Run health check in background — don't block UI
  checkHealth();
  setInterval(checkHealth, 30000);
})();

/* ── Export to Excel (.xlsx) ──────────────────────────────────────────── */
function downloadXLSX(workbook, filename) {
  /* Use FileSaver.js saveAs — handles Chrome filename and Safari gesture restrictions */
  var wbout = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
  var blob  = new Blob([wbout], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  });
  saveAs(blob, filename);
}

function exportTestSuiteXLSX(suite) {
  if (!suite || !suite.cases || suite.cases.length === 0) {
    alert('No test cases to export. Please generate a test suite first.');
    return;
  }

  var rows = [[
    'Test Case ID', 'Title', 'Category', 'Priority',
    'Preconditions', 'Step #', 'Action', 'Expected Result',
    'Expected Outcome', 'Tags'
  ]];

  suite.cases.forEach(function(tc) {
    var pre  = (tc.preconditions || []).join('\n');
    var tags = (tc.tags || []).join(', ');

    if (tc.steps && tc.steps.length > 0) {
      tc.steps.forEach(function(s) {
        rows.push([
          tc.id, tc.title, tc.category, tc.priority,
          pre, s.step_number, s.action, s.expected_result,
          tc.expected_outcome, tags
        ]);
      });
    } else {
      rows.push([
        tc.id, tc.title, tc.category, tc.priority,
        pre, '', '', '', tc.expected_outcome, tags
      ]);
    }
  });

  var ws = XLSX.utils.aoa_to_sheet(rows);

  // Column widths
  ws['!cols'] = [
    {wch:12},{wch:35},{wch:14},{wch:10},
    {wch:30},{wch:8},{wch:45},{wch:45},
    {wch:35},{wch:25}
  ];

  var wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Test Suite');

  var ticket   = (suite.ticket_id || 'export').replace(/[^a-zA-Z0-9_-]/g, '_');
  var dateStr  = new Date().toISOString().slice(0, 10);
  downloadXLSX(wb, 'TestSuite_' + ticket + '_' + dateStr + '.xlsx');
}

function exportPRReviewXLSX(review) {
  if (!review || !review.issues || review.issues.length === 0) {
    alert('No PR review issues to export. Please run a PR review first.');
    return;
  }

  var rows = [[
    'Issue ID', 'Category', 'Severity', 'Title',
    'File Path', 'Start Line', 'End Line', 'Snippet',
    'Description', 'Suggestion'
  ]];

  review.issues.forEach(function(issue) {
    var loc = issue.location || {};
    rows.push([
      issue.id, issue.category, issue.severity, issue.title,
      loc.file_path || '', loc.start_line || '', loc.end_line || '',
      loc.snippet || '', issue.description, issue.suggestion
    ]);
  });

  var ws = XLSX.utils.aoa_to_sheet(rows);
  ws['!cols'] = [
    {wch:10},{wch:16},{wch:12},{wch:35},
    {wch:30},{wch:10},{wch:10},{wch:35},
    {wch:50},{wch:50}
  ];

  var wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'PR Review');

  var prName  = (review.pr_title || 'export').replace(/[^a-zA-Z0-9_-]/g, '_');
  var dateStr = new Date().toISOString().slice(0, 10);
  downloadXLSX(wb, 'PRReview_' + prName + '_' + dateStr + '.xlsx');
}

/* Use event delegation on document so buttons inside hidden divs always work */
document.addEventListener('click', function(e) {
  var target = e.target.closest('#exportTestSuite');
  if (target) {
    exportTestSuiteXLSX(lastTestSuite);
    return;
  }
  target = e.target.closest('#exportPRReview');
  if (target) {
    exportPRReviewXLSX(lastPRReview);
    return;
  }
});

