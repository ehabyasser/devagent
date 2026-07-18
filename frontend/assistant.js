/* ═══════════════════════════════════════════════════════════════════════
   assistant.js — Floating AI writing assistant
   Context-aware chat that helps write feature descriptions, code review
   context, and rule definitions. Streams responses token by token.
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* ── State ──────────────────────────────────────────────────────────── */
  let isOpen = false;
  let isStreaming = false;
  let history = [];   // [{role, content}]
  let currentMode = 'testgen';

  const MODE_META = {
    testgen:    { label: 'Test Generator',  icon: '🧪', hint: 'Describe the feature or user story in your own words…', field: 'featureDescription' },
    codereview: { label: 'Code Review',     icon: '🔍', hint: 'Describe what the code change does…',                   field: 'crContext' },
    rules:      { label: 'Rules Manager',   icon: '📋', hint: 'Describe the coding standard you want to enforce…',    field: null },
  };

  /* ── Helpers ────────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s || '')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  function fmt(text) {
    // Minimal markdown: bold, italic, code, line breaks
    return esc(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>')
      .replace(/\n/g, '<br>');
  }

  /* ── Get current mode from app.js global ───────────────────────────── */
  function getAppMode() {
    // app.js exposes currentMode as a global
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

        <!-- Typing indicator (hidden by default) -->
        <div class="ai-typing hidden" id="aiTyping">
          <div class="ai-typing-dots">
            <span></span><span></span><span></span>
          </div>
          <span class="ai-typing-label">Thinking…</span>
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

  /* ── Render a message bubble ─────────────────────────────────────────── */
  function appendMessage(role, content, id) {
    const container = document.getElementById('aiMessages');
    const welcome = document.getElementById('aiWelcome');
    if (welcome) welcome.style.display = 'none';

    const div = document.createElement('div');
    div.className = `ai-msg ai-msg-${role}`;
    if (id) div.id = id;

    if (role === 'user') {
      div.innerHTML = `<div class="ai-bubble ai-bubble-user">${esc(content)}</div>`;
    } else {
      div.innerHTML = `
        <div class="ai-bubble-wrap">
          <div class="ai-bubble ai-bubble-assistant" id="${id}-text">${fmt(content)}</div>
          <div class="ai-bubble-actions">
            <button class="ai-action-btn ai-copy-btn" title="Copy to clipboard">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="1.8"/></svg>
              Copy
            </button>
            <button class="ai-action-btn ai-insert-btn" title="Insert into active field">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12l7 7 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              Insert
            </button>
          </div>
        </div>`;

      // Wire copy button
      div.querySelector('.ai-copy-btn').addEventListener('click', function () {
        const text = document.getElementById(id + '-text')?.innerText || content;
        navigator.clipboard.writeText(text).then(() => {
          this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="#22c55e" stroke-width="2" stroke-linecap="round"/></svg> Copied!`;
          this.style.color = '#22c55e';
          setTimeout(() => {
            this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="1.8"/></svg> Copy`;
            this.style.color = '';
          }, 2000);
        });
      });

      // Wire insert button
      div.querySelector('.ai-insert-btn').addEventListener('click', function () {
        const text = document.getElementById(id + '-text')?.innerText || content;
        const meta = MODE_META[currentMode];
        const fieldId = meta?.field;
        const field = fieldId ? document.getElementById(fieldId) : null;
        if (field) {
          field.value = text;
          field.dispatchEvent(new Event('input', { bubbles: true }));
          field.focus();
          // Switch to the right mode
          if (typeof switchMode === 'function') switchMode(currentMode);
          this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="#22c55e" stroke-width="2" stroke-linecap="round"/></svg> Inserted!`;
          this.style.color = '#22c55e';
          setTimeout(() => {
            this.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12l7 7 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg> Insert`;
            this.style.color = '';
          }, 2000);
        } else {
          // No field — just copy
          navigator.clipboard.writeText(text);
          this.textContent = 'Copied!';
          setTimeout(() => { this.textContent = 'Insert'; }, 2000);
        }
      });
    }

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
  }

  /* ── Stream a response ───────────────────────────────────────────────── */
  async function streamResponse(userMsg) {
    if (isStreaming) return;
    isStreaming = true;

    const sendBtn = document.getElementById('aiSendBtn');
    const typing  = document.getElementById('aiTyping');
    if (sendBtn) sendBtn.disabled = true;
    if (typing)  typing.classList.remove('hidden');

    // Add user bubble
    appendMessage('user', userMsg);

    // Prepare assistant bubble
    const msgId = 'ai-resp-' + Date.now();
    let accumulated = '';

    try {
      const res = await fetch('/api/assist/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          mode: currentMode,
          history: history.slice(-6),
        }),
      });

      if (!res.ok) throw new Error('Assistant unavailable');

      if (typing) typing.classList.add('hidden');
      const assistDiv = appendMessage('assistant', '', msgId);
      const textEl = document.getElementById(msgId + '-text');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') break;
          try {
            const { token } = JSON.parse(data);
            accumulated += token;
            if (textEl) textEl.innerHTML = fmt(accumulated);
            const msgs = document.getElementById('aiMessages');
            if (msgs) msgs.scrollTop = msgs.scrollHeight;
          } catch (_) {}
        }
      }

      // Save to history
      history.push({ role: 'user', content: userMsg });
      history.push({ role: 'assistant', content: accumulated });

    } catch (err) {
      if (typing) typing.classList.add('hidden');
      appendMessage('assistant', '⚠️ ' + (err.message || 'Something went wrong. Please try again.'), msgId);
    } finally {
      isStreaming = false;
      if (sendBtn) {
        const inp = document.getElementById('aiInput');
        sendBtn.disabled = !(inp && inp.value.trim());
      }
    }
  }

  /* ── Toggle panel open/close ─────────────────────────────────────────── */
  function togglePanel() {
    isOpen = !isOpen;
    const panel = document.getElementById('aiAssistPanel');
    const fab   = document.getElementById('aiAssistFab');
    const iconChat  = fab?.querySelector('.ai-fab-icon-chat');
    const iconClose = fab?.querySelector('.ai-fab-icon-close');

    if (isOpen) {
      panel?.classList.remove('hidden');
      panel?.classList.add('ai-panel-open');
      if (iconChat)  iconChat.classList.add('hidden');
      if (iconClose) iconClose.classList.remove('hidden');
      fab?.classList.add('ai-fab-active');
      // Sync mode
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
    const meta = MODE_META[appMode] || MODE_META.testgen;
    currentMode = appMode;

    const label = document.getElementById('aiModeLabel');
    const inp   = document.getElementById('aiInput');
    const chips = document.querySelectorAll('.ai-mode-chip');

    if (label) label.textContent = meta.label;
    if (inp)   inp.placeholder = meta.hint;
    chips.forEach(c => c.classList.toggle('active', c.dataset.mode === currentMode));
  }

  /* ── Init ────────────────────────────────────────────────────────────── */
  function init() {
    buildWidget();

    const fab     = document.getElementById('aiAssistFab');
    const closeBtn = document.getElementById('aiCloseBtn');
    const clearBtn = document.getElementById('aiClearBtn');
    const sendBtn  = document.getElementById('aiSendBtn');
    const input    = document.getElementById('aiInput');

    fab?.addEventListener('click', togglePanel);
    closeBtn?.addEventListener('click', togglePanel);

    clearBtn?.addEventListener('click', () => {
      history = [];
      const msgs = document.getElementById('aiMessages');
      const welcome = document.getElementById('aiWelcome');
      if (msgs) {
        // Remove all messages (keep welcome)
        Array.from(msgs.querySelectorAll('.ai-msg')).forEach(el => el.remove());
      }
      if (welcome) welcome.style.display = '';
    });

    input?.addEventListener('input', () => {
      const len = input.value.length;
      const cc = document.getElementById('aiCharCount');
      if (cc) cc.textContent = `${len} / 2000`;
      if (sendBtn) sendBtn.disabled = !input.value.trim() || isStreaming;
      // Auto-resize
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });

    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendBtn?.click();
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

    // Mode chips in welcome
    document.addEventListener('click', (e) => {
      const chip = e.target.closest('.ai-mode-chip');
      if (!chip) return;
      currentMode = chip.dataset.mode;
      document.querySelectorAll('.ai-mode-chip').forEach(c => c.classList.toggle('active', c === chip));
      const meta = MODE_META[currentMode];
      const inp = document.getElementById('aiInput');
      const label = document.getElementById('aiModeLabel');
      if (inp) inp.placeholder = meta.hint;
      if (label) label.textContent = meta.label;
    });

    // Watch app mode changes (patch switchMode)
    const origSwitch = window.switchMode;
    if (typeof origSwitch === 'function') {
      window.switchMode = function(mode) {
        origSwitch(mode);
        if (isOpen) syncMode();
      };
    }

    // Poll mode changes if switchMode not ready yet
    setInterval(() => { if (isOpen) syncMode(); }, 2000);
  }

  // Boot after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
