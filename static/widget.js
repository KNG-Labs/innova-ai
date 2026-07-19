/* Innova AI — минимальный сайтовый чат-виджет (vanilla JS, без сборки).
 *
 * Подключение:
 *   <script src="http://localhost:8000/static/widget.js"
 *           data-api-base="http://localhost:8000"></script>
 *
 * Состояние (оба ключа живут в localStorage, переживают refresh):
 *   innova_anonymous_id — генерируется один раз на браузер
 *   innova_session_id   — приходит от backend, переиспользуется в каждом запросе
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var API_BASE = (script && script.getAttribute("data-api-base")) || window.location.origin;
  API_BASE = API_BASE.replace(/\/+$/, ""); // без хвостового слэша

  var ANON_KEY = "innova_anonymous_id";
  var SESSION_KEY = "innova_session_id";

  // anonymous_id должен матчить серверный pattern ^[a-zA-Z0-9._:-]+$ (min 3).
  // randomUUID даёт hex+дефисы -> подходит. Fallback для не-secure контекста.
  function getAnonId() {
    var id = localStorage.getItem(ANON_KEY);
    if (!id) {
      if (window.crypto && crypto.randomUUID) {
        id = crypto.randomUUID();
      } else {
        id = "anon-" + Date.now() + "-" + Math.random().toString(36).slice(2);
      }
      localStorage.setItem(ANON_KEY, id);
    }
    return id;
  }

  // ── styles (inline, чтобы не тащить второй request и не связываться с путём) ──
  var css =
    ".innova-launcher{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;" +
    "background:#1a73e8;color:#fff;border:none;cursor:pointer;font-size:24px;box-shadow:0 4px 12px rgba(0,0,0,.25);z-index:2147483000}" +
    ".innova-panel{position:fixed;right:20px;bottom:88px;width:340px;max-width:calc(100vw - 40px);height:480px;max-height:calc(100vh - 120px);" +
    "background:#fff;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.28);display:none;flex-direction:column;overflow:hidden;z-index:2147483000;" +
    "font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif}" +
    ".innova-panel.open{display:flex}" +
    ".innova-head{background:#1a73e8;color:#fff;padding:12px 14px;font-weight:600;font-size:15px}" +
    ".innova-msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;background:#f7f8fa}" +
    ".innova-bubble{max-width:80%;padding:8px 11px;border-radius:12px;font-size:14px;line-height:1.35;white-space:pre-wrap;word-wrap:break-word}" +
    ".innova-user{align-self:flex-end;background:#1a73e8;color:#fff;border-bottom-right-radius:4px}" +
    ".innova-bot{align-self:flex-start;background:#fff;color:#1a1a1a;border:1px solid #e3e6ea;border-bottom-left-radius:4px}" +
    ".innova-error{align-self:flex-start;background:#fdecea;color:#b3261e;border:1px solid #f5c6c2}" +
    ".innova-typing{align-self:flex-start;color:#888;font-size:13px;font-style:italic}" +
    ".innova-input{display:flex;border-top:1px solid #e3e6ea;background:#fff}" +
    ".innova-input textarea{flex:1;border:none;resize:none;padding:11px;font-size:14px;outline:none;font-family:inherit;max-height:90px}" +
    ".innova-send{border:none;background:#1a73e8;color:#fff;padding:0 16px;cursor:pointer;font-size:14px;font-weight:600}" +
    ".innova-send:disabled{background:#9bbef3;cursor:default}";

  var styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  // ── DOM ──
  var launcher = document.createElement("button");
  launcher.className = "innova-launcher";
  launcher.setAttribute("aria-label", "Открыть чат");
  launcher.textContent = "\uD83D\uDCAC"; // 💬

  var panel = document.createElement("div");
  panel.className = "innova-panel";
  panel.innerHTML =
    '<div class="innova-head">Чат с ассистентом</div>' +
    '<div class="innova-msgs"></div>' +
    '<div class="innova-input">' +
    '<textarea rows="1" placeholder="Напишите сообщение..."></textarea>' +
    '<button class="innova-send">Отпр.</button>' +
    "</div>";

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  var msgs = panel.querySelector(".innova-msgs");
  var input = panel.querySelector("textarea");
  var sendBtn = panel.querySelector(".innova-send");

  function addBubble(text, kind) {
    var b = document.createElement("div");
    b.className = "innova-bubble innova-" + kind;
    b.textContent = text;
    msgs.appendChild(b);
    msgs.scrollTop = msgs.scrollHeight;
    return b;
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    input.disabled = busy;
  }

  launcher.addEventListener("click", function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) input.focus();
  });

  async function send() {
    var text = input.value.trim();
    if (!text) return;

    input.value = "";
    addBubble(text, "user");
    setBusy(true);
    var typing = addBubble("печатает…", "typing");

    var body = {
      anonymous_id: getAnonId(),
      channel: "website",
      content: text,
      page_title: document.title || null // context-сигнал для агента
    };
    var sid = localStorage.getItem(SESSION_KEY);
    if (sid) body.session_id = sid;

    try {
      var res = await fetch(API_BASE + "/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });

      // 403 = session принадлежит другому anon_id (рассинхрон localStorage).
      // Сбрасываем session_id -> следующее сообщение начнёт новую сессию.
      if (res.status === 403) {
        localStorage.removeItem(SESSION_KEY);
        throw new Error("session reset");
      }
      if (!res.ok) throw new Error("HTTP " + res.status);

      var data = await res.json();

      if (data.state === "LEAD_READY" || data.state === "CLOSED") {
        localStorage.removeItem(SESSION_KEY);
      } else if (data.session_id) {
        localStorage.setItem(SESSION_KEY, data.session_id);
      }

      typing.remove();
      addBubble(data.answer || "(пустой ответ)", "bot");
    } catch (e) {
      typing.remove();
      addBubble("Не удалось получить ответ. Попробуйте ещё раз.", "error");
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
})();
