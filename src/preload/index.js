/**
 * src/preload/index.js - Secure Preload Layer for Lumina Desktop.
 * 
 * Exposes a minimal, type-safe API to the renderer process while maintaining
 * complete context isolation and keeping API tokens safely out of reach.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lumina', {
  platform: process.platform,

  // ── Streaming Chat ────────────────────────────────────────────────────────
  sendMessage: (payload, onEvent) => {
    return new Promise(async (resolve, reject) => {
      try {
        const reqId = await ipcRenderer.invoke('lumina:chat:stream', payload);

        const channel = `lumina:stream:event:${reqId}`;
        const listener = (event, data) => {
          if (typeof onEvent === 'function') {
            onEvent(data);
          }
          if (data.type === 'message:complete') {
            ipcRenderer.removeListener(channel, listener);
            resolve(data);
          } else if (data.type === 'message:error') {
            ipcRenderer.removeListener(channel, listener);
            resolve(data);
          }
        };

        ipcRenderer.on(channel, listener);
      } catch (err) {
        reject(err);
      }
    });
  },

  // ── Conversation Management ───────────────────────────────────────────────
  listConversations: () => ipcRenderer.invoke('lumina:conversations:list'),
  getConversation: (id) => ipcRenderer.invoke('lumina:conversations:get', id),
  deleteConversation: (id) => ipcRenderer.invoke('lumina:conversations:delete', id),

  // ── Models & Control ──────────────────────────────────────────────────────
  listModels: () => ipcRenderer.invoke('lumina:models:list'),
  launchModel: (model) => ipcRenderer.invoke('lumina:models:launch', model),
  killModel: (payload) => ipcRenderer.invoke('lumina:models:kill', payload),
  triggerSmartswitch: (payload) => ipcRenderer.invoke('lumina:models:smartswitch', payload),
  systemAssess: () => ipcRenderer.invoke('lumina:models:assess'),
  downloadModel: (payload) => ipcRenderer.invoke('lumina:models:download', payload),
  getStatus: () => ipcRenderer.invoke('lumina:status:get'),

  // ── RAG & Tools ───────────────────────────────────────────────────────────
  listTools: () => ipcRenderer.invoke('lumina:tools:list'),
  createTool: (payload) => ipcRenderer.invoke('lumina:tools:create', payload),
  deleteTool: (name) => ipcRenderer.invoke('lumina:tools:delete', name),
  ragIngest: (text, filename) => ipcRenderer.invoke('lumina:rag:ingest', text, filename),
  executeCode: (code) => ipcRenderer.invoke('lumina:ide:execute', code),
  completeCode: (prefix, maxTokens) => ipcRenderer.invoke('lumina:ide:complete', prefix, maxTokens),

  // ── Window Controls ───────────────────────────────────────────────────────
  minimizeWindow: () => ipcRenderer.send('lumina:window:minimize'),
  maximizeWindow: () => ipcRenderer.send('lumina:window:maximize'),
  closeWindow: () => ipcRenderer.send('lumina:window:close'),

  // ── Backend Lifecycle Events ──────────────────────────────────────────────
  onBackendReady: (callback) => {
    ipcRenderer.on('lumina:backend:ready', (event, data) => callback(data));
  },
  onBackendStatus: (callback) => {
    ipcRenderer.on('lumina:backend:status', (event, data) => callback(data));
  },
  onBackendError: (callback) => {
    ipcRenderer.on('lumina:backend:error', (event, data) => callback(data));
  }
});
