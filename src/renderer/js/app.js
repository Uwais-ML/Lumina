/**
 * src/renderer/js/app.js - Lumina Frontend Application State & Logic.
 *
 * Manages:
 * - Application state (conversations, messages, backend status, mode)
 * - Real-time streaming message rendering with incremental Markdown
 * - Intelligent auto-scroll during stream generation
 * - Navigation between views
 * - Conversation history load & display
 * - RAG ingestion, model loading, tools display
 * - Settings persistence
 * - Lumina logo glow as generation indicator
 */

'use strict';

// ── Markdown renderer (bundled marked.js via CDN or local) ────────────────────
// We use a lightweight marked-like parser to avoid external CDN deps in Electron
const simpleMarkdown = (() => {
  function escape(text) {
    return text.replace(/&/g, '&amp;')
               .replace(/</g, '&lt;')
               .replace(/>/g, '&gt;');
  }

  function renderInline(text) {
    // Bold, Italic, Code, Links
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>');
  }

  function render(markdown) {
    if (!markdown) return '';
    const lines = markdown.split('\n');
    const output = [];
    let inCodeBlock = false;
    let codeLang = '';
    let codeLines = [];
    let inList = false;
    let listItems = [];
    let listType = '';

    const flushList = () => {
      if (!inList) return;
      const tag = listType === 'ol' ? 'ol' : 'ul';
      output.push(`<${tag}>${listItems.map(i => `<li>${renderInline(i)}</li>`).join('')}</${tag}>`);
      listItems = [];
      inList = false;
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // Code fence
      if (line.startsWith('```')) {
        if (inCodeBlock) {
          output.push(`<pre><code class="language-${codeLang}">${escape(codeLines.join('\n'))}</code></pre>`);
          inCodeBlock = false; codeLines = []; codeLang = '';
        } else {
          flushList();
          inCodeBlock = true;
          codeLang = line.slice(3).trim() || 'plaintext';
        }
        continue;
      }
      if (inCodeBlock) { codeLines.push(line); continue; }

      // Headings
      const h3 = line.match(/^### (.+)/);
      const h2 = line.match(/^## (.+)/);
      const h1 = line.match(/^# (.+)/);
      if (h3) { flushList(); output.push(`<h3>${renderInline(h3[1])}</h3>`); continue; }
      if (h2) { flushList(); output.push(`<h2>${renderInline(h2[1])}</h2>`); continue; }
      if (h1) { flushList(); output.push(`<h1>${renderInline(h1[1])}</h1>`); continue; }

      // Blockquote
      if (line.startsWith('> ')) {
        flushList();
        output.push(`<blockquote>${renderInline(line.slice(2))}</blockquote>`);
        continue;
      }

      // Horizontal rule
      if (/^[-*_]{3,}$/.test(line.trim())) { flushList(); output.push('<hr>'); continue; }

      // Ordered list
      const olMatch = line.match(/^\d+\. (.+)/);
      if (olMatch) {
        if (!inList || listType !== 'ol') { flushList(); inList = true; listType = 'ol'; }
        listItems.push(olMatch[1]);
        continue;
      }
      // Unordered list
      const ulMatch = line.match(/^[-*+] (.+)/);
      if (ulMatch) {
        if (!inList || listType !== 'ul') { flushList(); inList = true; listType = 'ul'; }
        listItems.push(ulMatch[1]);
        continue;
      }

      flushList();

      // Empty line = paragraph break
      if (!line.trim()) { output.push('<br>'); continue; }

      output.push(`<p>${renderInline(escape(line))}</p>`);
    }
    flushList();
    if (inCodeBlock) {
      output.push(`<pre><code>${escape(codeLines.join('\n'))}</code></pre>`);
    }
    return output.join('');
  }

  return { render };
})();


// ── Application State ─────────────────────────────────────────────────────────
const state = {
  activeView: 'chat',
  activeConversationId: null,
  messages: [],            // Current conversation messages
  mode: 'chat',            // 'chat' | 'rag' | 'agentic'
  model: 'qwen',
  temperature: 0.7,
  maxTokens: 2048,
  isStreaming: false,
  currentStreamReqId: null,
  conversations: [],       // Loaded from backend
  backendReady: false,
  currentAssistantEl: null // The active streaming message element
};


// ── DOM Elements ──────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

const dom = {
  appLogo:          $('app-logo'),
  telemetryPill:    $('telemetry-pill'),
  statusDot:        $('status-dot'),
  statusModelName:  $('status-model-name'),
  statusTps:        $('status-tps'),
  navItems:         $$('.nav-item'),
  newChatBtn:       $('new-chat-btn'),
  conversationsList:$('conversations-list'),
  ramMeterFill:     $('ram-meter-fill'),
  ramMeterVal:      $('ram-meter-val'),
  viewChat:         $('view-chat'),
  welcomeScreen:    $('welcome-screen'),
  chatThread:       $('chat-thread'),
  messagesContainer:$('messages-container'),
  streamStatusBar:  $('stream-status-bar'),
  streamStatusText: $('stream-status-text'),
  stopGenBtn:       $('stop-gen-btn'),
  userInput:        $('user-input'),
  sendBtn:          $('send-btn'),
  modeBtns:         $$('.mode-btn'),
  modelSelect:      $('model-select'),
  starterCards:     $$('.starter-card'),
  metricModel:      $('metric-model'),
  metricPort:       $('metric-port'),
  metricTps:        $('metric-tps'),
  metricMode:       $('metric-mode'),
  modelsList:       $('models-list'),
  toolsGrid:        $('tools-grid'),
  ingestTitle:      $('ingest-title'),
  ingestContent:    $('ingest-content'),
  btnIngest:        $('btn-ingest'),
  ingestFeedback:   $('ingest-feedback'),
  settingBaseUrl:   $('setting-base-url'),
  settingTemp:      $('setting-temp'),
  tempValDisplay:   $('temp-val-display'),
  settingMaxTokens: $('setting-max-tokens'),
  btnSaveSettings:  $('btn-save-settings'),
  saveSettingsStatus:$('save-settings-status'),
  windowControls:   $('window-controls'),
  btnMinimize:      $('btn-minimize'),
  btnMaximize:      $('btn-maximize'),
  btnClose:         $('btn-close')
};


// ── Initialisation ─────────────────────────────────────────────────────────────
async function init() {
  setupPlatform();
  loadSettings();
  bindEventListeners();

  // Wait for backend bridge to be ready
  window.lumina.onBackendReady(() => {
    state.backendReady = true;
    console.log('[Lumina UI] Backend bridge ready.');
    refreshAll();
  });

  window.lumina.onBackendStatus((data) => {
    if (data.status === 'stopped') {
      setTelemetry(false, 'Offline', '-- T/s');
    }
  });

  // Attempt early poll (bridge may already be ready from a prior preload)
  setTimeout(() => {
    if (!state.backendReady) refreshAll();
  }, 1200);

  // Periodic system status poll every 8s
  setInterval(pollStatus, 8000);
}


function setupPlatform() {
  if (window.lumina.platform === 'darwin') {
    document.body.classList.add('platform-darwin');
  }
}


function loadSettings() {
  try {
    const saved = localStorage.getItem('lumina_settings');
    if (saved) {
      const s = JSON.parse(saved);
      if (s.temperature !== undefined) state.temperature = s.temperature;
      if (s.maxTokens    !== undefined) state.maxTokens    = s.maxTokens;
      if (s.model        !== undefined) state.model        = s.model;
    }
  } catch (e) { /* ignore */ }

  // Apply to DOM
  if (dom.settingTemp)       dom.settingTemp.value        = state.temperature;
  if (dom.tempValDisplay)    dom.tempValDisplay.textContent = state.temperature;
  if (dom.settingMaxTokens)  dom.settingMaxTokens.value   = state.maxTokens;
}


function saveSettings() {
  state.temperature = parseFloat(dom.settingTemp.value);
  state.maxTokens   = parseInt(dom.settingMaxTokens.value) || 2048;
  localStorage.setItem('lumina_settings', JSON.stringify({
    temperature: state.temperature,
    maxTokens:   state.maxTokens,
    model:       state.model
  }));
  dom.saveSettingsStatus.textContent = '✓ Saved';
  setTimeout(() => { dom.saveSettingsStatus.textContent = ''; }, 2000);
}


// ── Event Listeners ────────────────────────────────────────────────────────────
function bindEventListeners() {
  // Navigation
  dom.navItems.forEach(item => {
    item.addEventListener('click', () => {
      const view = item.dataset.view;
      if (view) switchView(view);
    });
  });

  // New Chat
  dom.newChatBtn.addEventListener('click', startNewChat);

  // Mode toggles
  dom.modeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      dom.modeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.mode = btn.dataset.mode;
    });
  });

  // Model select
  if (dom.modelSelect) {
    dom.modelSelect.addEventListener('change', () => {
      state.model = dom.modelSelect.value;
    });
  }

  // Input auto-resize
  dom.userInput.addEventListener('input', autoResizeTextarea);

  // Send on Enter (Shift+Enter = newline)
  dom.userInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Send button
  dom.sendBtn.addEventListener('click', handleSend);

  // Starter cards
  dom.starterCards.forEach(card => {
    card.addEventListener('click', () => {
      const prompt = card.dataset.prompt;
      if (prompt) {
        dom.userInput.value = prompt;
        autoResizeTextarea();
        switchView('chat');
        handleSend();
      }
    });
  });

  // Stop generation
  if (dom.stopGenBtn) {
    dom.stopGenBtn.addEventListener('click', stopGeneration);
  }

  // RAG ingest
  if (dom.btnIngest) {
    dom.btnIngest.addEventListener('click', handleRagIngest);
  }

  // Settings
  if (dom.settingTemp) {
    dom.settingTemp.addEventListener('input', () => {
      const val = parseFloat(dom.settingTemp.value).toFixed(2);
      dom.tempValDisplay.textContent = val;
    });
  }
  if (dom.btnSaveSettings) {
    dom.btnSaveSettings.addEventListener('click', saveSettings);
  }

  // Kill active model
  const btnKill = $('btn-kill-active-model');
  if (btnKill) {
    btnKill.addEventListener('click', async () => {
      btnKill.textContent = '⏳ Stopping...';
      btnKill.disabled = true;
      try {
        await window.lumina.killModel();
        btnKill.textContent = '✓ Killed';
        setTimeout(() => { btnKill.textContent = '■ Kill Model'; btnKill.disabled = false; }, 2000);
        pollStatus();
      } catch (err) {
        btnKill.textContent = 'Error';
        setTimeout(() => { btnKill.textContent = '■ Kill Model'; btnKill.disabled = false; }, 2000);
      }
    });
  }

  // Trigger SmartSwitch
  const btnSwitch = $('btn-trigger-smartswitch');
  if (btnSwitch) {
    btnSwitch.addEventListener('click', async () => {
      btnSwitch.textContent = '⏳ Switching...';
      btnSwitch.disabled = true;
      try {
        await window.lumina.triggerSmartswitch();
        btnSwitch.textContent = '✓ Switched';
        setTimeout(() => { btnSwitch.textContent = '⚡ SmartSwitch'; btnSwitch.disabled = false; }, 2000);
        pollStatus();
      } catch (err) {
        btnSwitch.textContent = 'Error';
        setTimeout(() => { btnSwitch.textContent = '⚡ SmartSwitch'; btnSwitch.disabled = false; }, 2000);
      }
    });
  }

  // System Assess
  const btnAssess = $('btn-run-assess');
  if (btnAssess) {
    btnAssess.addEventListener('click', runSystemAssess);
  }

  // Window controls
  if (dom.btnMinimize) dom.btnMinimize.addEventListener('click', () => window.lumina.minimizeWindow());
  if (dom.btnMaximize) dom.btnMaximize.addEventListener('click', () => window.lumina.maximizeWindow());
  if (dom.btnClose)    dom.btnClose.addEventListener('click',    () => window.lumina.closeWindow());

  // IDE Studio controls
  bindIdeControls();

  // Custom tool creator controls
  bindToolCreationControls();
}


// ── View Navigation ────────────────────────────────────────────────────────────
function switchView(viewId) {
  state.activeView = viewId;

  // Update nav items
  dom.navItems.forEach(item => {
    item.classList.toggle('active', item.dataset.view === viewId);
  });

  // Toggle workspace views
  $$('.workspace-view').forEach(v => {
    v.classList.toggle('active', v.id === `view-${viewId}`);
  });

  // Lazy-load view data
  if (viewId === 'models')   loadModels();
  if (viewId === 'store')    loadModelStore();
  if (viewId === 'ide')      updateLineNumbers();
  if (viewId === 'tools')    loadTools();
  if (viewId === 'settings') {/* already bound */}
}


// ── Refresh All ────────────────────────────────────────────────────────────────
async function refreshAll() {
  await Promise.allSettled([
    loadConversations(),
    pollStatus()
  ]);
}


// ── Status Polling ─────────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const data = await window.lumina.getStatus();
    const active = data?.active_model;
    const sys    = data?.system;

    const isAlive = !!active?.model;
    const modelLabel = active?.model || 'No model active';
    const tps  = active?.tps ? `${active.tps.toFixed(1)} T/s` : '-- T/s';

    setTelemetry(isAlive, modelLabel, tps);

    if (dom.metricModel) dom.metricModel.textContent = modelLabel;
    if (dom.metricPort)  dom.metricPort.textContent  = active?.port || data?.port || '54993';
    if (dom.metricTps)   dom.metricTps.textContent   = tps;
    if (dom.metricMode)  dom.metricMode.textContent  = active?.mode || 'RAM';

    if (sys && dom.ramMeterFill) {
      const pct = sys.ram_percent || 0;
      dom.ramMeterFill.style.width = `${pct}%`;
      dom.ramMeterVal.textContent  = `${Math.round(pct)}%`;
    }
  } catch (e) {
    // Backend not yet ready — silent
  }
}


function setTelemetry(alive, modelName, tps) {
  if (!dom.telemetryPill) return;
  dom.telemetryPill.classList.toggle('alive', alive);
  dom.statusModelName.textContent = modelName.length > 22 ? modelName.slice(0, 22) + '…' : modelName;
  dom.statusTps.textContent       = tps;
}


// ── Conversation Management ───────────────────────────────────────────────────
async function loadConversations() {
  try {
    const convs = await window.lumina.listConversations();
    state.conversations = convs || [];
    renderConversationsList();
  } catch (e) {
    console.warn('[Lumina UI] loadConversations error:', e);
  }
}


function renderConversationsList() {
  if (!dom.conversationsList) return;
  const convs = state.conversations;

  if (!convs.length) {
    dom.conversationsList.innerHTML = '<div class="conv-empty">No conversations yet</div>';
    return;
  }

  dom.conversationsList.innerHTML = '';
  convs.forEach(conv => {
    const item = document.createElement('div');
    item.className = 'conv-item' + (conv.id === state.activeConversationId ? ' active' : '');
    item.dataset.id = conv.id;

    const dot = document.createElement('span');
    dot.className = 'conv-dot';

    const title = document.createElement('span');
    title.className = 'conv-title';
    title.textContent = conv.title || 'Untitled Chat';
    title.title = conv.title || '';

    const delBtn = document.createElement('button');
    delBtn.className = 'conv-delete';
    delBtn.title = 'Delete conversation';
    delBtn.textContent = '×';
    delBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      await deleteConversation(conv.id);
    });

    item.appendChild(dot);
    item.appendChild(title);
    item.appendChild(delBtn);
    item.addEventListener('click', () => loadConversation(conv.id));
    dom.conversationsList.appendChild(item);
  });
}


async function loadConversation(convId) {
  try {
    const conv = await window.lumina.getConversation(convId);
    if (!conv) return;

    state.activeConversationId = convId;
    state.messages = conv.messages || [];
    state.mode = conv.mode || 'chat';

    // Update active mode button
    dom.modeBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === state.mode);
    });

    switchView('chat');
    renderFullConversation();
    renderConversationsList();
    scrollToBottom(true);
  } catch (e) {
    console.error('[Lumina UI] loadConversation error:', e);
  }
}


async function deleteConversation(convId) {
  try {
    await window.lumina.deleteConversation(convId);
    state.conversations = state.conversations.filter(c => c.id !== convId);
    if (state.activeConversationId === convId) {
      startNewChat();
    }
    renderConversationsList();
  } catch (e) {
    console.error('[Lumina UI] deleteConversation error:', e);
  }
}


function startNewChat() {
  state.activeConversationId = null;
  state.messages = [];
  state.isStreaming = false;
  state.currentAssistantEl = null;

  // Clear thread, show welcome
  if (dom.chatThread) dom.chatThread.innerHTML = '';
  if (dom.welcomeScreen) dom.welcomeScreen.classList.remove('hidden');

  // Reset input
  dom.userInput.value = '';
  dom.userInput.style.height = '';
  dom.sendBtn.disabled = false;

  setStreamStatus(false);
  setLogoGenerating(false);

  renderConversationsList();
  switchView('chat');
  dom.userInput.focus();
}


// ── Rendering Full Conversation ────────────────────────────────────────────────
function renderFullConversation() {
  if (!dom.chatThread) return;
  dom.chatThread.innerHTML = '';
  if (dom.welcomeScreen) dom.welcomeScreen.classList.add('hidden');

  state.messages.forEach(msg => {
    if (msg.role === 'user') {
      appendUserMessage(msg.content);
    } else if (msg.role === 'assistant') {
      const el = appendAssistantMessage();
      finaliseAssistantMessage(el, msg.content, msg.sources || [], msg.tools || []);
    }
  });
}


// ── Message Rendering ─────────────────────────────────────────────────────────
function appendUserMessage(content) {
  if (dom.welcomeScreen && !dom.welcomeScreen.classList.contains('hidden')) {
    dom.welcomeScreen.classList.add('hidden');
  }

  const row = document.createElement('div');
  row.className = 'message-row user';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble-user';
  bubble.textContent = content;

  row.appendChild(bubble);
  dom.chatThread.appendChild(row);
  return row;
}


function appendAssistantMessage() {
  const row = document.createElement('div');
  row.className = 'message-row assistant';

  const header = document.createElement('div');
  header.className = 'assistant-header';

  const avatar = document.createElement('div');
  avatar.className = 'assistant-avatar';
  avatar.innerHTML = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;

  const name = document.createElement('span');
  name.className = 'assistant-name';
  name.textContent = 'Lumina';

  header.appendChild(avatar);
  header.appendChild(name);

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble-assistant';

  // Streaming cursor
  const cursor = document.createElement('span');
  cursor.className = 'streaming-cursor';
  cursor.id = 'streaming-cursor-active';
  bubble.appendChild(cursor);

  row.appendChild(header);
  row.appendChild(bubble);
  dom.chatThread.appendChild(row);

  return { row, bubble, cursor };
}


function appendStreamDelta(elRef, delta) {
  // Accumulate raw text, then render markdown on the bubble
  if (!elRef) return;
  if (!elRef._rawText) elRef._rawText = '';
  elRef._rawText += delta;

  // Remove cursor temporarily, re-render, re-add cursor
  const cursor = elRef.cursor;
  if (cursor && cursor.parentElement) cursor.parentElement.removeChild(cursor);

  elRef.bubble.innerHTML = simpleMarkdown.render(elRef._rawText);

  // Re-append cursor to signal ongoing stream
  elRef.bubble.appendChild(cursor);
}


function finaliseAssistantMessage(elRef, fullText, sources, tools) {
  if (!elRef) return;
  const cursor = document.getElementById('streaming-cursor-active');
  if (cursor) cursor.remove();

  if (elRef.bubble) {
    elRef.bubble.innerHTML = simpleMarkdown.render(fullText || '');
  }

  // Sources
  if (sources && sources.length > 0) {
    const srcRow = document.createElement('div');
    srcRow.className = 'sources-row';
    sources.forEach(src => {
      const chip = document.createElement('span');
      chip.className = 'source-chip';
      chip.innerHTML = `📄 ${src}`;
      srcRow.appendChild(chip);
    });
    elRef.bubble.appendChild(srcRow);
  }
}


function appendToolEvent(tool, args, result) {
  const row = document.createElement('div');
  row.className = 'tool-event-row';
  row.innerHTML = `
    <span class="tool-event-icon">⚙️</span>
    <div class="tool-event-detail">
      <strong>${tool}</strong>(${(args || []).join(', ')})
      <div class="tool-event-result">${result || ''}</div>
    </div>
  `;
  dom.chatThread.appendChild(row);
}


function appendErrorMessage(errorText) {
  const div = document.createElement('div');
  div.className = 'message-error';
  div.innerHTML = `<span class="message-error-icon">⚠️</span><span>${errorText}</span>`;
  dom.chatThread.appendChild(div);
}


// ── Send Message ──────────────────────────────────────────────────────────────
async function handleSend() {
  const content = dom.userInput.value.trim();
  if (!content || state.isStreaming) return;

  // Ensure a conversation ID exists
  if (!state.activeConversationId) {
    state.activeConversationId = `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  // Build message list for backend
  const userMessage = { role: 'user', content };
  state.messages.push(userMessage);

  // Clear input immediately
  dom.userInput.value = '';
  dom.userInput.style.height = '';

  // Render user bubble
  appendUserMessage(content);

  // Create assistant placeholder
  const assistantEl = appendAssistantMessage();
  state.currentAssistantEl = assistantEl;

  // Scroll down
  scrollToBottom();

  // Set streaming state
  state.isStreaming = true;
  dom.sendBtn.disabled = true;
  setStreamStatus(true, 'Lumina is thinking...');
  setLogoGenerating(true);

  let fullResponseText = '';
  let completeSources = [];
  let completeTools = [];

  const payload = {
    conversation_id: state.activeConversationId,
    messages: state.messages.map(m => ({ role: m.role, content: m.content })),
    mode: state.mode,
    model: state.model,
    temperature: state.temperature,
    max_tokens: state.maxTokens
  };

  try {
    await window.lumina.sendMessage(payload, (event) => {
      if (!state.isStreaming) return; // Cancelled

      switch (event.type) {
        case 'message:start':
          state.currentStreamReqId = event.id;
          break;

        case 'message:status':
          setStreamStatus(true, event.detail || 'Lumina is processing...');
          break;

        case 'message:delta':
          fullResponseText += event.delta || '';
          appendStreamDelta(assistantEl, event.delta || '');
          scrollToBottomIfNearBottom();
          break;

        case 'message:tool':
          appendToolEvent(event.tool, event.args, event.result);
          completeTools.push(event);
          scrollToBottom();
          break;

        case 'message:complete':
          completeSources = event.sources || [];
          completeTools   = event.tools   || [];
          finaliseAssistantMessage(assistantEl, event.full_text || fullResponseText, completeSources, completeTools);
          break;

        case 'message:error':
          finaliseAssistantMessage(assistantEl, event.partial_text || '', [], []);
          appendErrorMessage(event.error || 'An error occurred.');
          break;
      }
    });
  } catch (err) {
    appendErrorMessage(`Connection error: ${err.message}`);
  } finally {
    // Add assistant message to local state
    const assistantMessage = {
      role: 'assistant',
      content: fullResponseText,
      sources: completeSources,
      tools: completeTools
    };
    state.messages.push(assistantMessage);

    // Reset streaming UI
    state.isStreaming = false;
    state.currentStreamReqId = null;
    state.currentAssistantEl = null;
    dom.sendBtn.disabled = false;
    setStreamStatus(false);
    setLogoGenerating(false);

    // Refresh conversation list to show updated title
    loadConversations();
    scrollToBottom();
  }
}


function stopGeneration() {
  if (!state.isStreaming) return;
  state.isStreaming = false;

  const cursor = document.getElementById('streaming-cursor-active');
  if (cursor) cursor.remove();

  dom.sendBtn.disabled = false;
  setStreamStatus(false);
  setLogoGenerating(false);
}


// ── UI Helpers ─────────────────────────────────────────────────────────────────
function setStreamStatus(visible, text = 'Lumina is generating...') {
  if (!dom.streamStatusBar) return;
  dom.streamStatusBar.classList.toggle('visible', visible);
  if (dom.streamStatusText) dom.streamStatusText.textContent = text;
}


function setLogoGenerating(active) {
  if (!dom.appLogo) return;
  dom.appLogo.classList.toggle('generating', active);
}


function autoResizeTextarea() {
  const el = dom.userInput;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 180) + 'px';
}


let _scrollLocked = false;
function scrollToBottom(force = false) {
  const container = dom.messagesContainer;
  if (!container) return;
  container.scrollTop = container.scrollHeight;
}


function scrollToBottomIfNearBottom() {
  const container = dom.messagesContainer;
  if (!container) return;
  const threshold = 180;
  const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  if (atBottom) container.scrollTop = container.scrollHeight;
}


// ── Models View ────────────────────────────────────────────────────────────────
async function loadModels() {
  if (!dom.modelsList) return;
  try {
    const data = await window.lumina.listModels();
    const locals = data?.local || [];

    // Populate model select
    if (dom.modelSelect) {
      dom.modelSelect.innerHTML = '';
      if (locals.length) {
        locals.forEach(m => {
          const opt = document.createElement('option');
          opt.value = m.name;
          opt.textContent = m.name;
          dom.modelSelect.appendChild(opt);
        });
      } else {
        const opt = document.createElement('option');
        opt.value = 'qwen';
        opt.textContent = 'qwen (Default)';
        dom.modelSelect.appendChild(opt);
      }
    }

    if (!locals.length) {
      dom.modelsList.innerHTML = '<div class="list-placeholder">No GGUF models found in models/. Run ./lumina --setup to download base models.</div>';
      return;
    }

    dom.modelsList.innerHTML = '';
    locals.forEach(model => {
      const item = document.createElement('div');
      item.className = 'model-item';
      item.innerHTML = `
        <span class="model-icon">🧠</span>
        <div class="model-info">
          <div class="model-name">${model.name}</div>
          <div class="model-size">${model.size_mb} MB</div>
        </div>
        <button class="model-launch-btn" data-model="${model.name}">▶ Launch</button>
      `;
      const btn = item.querySelector('.model-launch-btn');
      btn.addEventListener('click', () => launchModel(model.name));
      dom.modelsList.appendChild(item);
    });
  } catch (e) {
    dom.modelsList.innerHTML = '<div class="list-placeholder">Failed to load models.</div>';
  }
}


async function launchModel(modelName) {
  try {
    const btn = dom.modelsList.querySelector(`[data-model="${modelName}"]`);
    if (btn) { btn.textContent = '⏳ Launching...'; btn.disabled = true; }

    const result = await window.lumina.launchModel(modelName);
    if (result?.port) {
      if (btn) { btn.textContent = '✓ Running'; btn.disabled = false; }
      pollStatus();
    }
  } catch (e) {
    console.error('[Lumina UI] launchModel error:', e);
  }
}


// ── System Assess & Hardware Benchmark ─────────────────────────────────────────
async function runSystemAssess() {
  const container = $('assess-results-container');
  const btn = $('btn-run-assess');
  if (btn) { btn.textContent = '⏳ Evaluating...'; btn.disabled = true; }
  if (container) container.innerHTML = '<div class="list-placeholder">Measuring RAM bandwidth & calculating model fit...</div>';

  try {
    const data = await window.lumina.systemAssess();
    if (!data || !container) return;
    const models = data.models || [];
    let html = `
      <div style="font-size: 12px; margin-bottom: 12px; color: var(--text-muted);">
        CPU Cores: <strong>${data.cpu_cores}</strong> | Total RAM: <strong>${data.ram_total_gb} GB</strong> | Free: <strong style="color:var(--emerald);">${data.ram_free_gb} GB</strong>
      </div>
    `;

    if (models.length) {
      models.forEach(m => {
        html += `
          <div class="assess-row">
            <div>
              <div class="assess-name">${m.name}</div>
              <div style="font-size: 11px; color: var(--text-muted);">${m.size_mb} MB</div>
            </div>
            <div style="text-align: right;">
              <span class="${m.fits_ram ? 'assess-tag-fit' : 'assess-tag-warn'}">
                ${m.fits_ram ? '✓ Fits in Memory' : '⚠️ Memory Pressure'}
              </span>
              <div class="assess-tps">~${m.estimated_tps} T/s est.</div>
            </div>
          </div>
        `;
      });
    } else {
      html += '<div class="list-placeholder">No local models found to assess.</div>';
    }
    container.innerHTML = html;
  } catch (err) {
    if (container) container.innerHTML = `<div class="list-placeholder" style="color:var(--rose);">Assess failed: ${err.message}</div>`;
  } finally {
    if (btn) { btn.textContent = '🔬 Run Assess'; btn.disabled = false; }
  }
}


// ── Model Store & Catalog ──────────────────────────────────────────────────────
async function loadModelStore() {
  const grid = $('store-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="list-placeholder">Loading model catalog from HuggingFace index...</div>';

  try {
    const data = await window.lumina.listModels();
    const catalog = data?.catalog || [];

    if (!catalog.length) {
      grid.innerHTML = '<div class="list-placeholder">No catalog entries found in resources/llmstore.json</div>';
      return;
    }

    grid.innerHTML = '';
    catalog.forEach(item => {
      const card = document.createElement('div');
      card.className = 'store-card';
      card.innerHTML = `
        <div>
          <div class="store-title">${item.filename_pattern || item.name}</div>
          <div class="store-meta" style="margin-top: 6px;">
            <span class="chip chip-indigo">${item.parameters || 'LLM'}</span>
            <span class="chip chip-cyan">${item.quantization || 'GGUF'}</span>
          </div>
          <p class="store-pros" style="margin-top: 8px;">${item.pros || ''}</p>
        </div>
        <div style="margin-top: 10px;">
          <button class="store-btn" data-repo="${item.name}" data-file="${item.filename_pattern}">
            ⬇ Download (${item.parameters || 'GGUF'})
          </button>
        </div>
      `;

      const btn = card.querySelector('.store-btn');
      btn.addEventListener('click', async () => {
        btn.textContent = '⏳ Downloading...';
        btn.disabled = true;
        const feedback = $('store-feedback');
        if (feedback) feedback.textContent = `Downloading ${item.filename_pattern}...`;

        try {
          await window.lumina.downloadModel({ repo_id: item.name, filename: item.filename_pattern });
          btn.textContent = '✓ Downloaded';
          if (feedback) feedback.textContent = `✓ ${item.filename_pattern} downloaded to models/`;
          loadModels();
        } catch (err) {
          btn.textContent = 'Error';
          btn.disabled = false;
          if (feedback) feedback.textContent = `Download failed: ${err.message}`;
        }
      });

      grid.appendChild(card);
    });
  } catch (err) {
    grid.innerHTML = `<div class="list-placeholder" style="color:var(--rose);">Failed to load store: ${err.message}</div>`;
  }
}


// ── Tools View ─────────────────────────────────────────────────────────────────
async function loadTools() {
  const grid = $('tools-grid');
  if (!grid) return;
  try {
    const tools = await window.lumina.listTools();
    if (!tools || !tools.length) {
      grid.innerHTML = '<div class="list-placeholder">No tools found in Tools/ directory.</div>';
      return;
    }
    grid.innerHTML = '';
    tools.forEach(t => {
      const card = document.createElement('div');
      card.className = 'tool-card';
      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div class="tool-name">${t.name}</div>
          <button class="conv-delete" data-tool="${t.name}" title="Delete tool" style="opacity:0.6;">✕</button>
        </div>
        <div class="tool-desc">${t.description || 'Python tool module'}</div>
      `;
      const delBtn = card.querySelector('.conv-delete');
      if (delBtn) {
        delBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (confirm(`Delete custom tool '${t.name}'?`)) {
            await window.lumina.deleteTool(t.name);
            loadTools();
          }
        });
      }
      grid.appendChild(card);
    });
  } catch (e) {
    grid.innerHTML = '<div class="list-placeholder">Failed to load tools.</div>';
  }
}

function bindToolCreationControls() {
  const saveBtn = $('btn-save-custom-tool');
  const refreshBtn = $('btn-refresh-tools');
  const feedback = $('tool-create-feedback');

  if (refreshBtn) {
    refreshBtn.addEventListener('click', loadTools);
  }

  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const nameInput = $('tool-name-input');
      const descInput = $('tool-desc-input');
      const codeInput = $('tool-code-input');

      const name = nameInput?.value?.trim();
      const desc = descInput?.value?.trim() || 'Custom user tool';
      const code = codeInput?.value?.trim();

      if (!name || !code) {
        if (feedback) {
          feedback.textContent = 'Please provide both tool name and Python code.';
          feedback.style.color = 'var(--rose)';
        }
        return;
      }

      saveBtn.disabled = true;
      saveBtn.textContent = '⏳ Saving...';

      try {
        await window.lumina.createTool({ name, description: desc, code });
        if (feedback) {
          feedback.textContent = `✓ Tool '${name}.py' registered successfully!`;
          feedback.style.color = 'var(--emerald)';
        }
        if (nameInput) nameInput.value = '';
        if (descInput) descInput.value = '';
        if (codeInput) codeInput.value = '';
        loadTools();
      } catch (err) {
        if (feedback) {
          feedback.textContent = `Error: ${err.message}`;
          feedback.style.color = 'var(--rose)';
        }
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = '➕ Register Custom Tool';
      }
    });
  }
}


// ── RAG Ingest ─────────────────────────────────────────────────────────────────
async function handleRagIngest() {
  const text = dom.ingestContent?.value?.trim();
  const title = dom.ingestTitle?.value?.trim() || 'custom_document.txt';
  if (!text) {
    dom.ingestFeedback.textContent = 'Please enter document content.';
    dom.ingestFeedback.className = 'ingest-feedback error';
    return;
  }

  dom.btnIngest.disabled = true;
  dom.ingestFeedback.textContent = '⏳ Ingesting into vector store...';
  dom.ingestFeedback.className = 'ingest-feedback';

  try {
    const result = await window.lumina.ragIngest(text, title);
    if (result?.chunks) {
      dom.ingestFeedback.textContent = `✓ Ingested! ${result.chunks} chunks created in Chroma DB.`;
      dom.ingestFeedback.className = 'ingest-feedback success';
      dom.ingestContent.value = '';
      dom.ingestTitle.value = '';
    } else {
      throw new Error('Unexpected response from RAG ingest');
    }
  } catch (e) {
    dom.ingestFeedback.textContent = `⚠ Failed to ingest: ${e.message}`;
    dom.ingestFeedback.className = 'ingest-feedback error';
  } finally {
    dom.btnIngest.disabled = false;
  }
}


// ── VS Code Style Code Studio (IDE) ─────────────────────────────────────────
function updateLineNumbers() {
  const editor = $('ide-code-editor');
  const numbersEl = $('ide-line-numbers');
  if (!editor || !numbersEl) return;
  const lineCount = (editor.value.match(/\n/g) || []).length + 1;
  let nums = '';
  for (let i = 1; i <= Math.max(lineCount, 15); i++) {
    nums += i + '<br>';
  }
  numbersEl.innerHTML = nums;
}

function bindIdeControls() {
  const editor = $('ide-code-editor');
  const runBtn = $('ide-run-btn');
  const autoBtn = $('ide-autocomplete-btn');
  const askBtn = $('ide-ask-model-btn');
  const clearBtn = $('ide-clear-output-btn');
  const outputEl = $('ide-output-body');
  const statusEl = $('ide-status');

  if (!editor) return;

  // Sync line numbers on typing & scroll
  editor.addEventListener('input', updateLineNumbers);
  editor.addEventListener('scroll', () => {
    const numbersEl = $('ide-line-numbers');
    if (numbersEl) numbersEl.scrollTop = editor.scrollTop;
  });

  // Tab key indents code with 4 spaces instead of losing focus
  editor.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
      editor.selectionStart = editor.selectionEnd = start + 4;
      updateLineNumbers();
    }
    // Shift+F triggers LLM autocomplete inline
    if (e.shiftKey && (e.key === 'F' || e.key === 'f')) {
      e.preventDefault();
      triggerIdeAutocomplete();
    }
  });

  // Run Code button
  if (runBtn) {
    runBtn.addEventListener('click', async () => {
      const code = editor.value.trim();
      if (!code) return;
      runBtn.textContent = '⏳ Executing…';
      runBtn.disabled = true;
      if (statusEl) statusEl.textContent = 'Running code in Python environment…';
      if (outputEl) outputEl.textContent += `\n\n$ python3 -c script.py\n`;

      try {
        const res = await window.lumina.executeCode(code);
        if (outputEl) {
          outputEl.textContent += res?.output || '(Completed with no output)';
          outputEl.scrollTop = outputEl.scrollHeight;
        }
        if (statusEl) statusEl.textContent = `Process finished (exit code: ${res?.exit_code ?? 0})`;
      } catch (err) {
        if (outputEl) outputEl.textContent += `\n❌ Error: ${err.message}`;
        if (statusEl) statusEl.textContent = 'Execution failed';
      } finally {
        runBtn.textContent = '▶ Run Code';
        runBtn.disabled = false;
      }
    });
  }

  // Clear output
  if (clearBtn && outputEl) {
    clearBtn.addEventListener('click', () => {
      outputEl.textContent = '// Console cleared.';
    });
  }

  // Autocomplete button (Shift+F)
  if (autoBtn) {
    autoBtn.addEventListener('click', triggerIdeAutocomplete);
  }

  // Ask Model About Selection button
  if (askBtn) {
    askBtn.addEventListener('click', () => {
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      let selectedText = editor.value.substring(start, end).trim();

      // If no text explicitly highlighted, grab the full editor script
      if (!selectedText) {
        selectedText = editor.value.trim();
      }

      if (!selectedText) {
        if (statusEl) statusEl.textContent = 'No code to inspect! Write or select some code first.';
        return;
      }

      // Switch to Chat view and auto-fill prompt asking Lumina to analyze code
      switchView('chat');
      const prompt = `Here is a code snippet from the Lumina IDE Studio:\n\n\`\`\`python\n${selectedText}\n\`\`\`\n\nCan you explain what this code does, check for bugs or edge cases, and suggest improvements?`;
      if (dom.userInput) {
        dom.userInput.value = prompt;
        autoResizeTextarea();
        handleSend();
      }
    });
  }
}

async function triggerIdeAutocomplete() {
  const editor = $('ide-code-editor');
  const statusEl = $('ide-status');
  const autoBtn = $('ide-autocomplete-btn');
  if (!editor) return;

  const cursorPos = editor.selectionStart;
  const prefix = editor.value.substring(0, cursorPos);
  if (prefix.trim().length < 3) {
    if (statusEl) statusEl.textContent = 'Write at least 3 characters to autocomplete.';
    return;
  }

  if (autoBtn) { autoBtn.textContent = '⏳ Completing…'; autoBtn.disabled = true; }
  if (statusEl) statusEl.textContent = 'Querying local model for completion…';

  try {
    const res = await window.lumina.completeCode(prefix, 48);
    const completion = res?.completion || '';
    if (completion) {
      const after = editor.value.substring(cursorPos);
      editor.value = prefix + completion + after;
      editor.selectionStart = editor.selectionEnd = cursorPos + completion.length;
      updateLineNumbers();
      if (statusEl) statusEl.textContent = '✓ Completed! (Tab/Shift+F to continue)';
    } else {
      if (statusEl) statusEl.textContent = 'No completion returned by model.';
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = `Autocomplete error: ${err.message}`;
  } finally {
    if (autoBtn) { autoBtn.textContent = '⚡ Autocomplete (Shift+F)'; autoBtn.disabled = false; }
  }
}


// ── Sun L Loader Animation ──────────────────────────────────────────────────
function initSunLoader(canvasId, options = {}) {
  const cv = document.getElementById(canvasId);
  if (!cv) return null;
  const ctx = cv.getContext('2d');
  let W, H, R, dpr, circ = [], ell = [];
  const N = 240, T = 8;
  const scaleMult = options.scaleMultiplier || 0.28;
  const bgColor = options.bg || null;

  function build() {
    dpr = window.devicePixelRatio || 1;
    W = cv.clientWidth || 120;
    H = cv.clientHeight || 120;
    cv.width = W * dpr;
    cv.height = H * dpr;
    R = Math.min(W, H) * scaleMult;
    circ = [];
    ell = [];
    for (let i = 0; i < N; i++) {
      const a = -3 * Math.PI / 4 + 2 * Math.PI * i / N;
      circ.push([R * Math.cos(a), R * Math.sin(a)]);
    }
    const h = R * 2.2, w = R * 1.6, t = R * 0.62;
    const poly = [[-w/2, -h/2], [-w/2 + t, -h/2], [-w/2 + t, h/2 - t], [w/2, h/2 - t], [w/2, h/2], [-w/2, h/2]];
    const seg = [];
    const total = poly.reduce((s, p, i) => {
      const q = poly[(i + 1) % poly.length];
      const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
      seg.push(d);
      return s + d;
    }, 0);
    for (let i = 0; i < N; i++) {
      let d = total * i / N, k = 0;
      while (d > seg[k]) { d -= seg[k]; k++; }
      const p = poly[k], q = poly[(k + 1) % poly.length], f = d / seg[k];
      ell.push([p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f]);
    }
    for (let pass = 0; pass < 6; pass++) {
      ell = ell.map((p, i) => {
        const a = ell[(i + N - 1) % N], b = ell[(i + 1) % N];
        return [(a[0] + p[0] * 2 + b[0]) / 4, (a[1] + p[1] * 2 + b[1]) / 4];
      });
    }
  }

  build();
  window.addEventListener('resize', build);

  const clamp = (x) => Math.max(0, Math.min(1, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const outCubic = (t) => 1 - Math.pow(1 - t, 3);
  const inOut = (t) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
  const mix = (a, b, t) => `rgb(${a.map((v, i) => Math.round(lerp(v, b[i], t))).join(',')})`;

  let animId = null;

  function frame(now) {
    const t = (now / 1000) % T;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (bgColor) {
      ctx.fillStyle = bgColor;
      ctx.fillRect(0, 0, W, H);
    }

    const rise = outCubic(clamp(t / 2.2));
    const g = smooth(2.0, 3.8, t);
    const m = inOut(clamp((t - 3.9) / 1.4));
    const alpha = Math.min(clamp(t / 0.3), 1 - smooth(7.0, 7.8, t));
    const pulse = 1 + Math.sin(t * 4.2) * 0.06 * g;
    const cx = W / 2, cy = lerp(H + R * 1.4, H / 2, rise);

    ctx.globalAlpha = alpha;

    // Horizon haze
    const hz = ctx.createLinearGradient(0, H, 0, H * 0.6);
    hz.addColorStop(0, `rgba(255,120,40,${0.28 * (1 - m) * rise})`);
    hz.addColorStop(1, 'rgba(255,120,40,0)');
    ctx.fillStyle = hz;
    ctx.fillRect(0, H * 0.6, W, H * 0.4);

    // Halo
    const hr = R * (2 + 2.2 * g) * pulse;
    const halo = ctx.createRadialGradient(cx, cy, R * 0.3, cx, cy, hr);
    halo.addColorStop(0, `rgba(255,170,60,${0.45 * g})`);
    halo.addColorStop(1, 'rgba(255,100,20,0)');
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, W, H);

    // Morphing shape (Sun into letter L)
    ctx.save();
    ctx.translate(cx, cy);
    ctx.beginPath();
    let ax = 0, ay = 0;
    for (let i = 0; i < N; i++) {
      const x = lerp(circ[i][0], ell[i][0], m);
      const y = lerp(circ[i][1], ell[i][1], m);
      ax += x; ay += y;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
    ax /= N; ay /= N;

    ctx.shadowColor = `rgba(255,140,40,${0.35 + 0.55 * g})`;
    ctx.shadowBlur = R * (0.25 + 0.9 * g) * pulse;
    ctx.fillStyle = mix([200, 80, 25], [255, 120, 35], g);
    ctx.fill();
    ctx.shadowBlur = 0;

    ctx.clip();
    const gr = ctx.createRadialGradient(ax, ay, 0, ax, ay, R * 1.45);
    gr.addColorStop(0, mix([255, 140, 50], [255, 248, 210], g));
    gr.addColorStop(Math.min(0.2 + 0.35 * g, 0.95) * pulse > 0.95 ? 0.95 : 0.2 + 0.35 * g, mix([255, 110, 30], [255, 190, 80], g));
    gr.addColorStop(1, mix([190, 60, 20], [235, 90, 25], g));
    ctx.fillStyle = gr;
    ctx.fillRect(-R * 2, -R * 2, R * 4, R * 4);
    ctx.restore();

    ctx.globalAlpha = 1;
    animId = requestAnimationFrame(frame);
  }

  animId = requestAnimationFrame(frame);
  return { stop: () => cancelAnimationFrame(animId), rebuild: build };
}


// ── Boot ───────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  init();
  initSunLoader('sun-loader-canvas', { scaleMultiplier: 0.28 });
  initSunLoader('sun-status-canvas', { scaleMultiplier: 0.26 });
});

