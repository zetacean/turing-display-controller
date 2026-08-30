// Cliente JavaScript para el dashboard Turing Display Controller
// Usa WebSocket nativo para actualizaciones en tiempo real.

(function () {
  "use strict";

  const log = document.getElementById("log");
  function appendLog(cls, text) {
    if (!log) return;
    const line = document.createElement("div");
    line.className = cls;
    const ts = new Date().toLocaleTimeString();
    line.textContent = `[${ts}] ${text}`;
    log.appendChild(line);
    while (log.childNodes.length > 100) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
  }

  function getMode() {
    return (document.getElementById("current-mode") || {}).textContent || "";
  }

  function setMode(mode) {
    const el = document.getElementById("current-mode");
    if (el) el.textContent = mode;
    document.querySelectorAll(".mode-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
  }

  function setQueueSize(n) {
    const el = document.getElementById("queue-size");
    if (el) el.textContent = String(n);
  }

  // Acciones sobre el backend
  async function postJSON(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  // Modo
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const mode = btn.dataset.mode;
      try {
        await postJSON("/api/mode", { mode });
      } catch (e) {
        appendLog("error", `mode: ${e.message}`);
      }
    });
  });

  // Notificación
  const pushBtn = document.getElementById("push-notif");
  if (pushBtn) {
    pushBtn.addEventListener("click", async () => {
      const message = document.getElementById("notif-message").value.trim();
      const duration = parseFloat(document.getElementById("notif-duration").value) || 5;
      if (!message) {
        appendLog("error", "Mensaje vacío");
        return;
      }
      try {
        await postJSON("/api/notify", { message, duration });
        appendLog("info", `Notificación enviada: "${message}" (${duration}s)`);
      } catch (e) {
        appendLog("error", `notify: ${e.message}`);
      }
    });
  }

  // Frase
  const addBtn = document.getElementById("add-phrase");
  if (addBtn) {
    addBtn.addEventListener("click", async () => {
      const text = document.getElementById("phrase-text").value.trim();
      const author = document.getElementById("phrase-author").value.trim() || null;
      const category = document.getElementById("phrase-category").value.trim() || null;
      if (!text) {
        appendLog("error", "Texto de frase vacío");
        return;
      }
      try {
        await postJSON("/api/phrases", { phrases: [{ text, author, category }] });
        appendLog("info", `Frase añadida: "${text.slice(0, 40)}..."`);
        document.getElementById("phrase-text").value = "";
      } catch (e) {
        appendLog("error", `phrase: ${e.message}`);
      }
    });
  }

  // WebSocket
  let ws = null;
  function connectWS() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => appendLog("ack", "WebSocket conectado");
    ws.onclose = () => {
      appendLog("error", "WebSocket desconectado; reintentando en 3s");
      setTimeout(connectWS, 3000);
    };
    ws.onerror = () => appendLog("error", "WebSocket error");
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.event === "mode_changed") {
          setMode(data.payload.mode);
          appendLog("ack", `Modo cambiado: ${data.payload.mode}`);
        } else if (data.event === "notification_queued") {
          appendLog("info", `Notificación encolada: "${data.payload.message}"`);
        } else if (data.event === "phrases_added") {
          appendLog("ack", `Frases añadidas: ${data.payload.count}`);
        } else if (data.event === "ack") {
          appendLog("ack", `ack: ${data.payload.action}`);
        } else if (data.event === "error") {
          appendLog("error", `error: ${data.payload.detail}`);
        }
      } catch (e) {
        appendLog("error", `parse: ${e.message}`);
      }
    };
  }
  connectWS();

  // Refrescar estado cada 5s
  async function refreshStatus() {
    try {
      const r = await fetch("/api/status");
      if (!r.ok) return;
      const s = await r.json();
      setMode(s.mode);
      setQueueSize(s.notification_queue_size);
    } catch (_e) {
      // silencioso
    }
  }
  setInterval(refreshStatus, 5000);
  refreshStatus();
})();
