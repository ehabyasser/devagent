/* ═══════════════════════════════════════════════════════════════════════
   assistant.js — Floating AI writing assistant
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  let isOpen     = false;
  let isStreaming = false;
  let history    = [];
  let currentMode = 'testgen';

  const MODE_META = {
    testgen:    { label: 'Test Generator',  hint: 'Describe the feature or user story in your own words…', field: 'featureDescription' },
    codereview: { label: 'Code Review',     hint: 'Describe what the code change does…',                   field: 'crContext' },
    rules:      { label: 'Rules Manager',   hint: 'Describe the coding standard you want to enforce…',    field: null },
  };

  /* ── Read current app mode reliably ──────────────────────────────────── */
  function getAppMode() {
    // app.js sets window.devAgentMode on every switchMode call
    const m = window.devAgentMode;
    return (m && MODE_META[m]) ? m : 'testgen';
  }

  /* ── Escape HTML ──────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  /* ── Format markdown-ish text to HTML ────────────────────────────────── */
  function fmt(text) {
    if (!text) return '';
    let out = esc(text);
    out = out.replace(/\*\*(.+?)\*\*/gs, '<strong>$1</strong>');
    out = out.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/gs, '<em>$1</em>');
    out = out.replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>');

    const lines  = out.split('\n');
    const result = [];
    let inOl = false, inUl = false;

    for (const line of lines) {
      const numM = line.match(/^(\d+)\.\s+(.*)/);
      const bulM = line.match(/^[-•]\s+(.*)/);
      if (numM) {
        if (inUl) { result.push('</ul>'); inUl = false; }
        if (!inOl) { result.push('<ol class="ai-list">'); inOl = true; }
        result.push(`<li>${numM[2]}</li>`);
      } else if (bulM) {
        if (inOl) { result.push('</ol>'); inOl = false; }
        if (!inUl) { result.push('<ul class="ai-list">'); inUl = true; }
        result.push(`<li>${bulM[1]}</li>`);
      } else {
        if (inOl) { result.push('</ol>'); inOl = false; }
        if (inUl) { result.push('</ul>'); inUl = false; }
        result.push(line === '' ? '<br>' : `<span>${line}</span><br>`);
      }
    }
    if (inOl) result.push('</ol>');
    if (inUl) result.push('</ul>');
    return result.join('');
  }

  /* ── Severity colors ──────────────────────────────────────────────────── */
  const SEV_COLORS = { critical:'#ef4444', high:'#f97316', medium:'#eab308', low:'#22c55e', info:'#6366f1' };

  /* ── Build widget HTML ────────────────────────────────────────────────── */
  function buildWidget() {
    const wrap = document.createElement('div');
    wrap.id = 'aiAssistWrap';
    wrap.innerHTML = `
      <button id="aiAssistFab" class="ai-fab" aria-label="Open AI Writing Assistant" title="AI Writing Assistant">
        <svg class="ai-fab-icon ai-fab-icon-chat" width="22" height="22" viewBox="0 0 24 24" fill="none">
          <path d="M12 2C6.48 2 2 6.04 2 11c0 2.52 1.09 4.79 2.84 6.4L4 22l4.75-1.55A10.1 10.1 0 0012 21c5.52 0 10-4.04 10-9s-4.48-9-10-9z" fill="currentColor" opacity=".9"/>
          <circle cx="8" cy="11" r="1.2" fill="white"/><circle cx="12" cy="11" r="1.2" fill="white"/><circle cx="16" cy="11" r="1.2" fill="white"/>
        </svg>
        <svg class="ai-fab-icon ai-fab-icon-close hidden" width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
        </svg>
        <span class="ai-fab-pulse"></span>
      </button>

      <div id="aiAssistPanel" class="ai-panel hidden" role="dialog" aria-label="AI Writing Assistant">
        <div class="ai-panel-header">
          <div class="ai-panel-header-left">
            <div class="ai-panel-avatar">✦</div>
            <div>
              <div class="ai-panel-title">AI Assistant</div>
              <div class="ai-panel-subtitle" id="aiModeLabel">Test Generator</div>
            </div>
          </div>
          <div class="ai-panel-header-right">
            <button class="ai-icon-btn" id="aiClearBtn" title="Clear chat">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button class="ai-icon-btn" id="aiCloseBtn" title="Close">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            </button>
          </div>
        </div>

        <div class="ai-messages" id="aiMessages">
          <div class="ai-welcome" id="aiWelcome">
            <div class="ai-welcome-icon">✦</div>
            <p class="ai-welcome-title">AI Writing Assistant</p>
            <p class="ai-welcome-body">Describe your idea in plain language — I'll generate a proper description or suggest rules based on the current mode.</p>
            <div class="ai-mode-chips">
              <span class="ai-mode-chip active" data-mode="testgen">🧪 Test Gen</span>
              <span class="ai-mode-chip" data-mode="codereview">🔍 Code Review</span>
              <span class="ai-mode-chip" data-mode="rules">📋 Rules</span>
            </div>
          </div>
        </div>

        <div class="ai-input-area">
          <textarea id="aiInput" class="ai-textarea" placeholder="Describe what you need…" rows="2" maxlength="2000" aria-label="Message"></textarea>
          <div class="ai-input-footer">
            <span class="ai-char-count" id="aiCharCount">0 / 2000</span>
            <button class="ai-send-btn" id="aiSendBtn" aria-label="Send" disabled>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(wrap);
  }

  /* ── Append user bubble ───────────────────────────────────────────────── */
  function appendUserBubble(content) {
    const c = document.getElementById('aiMessages');
    const w = document.getElementById('aiWelcome');
    if (w) w.style.display = 'none';
    const d = document.createElement('div');
    d.className = 'ai-msg ai-msg-user';
    d.innerHTML = `<div class="ai-bubble ai-bubble-user">${esc(content)}</div>`;
    c.appendChild(d); c.scrollTop = c.scrollHeight;
  }

  /* ── Append assistant skeleton bubble ────────────────────────────────── */
  function appendAssistantBubble(id) {
    const c = document.getElementById('aiMessages');
    const d = document.createElement('div');
    d.className = 'ai-msg ai-msg-assistant';
    d.id = id;
    d.innerHTML = `
      <div class="ai-bubble-wrap">
        <div class="ai-bubble ai-bubble-assistant" id="${id}-text">
          <span class="ai-loading-dots"><span></span><span></span><span></span></span>
        </div>
        <div class="ai-bubble-actions" id="${id}-actions" style="display:none">
          <button class="ai-action-btn ai-copy-btn">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="1.8"/></svg>
            Copy
          </button>
          <button class="ai-action-btn ai-insert-btn">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12l7 7 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Insert
          </button>
        </div>
      </div>`;
    c.appendChild(d); c.scrollTop = c.scrollHeight;
    return d;
  }

  /* ── Finalize streaming bubble ────────────────────────────────────────── */
  function finalizeAssistantBubble(id, fullText) {
    const textEl    = document.getElementById(id + '-text');
    const actionsEl = document.getElementById(id + '-actions');
    if (textEl)    textEl.innerHTML = fmt(fullText);
    if (actionsEl) actionsEl.style.display = '';

    actionsEl?.querySelector('.ai-copy-btn')?.addEventListener('click', function () {
      navigator.clipboard.writeText(fullText).then(() => {
        this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="#22c55e" stroke-width="2" stroke-linecap="round"/></svg> Copied!`;
        this.style.color = '#22c55e';
        setTimeout(() => { this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="1.8"/></svg> Copy`; this.style.color = ''; }, 2000);
      });
    });

    actionsEl?.querySelector('.ai-insert-btn')?.addEventListener('click', function () {
      const fieldId = MODE_META[currentMode]?.field;
      const field   = fieldId ? document.getElementById(fieldId) : null;
      if (field) {
        field.value = fullText;
        field.dispatchEvent(new Event('input', { bubbles: true }));
        field.focus();
        if (typeof switchMode === 'function') switchMode(currentMode);
        this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="#22c55e" stroke-width="2" stroke-linecap="round"/></svg> Inserted!`;
        this.style.color = '#22c55e';
        setTimeout(() => { this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12l7 7 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg> Insert`; this.style.color = ''; }, 2000);
      } else {
        navigator.clipboard.writeText(fullText);
        this.textContent = 'Copied!';
        setTimeout(() => { this.textContent = 'Insert'; }, 2000);
      }
    });
  }

  /* ── Render rule suggestion cards ─────────────────────────────────────── */
  function appendRuleSuggestions(id, rules) {
    const textEl    = document.getElementById(id + '-text');
    const actionsEl = document.getElementById(id + '-actions');
    if (!textEl) return;

    const cardsHtml = rules.map((r, i) => `
      <div class="ai-rule-card" id="${id}-rule-${i}">
        <div class="ai-rule-card-header">
          <span class="ai-rule-cat">${esc(r.category)}</span>
          <span class="ai-rule-sev" style="color:${SEV_COLORS[r.severity]||'#6366f1'}">${esc(r.severity?.toUpperCase())}</span>
        </div>
        <div class="ai-rule-name">${esc(r.name)}</div>
        <div class="ai-rule-desc">${esc(r.description)}</div>
        <button class="ai-add-rule-btn" data-rule-idx="${i}">
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M7 2v10M2 7h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          Add Rule
        </button>
      </div>`).join('');

    textEl.innerHTML = `
      <div class="ai-rules-intro">✦ ${rules.length} rule suggestion${rules.length === 1 ? '' : 's'} based on your description:</div>
      ${cardsHtml}`;
    if (actionsEl) actionsEl.style.display = 'none'; // no copy/insert for rule cards

    // Wire Add buttons
    textEl.querySelectorAll('.ai-add-rule-btn').forEach(btn => {
      btn.addEventListener('click', async function () {
        const idx  = parseInt(this.dataset.ruleIdx);
        const rule = rules[idx];
        this.disabled = true;
        this.innerHTML = '<span class="ai-loading-dots"><span></span><span></span><span></span></span>';
        try {
          const res = await fetch('/api/rules', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
              name:        rule.name,
              category:    rule.category,
              description: rule.description,
              severity:    rule.severity,
              weight:      rule.weight,
              auto_fix:    rule.auto_fix,
              tags:        rule.tags,
              examples:    rule.examples,
              enabled:     true,
            }),
          });
          if (!res.ok) throw new Error('Failed');
          this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="#22c55e" stroke-width="2" stroke-linecap="round"/></svg> Added!`;
          this.style.color = '#22c55e';
          document.getElementById(`${id}-rule-${idx}`)?.classList.add('ai-rule-card-added');
          // Refresh rules manager if visible
          if (typeof loadRulesManager === 'function' && window.devAgentMode === 'rules') loadRulesManager();
          if (typeof loadActiveRuleCount === 'function') loadActiveRuleCount();
        } catch (_) {
          this.disabled = false;
          this.innerHTML = '⚠️ Retry';
          this.style.color = '#ef4444';
        }
      });
    });
  }

  /* ── Stream a text response ───────────────────────────────────────────── */
  async function streamResponse(userMsg) {
    if (isStreaming) return;
    isStreaming = true;
    const sendBtn = document.getElementById('aiSendBtn');
    if (sendBtn) sendBtn.disabled = true;

    appendUserBubble(userMsg);
    const msgId = 'ai-resp-' + Date.now();
    appendAssistantBubble(msgId);

    // Rules mode → use structured suggest endpoint instead of stream
    if (currentMode === 'rules') {
      try {
        const res = await fetch('/api/assist/rules-suggest', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ description: userMsg }),
        });
        if (!res.ok) throw new Error('Rule suggestion failed (HTTP ' + res.status + ')');
        const rules = await res.json();
        history.push({ role: 'user', content: userMsg });
        history.push({ role: 'assistant', content: `[${rules.length} rule suggestions]` });
        appendRuleSuggestions(msgId, rules);
      } catch (err) {
        const textEl = document.getElementById(msgId + '-text');
        if (textEl) textEl.innerHTML = `<span style="color:#f87171">⚠️ ${esc(err.message)}</span>`;
      } finally {
        isStreaming = false;
        const inp = document.getElementById('aiInput');
        if (sendBtn) sendBtn.disabled = !(inp && inp.value.trim());
      }
      return;
    }

    // testgen / codereview → streaming SSE
    let accumulated = '';
    try {
      const res = await fetch('/api/assist/stream', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: userMsg, mode: currentMode, history: history.slice(-6) }),
      });
      if (!res.ok) throw new Error('Assistant unavailable (HTTP ' + res.status + ')');

      const reader    = res.body.getReader();
      const decoder   = new TextDecoder();
      let   sseBuffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        sseBuffer += decoder.decode(value, { stream: true });
        const parts = sseBuffer.split('\n\n');
        sseBuffer = parts.pop() ?? '';
        for (const part of parts) {
          for (const line of part.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (raw === '[DONE]') break;
            try {
              const { token } = JSON.parse(raw);
              if (token) {
                accumulated += token;
                const textEl = document.getElementById(msgId + '-text');
                if (textEl) textEl.innerHTML = fmt(accumulated) + '<span class="ai-cursor">▍</span>';
                const msgs = document.getElementById('aiMessages');
                if (msgs) msgs.scrollTop = msgs.scrollHeight;
              }
            } catch (_) {}
          }
        }
      }
      history.push({ role: 'user', content: userMsg });
      history.push({ role: 'assistant', content: accumulated });
      finalizeAssistantBubble(msgId, accumulated);
    } catch (err) {
      const textEl = document.getElementById(msgId + '-text');
      if (textEl) textEl.innerHTML = `<span style="color:#f87171">⚠️ ${esc(err.message || 'Something went wrong.')}</span>`;
    } finally {
      isStreaming = false;
      const inp = document.getElementById('aiInput');
      if (sendBtn) sendBtn.disabled = !(inp && inp.value.trim());
    }
  }

  /* ── Sync mode from app ───────────────────────────────────────────────── */
  function syncMode() {
    const appMode = getAppMode();
    const meta    = MODE_META[appMode] || MODE_META.testgen;
    currentMode   = appMode;
    const label   = document.getElementById('aiModeLabel');
    const inp     = document.getElementById('aiInput');
    if (label) label.textContent = meta.label;
    if (inp)   inp.placeholder   = meta.hint;
    document.querySelectorAll('.ai-mode-chip').forEach(c => c.classList.toggle('active', c.dataset.mode === currentMode));
  }

  /* ── Toggle panel ─────────────────────────────────────────────────────── */
  function togglePanel() {
    isOpen = !isOpen;
    const panel     = document.getElementById('aiAssistPanel');
    const fab       = document.getElementById('aiAssistFab');
    const iconChat  = fab?.querySelector('.ai-fab-icon-chat');
    const iconClose = fab?.querySelector('.ai-fab-icon-close');

    if (isOpen) {
      panel?.classList.remove('hidden');
      panel?.classList.add('ai-panel-open');
      iconChat?.classList.add('hidden');
      iconClose?.classList.remove('hidden');
      fab?.classList.add('ai-fab-active');
      syncMode();
      setTimeout(() => document.getElementById('aiInput')?.focus(), 150);
    } else {
      panel?.classList.remove('ai-panel-open');
      panel?.classList.add('ai-panel-closing');
      setTimeout(() => { panel?.classList.add('hidden'); panel?.classList.remove('ai-panel-closing'); }, 250);
      iconChat?.classList.remove('hidden');
      iconClose?.classList.add('hidden');
      fab?.classList.remove('ai-fab-active');
    }
  }

  /* ── Init ─────────────────────────────────────────────────────────────── */
  function init() {
    buildWidget();
    const fab      = document.getElementById('aiAssistFab');
    const closeBtn = document.getElementById('aiCloseBtn');
    const clearBtn = document.getElementById('aiClearBtn');
    const sendBtn  = document.getElementById('aiSendBtn');
    const input    = document.getElementById('aiInput');

    fab?.addEventListener('click', togglePanel);
    closeBtn?.addEventListener('click', togglePanel);

    clearBtn?.addEventListener('click', () => {
      history = [];
      Array.from(document.getElementById('aiMessages')?.querySelectorAll('.ai-msg') || []).forEach(el => el.remove());
      const w = document.getElementById('aiWelcome');
      if (w) w.style.display = '';
    });

    input?.addEventListener('input', () => {
      const len = input.value.length;
      const cc  = document.getElementById('aiCharCount');
      if (cc) cc.textContent = `${len} / 2000`;
      if (sendBtn) sendBtn.disabled = !input.value.trim() || isStreaming;
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });

    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!sendBtn?.disabled) sendBtn?.click(); }
    });

    sendBtn?.addEventListener('click', () => {
      const msg = input?.value.trim();
      if (!msg || isStreaming) return;
      if (input) { input.value = ''; input.style.height = 'auto'; }
      const cc = document.getElementById('aiCharCount');
      if (cc) cc.textContent = '0 / 2000';
      if (sendBtn) sendBtn.disabled = true;
      syncMode();
      streamResponse(msg);
    });

    // Mode chips in welcome screen
    document.addEventListener('click', (e) => {
      const chip = e.target.closest('.ai-mode-chip');
      if (!chip) return;
      currentMode = chip.dataset.mode;
      document.querySelectorAll('.ai-mode-chip').forEach(c => c.classList.toggle('active', c === chip));
      const meta  = MODE_META[currentMode];
      const inp   = document.getElementById('aiInput');
      const label = document.getElementById('aiModeLabel');
      if (inp)   inp.placeholder   = meta.hint;
      if (label) label.textContent = meta.label;
    });

    // Patch switchMode to stay in sync
    const orig = window.switchMode;
    if (typeof orig === 'function') {
      window.switchMode = function (mode) { orig(mode); if (isOpen) syncMode(); };
    }
    setInterval(() => { if (isOpen) syncMode(); }, 1500);
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init)
    : init();
})();
