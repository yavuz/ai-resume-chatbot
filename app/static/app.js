"use strict";

const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const suggestions = document.getElementById("suggestions");

// Sohbet geçmişi sunucuda tutulur; burada yalnızca oturum kimliği var.
// Sayfa yenilenince yeni sohbet başlar.
let sessionId = null;
let busy = false;
let fallbackReply = "";
const ref = new URLSearchParams(location.search).get("c");

fetch("/api/config")
  .then((r) => r.json())
  .then((cfg) => {
    fallbackReply = cfg.fallback_reply;
    input.maxLength = cfg.max_message_chars;
  })
  .catch(() => {});

// --- Basit ve güvenli metin render'ı: önce her şey escape edilir. ---

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function inline(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
}

function renderText(text) {
  const blocks = escapeHtml(text.trim()).split(/\n{2,}/);
  return blocks
    .map((block) => {
      const lines = block.split("\n");
      if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
        return "<ul>" + lines.map((l) => "<li>" + inline(l.replace(/^\s*[-*•]\s+/, "")) + "</li>").join("") + "</ul>";
      }
      return "<p>" + lines.map(inline).join("<br>") + "</p>";
    })
    .join("");
}

// --- Mesaj balonları ---

function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  if (role === "user") el.textContent = text;
  else el.innerHTML = renderText(text);
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function addTyping() {
  const el = document.createElement("div");
  el.className = "msg bot";
  el.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function fallbackText() {
  return fallbackReply || "Şu an yanıt veremiyorum. Lütfen daha sonra tekrar deneyin.";
}

// --- Sunucuya gönderme ve SSE akışını okuma ---

function parseSseEvent(raw) {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  return { event, data: data ? JSON.parse(data) : {} };
}

async function send(text) {
  if (busy) return;
  const message = text.trim();
  if (!message) return;

  busy = true;
  sendBtn.disabled = true;
  suggestions.hidden = true;
  addMessage("user", message);
  input.value = "";
  autoGrow();
  const bubble = addTyping();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, ref }),
    });

    if (!res.ok) {
      let detail = fallbackText();
      try {
        const body = await res.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {}
      bubble.classList.add("error");
      bubble.innerHTML = renderText(detail);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const { event, data } = parseSseEvent(buffer.slice(0, idx));
        buffer = buffer.slice(idx + 2);
        if (event === "session") {
          sessionId = data.session_id;
        } else if (event === "delta") {
          answer += data.text;
          bubble.innerHTML = renderText(answer);
          scrollToBottom();
        } else if (event === "error") {
          answer = data.text;
          bubble.innerHTML = renderText(answer);
        }
      }
    }
    if (!answer) bubble.innerHTML = renderText(fallbackText());
  } catch {
    bubble.classList.add("error");
    bubble.innerHTML = renderText(fallbackText());
  } finally {
    busy = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

// --- Etkileşim ---

function autoGrow() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(input.value);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send(input.value);
  }
});

input.addEventListener("input", autoGrow);

suggestions.addEventListener("click", (e) => {
  if (e.target instanceof HTMLButtonElement) send(e.target.textContent);
});
