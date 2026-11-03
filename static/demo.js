(() => {
  "use strict";

  const config = window.INNOVA_DEMO;
  const STORAGE_KEY = "innova_demo_v1";
  const greeting = "Здравствуйте! Сейчас я могу помочь с вопросами об автомобилях и услугах автосалона. Выберите бизнес «Автосалон» или задайте вопрос.";
  const input = document.querySelector("textarea");
  const sendButton = document.querySelector(".send");
  const messages = document.querySelector(".messages");
  const status = document.querySelector(".request-status");
  const errorBox = document.querySelector(".chat-error");
  const replies = document.querySelector(".quick-replies");
  const rows = [...document.querySelectorAll(".topic-row")];
  const timeFormat = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" });
  let activeRequest = null;

  function newDialog() {
    return {
      anonymousId: window.crypto.randomUUID ? window.crypto.randomUUID() : `demo-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      sessionId: null,
      topic: null,
      messages: [{ role: "assistant", content: greeting, time: new Date().toISOString() }],
      pending: null,
    };
  }

  function loadDialog() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (saved && /^[a-zA-Z0-9._:-]{3,128}$/.test(saved.anonymousId)
        && (saved.sessionId === null || /^[0-9a-f-]{36}$/i.test(saved.sessionId))
        && Array.isArray(saved.messages) && saved.messages.length
        && saved.messages.every(m => ["user", "assistant"].includes(m.role)
          && typeof m.content === "string" && Number.isFinite(Date.parse(m.time)))) {
        if (saved.messages[0].role === "assistant") saved.messages[0].content = greeting;
        return saved;
      }
    } catch { /* Хранилище может быть недоступно в приватном режиме. */ }
    return newDialog();
  }

  let dialog = loadDialog();

  function saveDialog() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(dialog)); }
    catch { /* Текущий диалог продолжает работать без сохранения в браузере. */ }
  }

  function scrollToLatest() { messages.scrollTop = messages.scrollHeight; }

  function renderMessage(message) {
    const row = document.createElement("div");
    row.className = `message ${message.role}`;
    if (message.role === "assistant") {
      const avatar = document.createElement("span");
      avatar.className = "avatar";
      const image = document.createElement("img");
      image.src = "images/assistant.webp";
      image.alt = "";
      avatar.append(image);
      row.append(avatar);
    }
    const body = document.createElement("div");
    body.className = "message-body";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = message.content;
    const time = document.createElement("time");
    time.className = "timestamp";
    time.dateTime = message.time;
    time.textContent = timeFormat.format(new Date(message.time));
    body.append(bubble, time);
    row.append(body);
    row.setAttribute("aria-label", message.role === "assistant" ? "INNOVA AI" : "Вы");
    messages.append(row);
    scrollToLatest();
  }

  function addMessage(role, content) {
    const message = { role, content, time: new Date().toISOString() };
    dialog.messages.push(message);
    renderMessage(message);
    saveDialog();
  }

  function updateControls() {
    const blocked = Boolean(activeRequest || dialog.pending);
    sendButton.disabled = blocked || !input.value.trim();
    input.readOnly = blocked;
    document.querySelector(".composer").setAttribute("aria-busy", String(Boolean(activeRequest)));
    document.querySelectorAll(".topic-card:not([data-unavailable])").forEach(button => {
      if (button.tagName === "BUTTON") button.disabled = blocked;
      button.setAttribute("aria-pressed", String(dialog.topic === button.dataset.topic));
    });
    document.querySelector(".retry").disabled = Boolean(activeRequest);
  }

  function renderReplies() {
    replies.replaceChildren();
    const last = dialog.messages.at(-1);
    let options = [];
    // shortcut: API не возвращает подсказки; расширять только по явным вопросам агента.
    if (!activeRequest && !dialog.pending && last?.role === "assistant" && last.content.includes("?")) {
      if (/какой\s+автомобиль\s+(?:вы\s+)?(?:ищете|рассматриваете)/iu.test(last.content)
        || /новый[^?]*пробег|пробег[^?]*новый/iu.test(last.content)) {
        options = ["Новый автомобиль", "С пробегом", "Пока выбираю"];
      } else if (/способ\s+покупки|наличн[^?]*кредит|кредит[^?]*трейд/iu.test(last.content)) {
        options = ["За наличные", "В кредит", "Трейд-ин"];
      }
    }
    for (const option of options) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = option;
      button.addEventListener("click", () => send(option));
      replies.append(button);
    }
    replies.hidden = !options.length;
  }

  async function requestAnswer(body) {
    if (activeRequest) return;
    const owner = dialog;
    const controller = new AbortController();
    activeRequest = controller;
    errorBox.hidden = true;
    status.textContent = "Ассистент готовит ответ…";
    updateControls();
    renderReplies();
    const timeout = setTimeout(() => controller.abort(), 60000);
    try {
      const response = await fetch("/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(response.status === 403
          ? "Сессия недоступна. Нажмите «Очистить чат», чтобы начать новый диалог."
          : "Не удалось получить ответ. Проверьте соединение и повторите запрос.");
      }
      const data = await response.json();
      if (typeof data.answer !== "string" || !data.answer.trim()
        || typeof data.session_id !== "string" || !/^[0-9a-f-]{36}$/i.test(data.session_id)) {
        throw new Error("Сервер вернул некорректный ответ. Попробуйте ещё раз.");
      }
      if (dialog !== owner) return;
      dialog.sessionId = data.session_id;
      dialog.pending = null;
      addMessage("assistant", data.answer);
    } catch (error) {
      if (dialog !== owner) return;
      errorBox.querySelector("p").textContent = error.name === "AbortError"
        ? "Ответ занимает слишком много времени. Можно повторить запрос."
        : (error instanceof TypeError ? "Нет соединения с сервером. Проверьте сеть и повторите запрос." : error.message);
      errorBox.hidden = false;
    } finally {
      clearTimeout(timeout);
      if (dialog === owner) {
        activeRequest = null;
        status.textContent = "";
        updateControls();
        renderReplies();
        saveDialog();
        scrollToLatest();
      }
    }
  }

  function send(content) {
    const text = content.trim();
    if (!text || text.length > 4000 || activeRequest || dialog.pending) return;
    dialog.topic = "cars";
    const body = {
      anonymous_id: dialog.anonymousId,
      channel: "website",
      content: text,
      page_title: "INNOVA AI — автомобили и услуги автосалона",
    };
    if (dialog.sessionId) body.session_id = dialog.sessionId;
    dialog.pending = body;
    input.value = "";
    input.style.height = "auto";
    addMessage("user", text);
    requestAnswer(body);
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const slider = document.querySelector(".topic-slider");
  rows.forEach((row, index) => {
    const track = document.createElement("div");
    track.className = "topic-track";
    for (const topic of config.topics.filter(topic => topic.row === index)) {
      const button = document.createElement("button");
      button.className = "topic-card";
      button.type = "button";
      button.dataset.topic = topic.id;
      const image = document.createElement("img");
      image.src = `images/${topic.image}`;
      image.alt = "";
      image.width = 280;
      image.height = 210;
      image.draggable = false;
      const name = document.createElement("span");
      name.className = "topic-name";
      name.textContent = topic.name;
      button.append(image, name);
      if (!topic.available) {
        button.disabled = true;
        button.dataset.unavailable = "true";
        button.setAttribute("aria-disabled", "true");
        const soon = document.createElement("span");
        soon.className = "soon";
        soon.textContent = "Скоро";
        button.append(soon);
      } else {
        button.setAttribute("aria-pressed", String(dialog.topic === topic.id));
        button.addEventListener("click", () => send(topic.message));
      }
      const slide = document.createElement("div");
      slide.className = "topic-slide";
      slide.append(button);
      track.append(slide);
    }
    row.append(track);
    const carousel = EmblaCarousel(row, {
      loop: true,
      dragFree: true,
      startIndex: index ? 0 : 1,
      align: (view, slide) => (view - slide) / 2
        + (index ? (track.children[1].offsetLeft - track.children[0].offsetLeft) / 2 : 0),
    }, [EmblaCarouselAutoScroll({
      speed: .36,
      startDelay: 0,
      stopOnInteraction: false,
      stopOnFocusIn: false,
      breakpoints: { "(prefers-reduced-motion: reduce)": { active: false } },
    })]);
    row.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      if (event.key === "Home") carousel.scrollTo(0, reducedMotion.matches);
      else if (event.key === "End") carousel.scrollTo(carousel.scrollSnapList().length - 1, reducedMotion.matches);
      else if (event.key === "ArrowRight") carousel.scrollNext(reducedMotion.matches);
      else carousel.scrollPrev(reducedMotion.matches);
    });
    carousel.on("reInit", syncAutoScroll);
    // Auto Scroll resumes after dragging settles; keep keyboard focus paused.
    carousel.on("settle", () => queueMicrotask(syncAutoScroll));
    function syncAutoScroll() {
      const paused = reducedMotion.matches || document.hidden || slider.contains(document.activeElement);
      const autoScroll = carousel.plugins().autoScroll;
      if (paused) autoScroll.stop();
      else autoScroll.play();
    }
    slider.addEventListener("focusin", syncAutoScroll);
    slider.addEventListener("focusout", () => queueMicrotask(syncAutoScroll));
    document.addEventListener("visibilitychange", syncAutoScroll);
    syncAutoScroll();
  });
  window.addEventListener("load", scrollToLatest);

  document.querySelector("form").addEventListener("submit", event => { event.preventDefault(); send(input.value); });
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send(input.value);
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 142)}px`;
    updateControls();
  });
  document.querySelector(".retry").addEventListener("click", () => {
    if (dialog.pending) requestAnswer(dialog.pending);
  });
  document.querySelector(".clear-chat").addEventListener("click", () => {
    activeRequest?.abort();
    activeRequest = null;
    dialog = newDialog();
    messages.replaceChildren();
    dialog.messages.forEach(renderMessage);
    input.value = "";
    input.style.height = "auto";
    status.textContent = "Начат новый диалог";
    errorBox.hidden = true;
    saveDialog();
    updateControls();
    renderReplies();
  });

  dialog.messages.forEach(renderMessage);
  if (dialog.pending) {
    errorBox.querySelector("p").textContent = "Предыдущий запрос не завершён. Можно повторить его или очистить чат.";
    errorBox.hidden = false;
  }
  updateControls();
  renderReplies();
  saveDialog();
})();
