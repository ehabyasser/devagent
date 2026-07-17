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
    type: 'codereview',
    pr_title: 'feat: Add Face ID authentication (LAContext)',
    language: 'swift',
    diff: 'diff --git a/Sources/Auth/AuthManager.swift b/Sources/Auth/AuthManager.swift\nindex 1a2b3c..4d5e6f 100644\n--- a/Sources/Auth/AuthManager.swift\n+++ b/Sources/Auth/AuthManager.swift\n@@ -1,7 +1,35 @@\n import Foundation\n+import LocalAuthentication\n \n-class AuthManager {\n-    func login(password: String) -> Bool {\n-        return password == "admin123"\n-    }\n+@MainActor\n+class AuthManager: ObservableObject {\n+    static let shared = AuthManager()\n+    @Published var isAuthenticated = false\n+    private let context = LAContext()\n+    private init() {}\n+\n+    func authenticateWithBiometrics() async throws {\n+        var error: NSError?\n+        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) else {\n+            throw AuthError.biometricsUnavailable\n+        }\n+        try await context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: "Sign in")\n+        isAuthenticated = true\n+    }\n+}\n+enum AuthError: LocalizedError {\n+    case biometricsUnavailable, authenticationFailed(Error)\n+}',
  },
  'prreview-secret': {
    type: 'codereview',
    pr_title: 'chore: Add analytics configuration (hardcoded secrets)',
    language: 'swift',
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
      var fd = document.getElementById('featureDescription');
      var ti = document.getElementById('ticketId');
      if (fd) { fd.value = ex.description || ''; fd.focus(); }
      if (ti) ti.value = '';
    } else if (ex.type === 'codereview') {
      switchMode('codereview');
      var crTitle = document.getElementById('crPrTitle');
      var crDiff  = document.getElementById('crDiffInput');
      var crLang  = document.getElementById('crLanguage');
      if (crTitle) crTitle.value = ex.pr_title || '';
      if (crDiff)  { crDiff.value = ex.diff || ''; crDiff.focus(); }
      if (crLang && ex.language) crLang.value = ex.language;
    }
  });
});

/* ── Keyboard shortcuts ─────────────────────────────────────────────────── */
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    if (currentMode === 'testgen') {
      var btn = document.getElementById('runTestGen');
      if (btn) btn.click();
    } else if (currentMode === 'codereview') {
      var btn2 = document.getElementById('runCodeReview');
      if (btn2) btn2.click();
    }
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



/* Use event delegation on document so buttons inside hidden divs always work */
document.addEventListener('click', function(e) {
  var target = e.target.closest('#exportTestSuite');
  if (target) {
    exportTestSuiteXLSX(lastTestSuite);
    return;
  }
});

