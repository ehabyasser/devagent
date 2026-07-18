/* ═══════════════════════════════════════════════════════════════════════
   assistant.js — Floating AI writing assistant
   Context-aware chat that helps write feature descriptions, code review
   context, and rule definitions. Streams responses token by token.
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* ── State ──────────────────────────────────────────────────────────── */
  let isOpen      = false;
  let isStreaming  = false;
  let history      = [];   // [{role, content}]
  let currentMode  = 'testgen';

  const MODE_META = {
    testgen:    { label: 'Test Generator',  icon: '🧪', hint: 'Describe the feature or user story in your own words…', field: 'featureDescription' },
    codereview: { label: 'Code Review',     icon: '🔍', hint: 'Describe what the code change does…',                   field: 'crContext' },
    rules:      { label: 'Rules Manager',   icon: '📋', hint: 'Describe the coding standard you want to enforce…',    field: null },
  };

  /* ── HTML-escape ───────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* ── Format text: escape first, then apply light markdown ────────────
     Handles bold, numbered lists, bullet lists, code spans, line breaks
  ─────────────────────────────────────────────────────────────────────── */
  function fmt(text) {
    if (!text) return '';
    let out = esc(text);

    // Bold  **text**
    out = out.replace(/\*\*(.+?)\*\*/gs, '<strong>$1</strong>');
    // Italic  *text* (not bold)
    out = out.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/gs, '<em>$1</em>');
    // Inline code  `code`
    out = out.replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>');

    // Numbered list: lines starting with "1. " etc → wrap in <ol>
    // Bullet list:   lines starting with "- " or "• "
    const lines = out.split('\n');
    const result = [];
    let inOl = false, inUl = false;

    for (const line of lines) {
      const numMatch = line.match(/^(\d+)\.\s+(.*)/);
      const bulMatch = line.match(/^[-•]\s+(.*)/);

      if (numMatch) {
        if (inUl) { result.push('</ul>'); inUl = false; }
        if (!inOl) { result.push('<ol class="ai-list">'); inOl = true; }
        result.push(`<li>${numMatch[2]}</li>`);
      } else if (bulMatch) {
        if (inOl) { result.push('</ol>'); inOl = false; }
        if (!inUl) { result.push('<ul class="ai-list">'); inUl = true; }
        result.push(`<li>${bulMatch[1]}</li>`);
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

  /* ── Get current mode from app.js global ───────────────────────────── */
  function getAppMode() {
    try { return window.currentMode || 'testgen'; } catch (_) { return 'testgen'; }
  }

  /* ── Build widget HTML ──────────────────────────────────────────────── */
  function buildWidget() {
    const wrap = document.createElement('div');
    wrap.id = 'aiAssistWrap';
    wrap.innerHTML = `
      <!-- FAB button -->
      <button id="aiAssistFab" class="ai-fab" aria-label="Open AI Writing Assistant" title="AI Writing Assistant">
        <svg class="ai-fab-icon ai-fab-icon-chat" width="22" height="22" viewBox="0 0 24 24" fill="none">
          <path d="M12 2C6.48 2 2 6.04 2 11c0 2.52 1.09 4.79 2.84 6.4L4 22l4.75-1.55A10.1 10.1 0 0012 21c5.52 0 10-4.04 10-9s-4.48-9-10-9z" fill="currentColor" opacity=".9"/>
          <circle cx="8" cy="11" r="1.2" fill="white"/>
          <circle cx="12" cy="11" r="1.2" fill="white"/>
          <circle cx="16" cy="11" r="1.2" fill="white"/>
        </svg>
        <svg class="ai-fab-icon ai-fab-icon-close hidden" width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
        </svg>
        <span class="ai-fab-pulse"></span>
      </button>

      <!-- Chat panel -->
      <div id="aiAssistPanel" class="ai-panel hidden" role="dialog" aria-label="AI Writing Assistant">
        <!-- Header -->
        <div class="ai-panel-header">
          <div class="ai-panel-header-left">
            <div class="ai-panel-avatar">✦</div>
            <div>
              <div class="ai-panel-title">AI Assistant</div>
              <div class="ai-panel-subtitle" id="aiModeLabel">Test Generator</div>
            </div>
          </div>
          <div class="ai-panel-header-right">
            <button class="ai-icon-btn" id="aiClearBtn" title="Clear chat" aria-label="Clear chat">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
            <button class="ai-icon-btn" id="aiCloseBtn" title="Close" aria-label="Close assistant">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            </button>
          </div>
        </div>

        <!-- Messages -->
        <div class="ai-messages" id="aiMessages">
          <div class="ai-welcome" id="aiWelcome">
            <div class="ai-welcome-icon">✦</div>
            <p class="ai-welcome-title">AI Writing Assistant</p>
            <p class="ai-welcome-body">Describe your idea in plain language and I'll craft a proper description optimized for the current mode.</p>
            <div class="ai-mode-chips">
              <span class="ai-mode-chip active" data-mode="testgen">🧪 Test Gen</span>
              <span class="ai-mode-chip" data-mode="codereview">🔍 Code Review</span>
              <span class="ai-mode-chip" data-mode="rules">📋 Rules</span>
            </div>
          </div>
        </div>

        <!-- Input area -->
        <div class="ai-input-area">
          <textarea
            id="aiInput"
            class="ai-textarea"
            placeholder="Describe what you need…"
            rows="2"
            maxlength="2000"
            aria-label="Message to AI assistant"
          ></textarea>
          <div class="ai-input-footer">
            <span class="ai-char-count" id="aiCharCount">0 / 2000</span>
            <button class="ai-send-btn" id="aiSendBtn" aria-label="Send message" disabled>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(wrap);
  }

  /* ── Append a user bubble ───────────────────────────────────────────── */
  function appendUserBubble(content) {
    const container = document.getElementById('aiMessages');
    const welcome   = document.getElementById('aiWelcome');
    if (welcome) welcome.style.display = 'none';

    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-user';
    div.innerHTML = `<div class="ai-bubble ai-bubble-user">${esc(content)}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  /* ── Append assistant bubble with loading dots ──────────────────────── */
  function appendAssistantBubble(id) {
    const container = document.getElementById('aiMessages');

    const div = document.createElement('div');
    div.className = 'ai-msg ai-msg-assistant';
    div.id = id;
    div.innerHTML = `
      <div class="ai-bubble-wrap">
        <div class="ai-bubble ai-bubble-assistant" id="${id}-text">
          <span class="ai-loading-dots">
            <span></span><span></span><span></span>
          </span>
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
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  /* ── Finalize an assistant bubble after streaming ───────────────────── */
  function finalizeAssistantBubble(id, fullText) {
    const textEl    = document.getElementById(id + '-text');
    const actionsEl = document.getElementById(id + '-actions');
    if (textEl) textEl.innerHTML = fmt(fullText);
    if (actionsEl) actionsEl.style.display = '';

    // Wire copy
    const copyBtn = actionsEl?.querySelector('.ai-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        navigator.clipboard.writeText(fullText).then(() => {
          this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="#22c55e" stroke-width="2" stroke-linecap="round"/></svg> Copied!`;
          this.style.color = '#22c55e';
          setTimeout(() => {
            this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="1.8"/></svg> Copy`;
            this.style.color = '';
          }, 2000);
        });
      });
    }

    // Wire insert
    const insertBtn = actionsEl?.querySelector('.ai-insert-btn');
    if (insertBtn) {
      insertBtn.addEventListener('click', function () {
        const meta  = MODE_META[currentMode];
        const field = meta?.field ? document.getElementById(meta.field) : null;
        if (field) {
          field.value = fullText;
          field.dispatchEvent(new Event('input', { bubbles: true }));
          field.focus();
          if (typeof switchMode === 'function') switchMode(currentMode);
          this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="#22c55e" stroke-width="2" stroke-linecap="round"/></svg> Inserted!`;
          this.style.color = '#22c55e';
          setTimeout(() => {
            this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12l7 7 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg> Insert`;
            this.style.color = '';
          }, 2000);
        } else {
          navigator.clipboard.writeText(fullText);
          this.textContent = 'Copied!';
          setTimeout(() => { this.textContent = 'Insert'; }, 2000);
        }
      });
    }
  }

  /* ── Stream a response ───────────────────────────────────────────────── */
  async function streamResponse(userMsg) {
    if (isStreaming) return;
    isStreaming = true;

    const sendBtn = document.getElementById('aiSendBtn');
    if (sendBtn) sendBtn.disabled = true;

    appendUserBubble(userMsg);

    const msgId      = 'ai-resp-' + Date.now();
    let accumulated  = '';

    appendAssistantBubble(msgId);

    try {
      const res = await fetch('/api/assist/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          mode:    currentMode,
          history: history.slice(-6),
        }),
      });

      if (!res.ok) throw new Error('Assistant unavailable (HTTP ' + res.status + ')');

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   sseBuffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        sseBuffer += decoder.decode(value, { stream: true });

        // SSE messages are separated by \n\n
        const parts = sseBuffer.split('\n\n');
        sseBuffer = parts.pop() ?? '';   // keep incomplete last chunk

        for (const part of parts) {
          for (const line of part.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (raw === '[DONE]') break;
            try {
              const { token } = JSON.parse(raw);
              if (token) {
                accumulated += token;
                // Show partial text while streaming (replace dots after first token)
                const textEl = document.getElementById(msgId + '-text');
                if (textEl) {
                  textEl.innerHTML = fmt(accumulated) +
                    '<span class="ai-cursor">▍</span>';
                }
                const msgs = document.getElementById('aiMessages');
                if (msgs) msgs.scrollTop = msgs.scrollHeight;
              }
            } catch (_) { /* ignore malformed chunks */ }
          }
        }
      }

      // Save history
      history.push({ role: 'user',      content: userMsg });
      history.push({ role: 'assistant', content: accumulated });

      // Finalize bubble (remove cursor, show actions)
      finalizeAssistantBubble(msgId, accumulated);

    } catch (err) {
      const textEl    = document.getElementById(msgId + '-text');
      const actionsEl = document.getElementById(msgId + '-actions');
      if (textEl)    textEl.innerHTML = `<span style="color:#f87171">⚠️ ${esc(err.message || 'Something went wrong. Please try again.')}</span>`;
      if (actionsEl) actionsEl.style.display = 'none';
    } finally {
      isStreaming = false;
      const inp = document.getElementById('aiInput');
      if (sendBtn) sendBtn.disabled = !(inp && inp.value.trim());
    }
  }

  /* ── Toggle panel ────────────────────────────────────────────────────── */
  function togglePanel() {
    isOpen = !isOpen;
    const panel     = document.getElementById('aiAssistPanel');
    const fab       = document.getElementById('aiAssistFab');
    const iconChat  = fab?.querySelector('.ai-fab-icon-chat');
    const iconClose = fab?.querySelector('.ai-fab-icon-close');

    if (isOpen) {
      panel?.classList.remove('hidden');
      panel?.classList.add('ai-panel-open');
      if (iconChat)  iconChat.classList.add('hidden');
      if (iconClose) iconClose.classList.remove('hidden');
      fab?.classList.add('ai-fab-active');
      syncMode();
      setTimeout(() => document.getElementById('aiInput')?.focus(), 150);
    } else {
      panel?.classList.remove('ai-panel-open');
      panel?.classList.add('ai-panel-closing');
      setTimeout(() => {
        panel?.classList.add('hidden');
        panel?.classList.remove('ai-panel-closing');
      }, 250);
      if (iconChat)  iconChat.classList.remove('hidden');
      if (iconClose) iconClose.classList.add('hidden');
      fab?.classList.remove('ai-fab-active');
    }
  }

  /* ── Sync mode from app.js ───────────────────────────────────────────── */
  function syncMode() {
    const appMode = getAppMode();
    const meta    = MODE_META[appMode] || MODE_META.testgen;
    currentMode   = appMode;

    const label   = document.getElementById('aiModeLabel');
    const inp     = document.getElementById('aiInput');
    const chips   = document.querySelectorAll('.ai-mode-chip');

    if (label) label.textContent  = meta.label;
    if (inp)   inp.placeholder    = meta.hint;
    chips.forEach(c => c.classList.toggle('active', c.dataset.mode === currentMode));
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
      const msgs    = document.getElementById('aiMessages');
      const welcome = document.getElementById('aiWelcome');
      if (msgs) Array.from(msgs.querySelectorAll('.ai-msg')).forEach(el => el.remove());
      if (welcome) welcome.style.display = '';
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
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn?.disabled) sendBtn?.click();
      }
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
      if (inp)   inp.placeholder  = meta.hint;
      if (label) label.textContent = meta.label;
    });

    // Wrap app's switchMode so we keep in sync
    const origSwitch = window.switchMode;
    if (typeof origSwitch === 'function') {
      window.switchMode = function (mode) {
        origSwitch(mode);
        if (isOpen) syncMode();
      };
    }
    // Fallback polling for sync
    setInterval(() => { if (isOpen) syncMode(); }, 2000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
