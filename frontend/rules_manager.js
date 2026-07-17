/**
 * rules_manager.js
 * Full Rules Manager UI + Code Review results renderer.
 * Handles: rule loading, toggle, search, filter, custom rule creation,
 * Code Review tab, score gauges, violation cards, Excel export.
 */
'use strict';

/* ── State ─────────────────────────────────────────────────────────── */
let allRules = [];
let selectedCategory = 'all';

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];
const SEVERITY_COLORS = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#eab308',
  low:      '#3b82f6',
  info:     '#6366f1',
};
const SCORE_LABELS = {
  security:            '🔒 Security',
  architecture:        '🏛 Architecture',
  performance:         '⚡ Performance',
  maintainability:     '🔧 Maintainability',
  readability:         '📖 Readability',
  testing:             '🧪 Testing',
  production_readiness:'🚀 Production Ready',
};

/* ── Utility ─────────────────────────────────────────────────────── */
function slugify(s) { return s.toLowerCase().replace(/[_\s]/g, '-'); }
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' '); }

/* ────────────────────────────────────────────────────────────────────
   RULES MANAGER
   ──────────────────────────────────────────────────────────────────── */
async function loadRulesManager() {
  try {
    const res = await fetch('/api/rules');
    allRules = await res.json();
    renderSidebar();
    renderRulesGrid(allRules);
    updateActiveCount();
  } catch (err) {
    console.error('Failed to load rules:', err);
  }
}

function renderSidebar() {
  const sidebar = document.getElementById('rulesSidebar');
  if (!sidebar) return;

  const categories = ['all', ...new Set(allRules.map(r => r.category))].sort();

  sidebar.innerHTML = categories.map(cat => {
    const count = cat === 'all' ? allRules.length : allRules.filter(r => r.category === cat).length;
    const active = cat === selectedCategory ? 'class="sidebar-item active"' : 'class="sidebar-item"';
    return `<button ${active} data-category="${cat}">
      <span class="sidebar-cat-name">${cat === 'all' ? 'All Rules' : capitalize(cat)}</span>
      <span class="sidebar-cat-count">${count}</span>
    </button>`;
  }).join('');

  sidebar.querySelectorAll('.sidebar-item').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedCategory = btn.dataset.category;
      sidebar.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyFilters();
    });
  });
}

function applyFilters() {
  const search = (document.getElementById('rulesSearch')?.value || '').toLowerCase();
  let filtered = allRules;
  if (selectedCategory !== 'all') {
    filtered = filtered.filter(r => r.category === selectedCategory);
  }
  if (search) {
    filtered = filtered.filter(r =>
      r.name.toLowerCase().includes(search) ||
      r.description.toLowerCase().includes(search) ||
      r.id.toLowerCase().includes(search) ||
      r.tags.some(t => t.toLowerCase().includes(search))
    );
  }
  renderRulesGrid(filtered);
}

function renderRulesGrid(rules) {
  const grid = document.getElementById('rulesGrid');
  if (!grid) return;
  if (rules.length === 0) {
    grid.innerHTML = '<div class="rules-empty">No rules match your filter.</div>';
    return;
  }
  grid.innerHTML = rules.map(r => renderRuleCard(r)).join('');

  // Bind toggle switches
  grid.querySelectorAll('.rule-toggle').forEach(toggle => {
    toggle.addEventListener('change', async (e) => {
      const ruleId = e.target.dataset.ruleId;
      const enabled = e.target.checked;
      await patchRule(ruleId, { enabled });
      const rule = allRules.find(r => r.id === ruleId);
      if (rule) rule.enabled = enabled;
      updateActiveCount();
    });
  });

  // Expand details
  grid.querySelectorAll('.rule-card').forEach(card => {
    card.querySelector('.rule-card-header')?.addEventListener('click', (e) => {
      if (e.target.closest('.rule-toggle-wrap')) return;
      card.classList.toggle('expanded');
    });
  });
}

function renderRuleCard(rule) {
  const sev = rule.severity;
  const sevColor = SEVERITY_COLORS[sev] || '#6366f1';
  const tags = rule.tags.map(t => `<span class="rule-tag">${t}</span>`).join('');
  const autoFixBadge = rule.auto_fix
    ? `<span class="rule-autofx">⚡ Auto-fix</span>`
    : '';
  const customBadge = rule.custom
    ? `<span class="rule-custom-badge">Custom</span>`
    : '';

  const badEx = rule.examples?.bad
    ? `<div class="ex-block"><div class="ex-label bad-label">❌ Violation</div><pre class="ex-code">${escHtml(rule.examples.bad)}</pre></div>`
    : '';
  const goodEx = rule.examples?.good
    ? `<div class="ex-block"><div class="ex-label good-label">✅ Correct</div><pre class="ex-code">${escHtml(rule.examples.good)}</pre></div>`
    : '';

  const deleteBtn = rule.custom
    ? `<button class="rule-delete-btn" data-rule-id="${rule.id}" title="Delete custom rule">🗑</button>`
    : '';

  return `
<div class="rule-card ${rule.enabled ? 'rule-enabled' : 'rule-disabled'}" data-rule-id="${rule.id}">
  <div class="rule-card-header">
    <div class="rule-severity-bar" style="background:${sevColor}"></div>
    <div class="rule-card-main">
      <div class="rule-card-top">
        <span class="rule-id">${rule.id}</span>
        <span class="rule-sev-pill" style="background:${sevColor}20;color:${sevColor}">${sev}</span>
        ${autoFixBadge}${customBadge}
      </div>
      <div class="rule-name">${escHtml(rule.name)}</div>
      <div class="rule-desc-preview">${escHtml(rule.description)}</div>
      <div class="rule-tags">${tags}</div>
    </div>
    <div class="rule-toggle-wrap">
      ${deleteBtn}
      <label class="toggle-switch" title="${rule.enabled ? 'Disable rule' : 'Enable rule'}">
        <input type="checkbox" class="rule-toggle" data-rule-id="${rule.id}" ${rule.enabled ? 'checked' : ''}/>
        <span class="toggle-slider"></span>
      </label>
    </div>
  </div>
  <div class="rule-card-detail">
    <div class="rule-weight-row">
      <span class="rule-weight-label">Weight</span>
      <div class="rule-weight-bar">
        <div class="rule-weight-fill" style="width:${rule.weight * 10}%;background:${sevColor}"></div>
      </div>
      <span class="rule-weight-val">${rule.weight}/10</span>
    </div>
    ${rule.auto_fix_hint ? `<div class="rule-hint"><strong>Fix hint:</strong> ${escHtml(rule.auto_fix_hint)}</div>` : ''}
    <div class="rule-examples">${badEx}${goodEx}</div>
  </div>
</div>`;
}

function updateActiveCount() {
  const count = allRules.filter(r => r.enabled).length;
  const el = document.getElementById('rulesActiveCount');
  if (el) el.textContent = `${count} / ${allRules.length} active`;
}

async function patchRule(ruleId, patch) {
  try {
    await fetch(`/api/rules/${ruleId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
  } catch (err) {
    console.error('Failed to patch rule:', err);
  }
}

/* ── Search ──────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('rulesSearch')?.addEventListener('input', applyFilters);
});

/* ── New Rule Modal ──────────────────────────────────────────────── */
function initModal() {
  const modal = document.getElementById('newRuleModal');
  const openBtn = document.getElementById('openNewRuleModal');
  const closeBtn = document.getElementById('closeNewRuleModal');
  const cancelBtn = document.getElementById('cancelNewRule');
  const form = document.getElementById('newRuleForm');
  const weightInput = document.getElementById('ruleWeightInput');
  const weightVal = document.getElementById('ruleWeightVal');

  openBtn?.addEventListener('click', async () => {
    // Populate category select
    const catSel = document.getElementById('ruleCategoryInput');
    if (catSel && catSel.options.length === 0) {
      const cats = ['architecture','swift_best_practices','concurrency','performance',
                    'memory_management','security','networking','ui_ux','testing',
                    'code_quality','git_hygiene','banking','custom'];
      cats.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c; opt.textContent = capitalize(c);
        if (c === 'custom') opt.selected = true;
        catSel.appendChild(opt);
      });
    }
    modal?.classList.remove('hidden');
  });

  const closeModal = () => modal?.classList.add('hidden');
  closeBtn?.addEventListener('click', closeModal);
  cancelBtn?.addEventListener('click', closeModal);
  modal?.addEventListener('click', e => { if (e.target === modal) closeModal(); });

  weightInput?.addEventListener('input', () => {
    if (weightVal) weightVal.textContent = weightInput.value;
  });

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      name: document.getElementById('ruleNameInput')?.value,
      category: document.getElementById('ruleCategoryInput')?.value,
      severity: document.getElementById('ruleSeverityInput')?.value,
      description: document.getElementById('ruleDescInput')?.value,
      weight: parseInt(document.getElementById('ruleWeightInput')?.value || '5', 10),
      auto_fix: document.getElementById('ruleAutoFix')?.checked,
      enabled: document.getElementById('ruleEnabled')?.checked,
      examples: {
        bad: document.getElementById('ruleBadExInput')?.value || '',
        good: document.getElementById('ruleGoodExInput')?.value || '',
      },
      tags: [],
    };
    try {
      const res = await fetch('/api/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const newRule = await res.json();
        allRules.push(newRule);
        closeModal();
        form.reset();
        renderSidebar();
        applyFilters();
        updateActiveCount();
      } else {
        alert('Failed to create rule. Please check your inputs.');
      }
    } catch (err) {
      alert('Network error: ' + err.message);
    }
  });
}

/* ── Delete custom rule ─────────────────────────────────────────── */
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.rule-delete-btn');
  if (!btn) return;
  const ruleId = btn.dataset.ruleId;
  if (!confirm(`Delete rule ${ruleId}? This cannot be undone.`)) return;
  const res = await fetch(`/api/rules/${ruleId}`, { method: 'DELETE' });
  if (res.ok || res.status === 204) {
    allRules = allRules.filter(r => r.id !== ruleId);
    renderSidebar();
    applyFilters();
    updateActiveCount();
  }
});

/* ────────────────────────────────────────────────────────────────────
   CODE REVIEW
   ──────────────────────────────────────────────────────────────────── */
async function loadActiveRuleCount() {
  try {
    const res = await fetch('/api/rules?enabled=true');
    const rules = await res.json();
    const el = document.getElementById('crRulesCount');
    if (el) el.textContent = `${rules.length} active rules will be applied`;
  } catch {
    const el = document.getElementById('crRulesCount');
    if (el) el.textContent = 'Could not load rule count';
  }
}

function initCodeReview() {
  const btn = document.getElementById('runCodeReview');
  btn?.addEventListener('click', runCodeReview);

  document.getElementById('goToRulesLink')?.addEventListener('click', (e) => {
    e.preventDefault();
    if (typeof switchMode === 'function') switchMode('rules');
  });

  document.getElementById('exportCRExcel')?.addEventListener('click', exportReviewToExcel);
}

async function runCodeReview() {
  const diff = document.getElementById('crDiffInput')?.value?.trim();
  if (!diff) {
    alert('Please paste a git diff before running the review.');
    return;
  }

  const btn = document.getElementById('runCodeReview');
  if (btn) {
    btn.disabled = true;
    btn.querySelector('.btn-text').textContent = 'Reviewing…';
  }

  // Show output panel
  const outputPanel = document.getElementById('panel-codereview-output');
  if (outputPanel) {
    outputPanel.classList.remove('hidden');
    document.getElementById('scoreGrid').innerHTML = '<div class="cr-loading">🤖 AI is reviewing your code against active rules…</div>';
    document.getElementById('violationsList').innerHTML = '';
    document.getElementById('crSummary').innerHTML = '';
  }

  try {
    const payload = {
      pr_title: document.getElementById('crPrTitle')?.value || 'Untitled PR',
      diff,
      language: document.getElementById('crLanguage')?.value || 'swift',
      context: document.getElementById('crContext')?.value || null,
    };
    const res = await fetch('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Review failed');
    }
    const result = await res.json();
    window._lastCRResult = result;
    renderCodeReviewResult(result);
  } catch (err) {
    document.getElementById('scoreGrid').innerHTML =
      `<div class="cr-error">⚠️ ${escHtml(err.message)}</div>`;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.querySelector('.btn-text').textContent = 'Run Code Review';
    }
  }
}

function renderCodeReviewResult(result) {
  // Title + approved badge
  const titleEl = document.getElementById('crTitle');
  if (titleEl) titleEl.textContent = result.pr_title || 'Code Review';

  const badge = document.getElementById('crApproved');
  if (badge) {
    badge.textContent = result.approved ? '✅ Approved' : '❌ Changes Requested';
    badge.className = `cr-badge ${result.approved ? 'badge-approved' : 'badge-rejected'}`;
  }

  // Score gauges
  const scoreGrid = document.getElementById('scoreGrid');
  if (scoreGrid && result.scores) {
    scoreGrid.innerHTML = Object.entries(SCORE_LABELS).map(([key, label]) => {
      const score = result.scores[key] ?? 0;
      const color = score >= 80 ? '#22c55e' : score >= 60 ? '#eab308' : '#ef4444';
      return `
<div class="score-card">
  <div class="score-gauge-wrap">
    <svg class="score-gauge" viewBox="0 0 36 36">
      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        fill="none" stroke="#1e293b" stroke-width="3.5"/>
      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        fill="none" stroke="${color}" stroke-width="3.5"
        stroke-dasharray="${score}, 100" stroke-linecap="round"/>
      <text x="18" y="20.5" class="gauge-text" fill="${color}">${score}</text>
    </svg>
  </div>
  <div class="score-label">${label}</div>
</div>`;
    }).join('');

    // Overall score hero
    const overall = result.scores.overall ?? 0;
    const overallColor = overall >= 80 ? '#22c55e' : overall >= 60 ? '#eab308' : '#ef4444';
    scoreGrid.insertAdjacentHTML('afterbegin', `
<div class="score-card score-overall">
  <div class="score-gauge-wrap">
    <svg class="score-gauge score-gauge-lg" viewBox="0 0 36 36">
      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        fill="none" stroke="#1e293b" stroke-width="3.5"/>
      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        fill="none" stroke="${overallColor}" stroke-width="3.5"
        stroke-dasharray="${overall}, 100" stroke-linecap="round"/>
      <text x="18" y="20.5" class="gauge-text" fill="${overallColor}">${overall}</text>
    </svg>
  </div>
  <div class="score-label">⭐ Overall</div>
</div>`);
  }

  // Violations
  const violations = result.violations || [];
  const countEl = document.getElementById('violationCount');
  if (countEl) countEl.textContent = violations.length;

  const list = document.getElementById('violationsList');
  if (list) {
    if (violations.length === 0) {
      list.innerHTML = '<div class="no-violations">🎉 No violations found — excellent code quality!</div>';
    } else {
      // Sort by severity
      const sorted = [...violations].sort((a, b) =>
        SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
      );
      list.innerHTML = sorted.map(v => renderViolationCard(v)).join('');
    }
  }

  // Violation severity filter pills
  const filtersEl = document.getElementById('violationFilters');
  if (filtersEl && violations.length > 0) {
    const sevCounts = {};
    violations.forEach(v => { sevCounts[v.severity] = (sevCounts[v.severity] || 0) + 1; });
    filtersEl.innerHTML = `<button class="vf-pill active" data-sev="all">All (${violations.length})</button>` +
      SEVERITY_ORDER.filter(s => sevCounts[s]).map(s =>
        `<button class="vf-pill" data-sev="${s}" style="--sev-color:${SEVERITY_COLORS[s]}">${s} (${sevCounts[s]})</button>`
      ).join('');

    filtersEl.querySelectorAll('.vf-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        filtersEl.querySelectorAll('.vf-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        const sev = pill.dataset.sev;
        list.querySelectorAll('.violation-card').forEach(card => {
          card.style.display = (sev === 'all' || card.dataset.sev === sev) ? '' : 'none';
        });
      });
    });
  }

  // Summary
  const sumEl = document.getElementById('crSummary');
  if (sumEl && result.summary) {
    sumEl.innerHTML = `<div class="cr-summary-label">AI Summary</div><p>${escHtml(result.summary)}</p>
      <div class="cr-meta">Model: ${result.model_used} · Rules applied: ${result.active_rules_count} · ${new Date(result.reviewed_at).toLocaleString()}</div>`;
  }
}

function renderViolationCard(v) {
  const color = SEVERITY_COLORS[v.severity] || '#6366f1';
  const autoFix = v.auto_fix_available
    ? `<span class="v-autofx">⚡ Auto-fix available</span>` : '';
  const snippet = v.code_snippet
    ? `<pre class="v-snippet">${escHtml(v.code_snippet)}</pre>` : '';
  const fix = v.suggested_fix
    ? `<div class="v-fix"><strong>Fix:</strong> ${escHtml(v.suggested_fix)}</div>` : '';
  const impact = v.business_impact
    ? `<div class="v-impact"><strong>Business Impact:</strong> ${escHtml(v.business_impact)}</div>` : '';

  return `
<div class="violation-card" data-sev="${v.severity}">
  <div class="v-header" style="border-left:3px solid ${color}">
    <div class="v-header-left">
      <span class="v-rule-id">${v.rule_id}</span>
      <span class="v-sev" style="color:${color}">${v.severity.toUpperCase()}</span>
      ${autoFix}
    </div>
    <span class="v-cat">${capitalize(v.category)}</span>
  </div>
  <div class="v-body">
    <div class="v-rule-name">${escHtml(v.rule_name)}</div>
    <div class="v-explanation">${escHtml(v.explanation)}</div>
    ${snippet}
    ${impact}
    ${fix}
    ${v.line_hint ? `<div class="v-line-hint">📍 ${escHtml(v.line_hint)}</div>` : ''}
  </div>
</div>`;
}

/* ── Excel Export ────────────────────────────────────────────────── */
function exportReviewToExcel() {
  const result = window._lastCRResult;
  if (!result) { alert('No review results to export.'); return; }

  // Sheet 1: Scores
  const scoresData = [
    ['Dimension', 'Score'],
    ...Object.entries(SCORE_LABELS).map(([k, label]) => [label, result.scores[k] ?? 0]),
    ['⭐ Overall', result.scores.overall ?? 0],
  ];

  // Sheet 2: Violations
  const violData = [
    ['Rule ID','Rule Name','Category','Severity','Explanation','Business Impact','Suggested Fix','Code Snippet','Auto-Fix'],
    ...(result.violations || []).map(v => [
      v.rule_id, v.rule_name, v.category, v.severity,
      v.explanation, v.business_impact, v.suggested_fix,
      v.code_snippet, v.auto_fix_available ? 'Yes' : 'No',
    ]),
  ];

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(scoresData), 'Scores');
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(violData), 'Violations');

  const filename = `CodeReview_${(result.pr_title || 'PR').replace(/[^a-zA-Z0-9]/g,'_')}_${Date.now()}.xlsx`;
  const wbOut = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  saveAs(new Blob([wbOut], { type: 'application/octet-stream' }), filename);
}

/* ── Escape HTML helper ─────────────────────────────────────────── */
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* ── Bootstrap ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initModal();
  initCodeReview();
});
