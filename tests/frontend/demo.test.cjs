const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const staticDir = path.resolve(__dirname, "../../static");
const sessionId = "11111111-1111-4111-8111-111111111111";
const answer = (text = "Какой автомобиль вы ищете?") => ({
  ok: true,
  json: async () => ({ session_id: sessionId, answer: text, state: "QUALIFICATION" }),
});
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup(t, fetch = async () => answer(), { saved = null, storageBlocked = false } = {}) {
  const dom = new JSDOM(fs.readFileSync(path.join(staticDir, "widget-demo.html"), "utf8"), {
    url: "http://localhost:8017/static/widget-demo.html", runScripts: "outside-only", pretendToBeVisual: true,
  });
  t.after(() => dom.window.close());
  const w = dom.window;
  // JSDOM has no layout or observer APIs; carousel motion is tested in Chrome.
  w.ResizeObserver = w.IntersectionObserver = class {
    observe() {}
    disconnect() {}
  };
  w.matchMedia = query => ({ matches: query === "(prefers-reduced-motion: reduce)", addEventListener() {}, removeEventListener() {} });
  const calls = [];
  w.fetch = async (...args) => { calls.push(JSON.parse(args[1].body)); return fetch(...args); };
  if (saved) w.localStorage.setItem("innova_demo_v1", saved);
  if (storageBlocked) Object.defineProperty(w, "localStorage", { get() { throw new Error("blocked"); } });
  for (const script of w.document.querySelectorAll("script[src]")) {
    w.eval(fs.readFileSync(path.join(staticDir, script.getAttribute("src")), "utf8"));
  }
  const find = selector => w.document.querySelector(selector);
  return {
    w, calls, find,
    state: () => JSON.parse(w.localStorage.getItem("innova_demo_v1")),
    send: text => {
      find("textarea").value = text;
      find("textarea").dispatchEvent(new w.Event("input"));
      find("form").dispatchEvent(new w.Event("submit", { cancelable: true }));
    },
  };
}

test("eight unique cards, seven disabled, all asset references resolve locally", async t => {
  const h = setup(t);
  const cards = [...h.w.document.querySelectorAll("button.topic-card")];
  assert.equal(cards.length, 8);
  assert.equal(new Set(cards.map(b => b.dataset.topic)).size, 8);
  assert.equal(cards.filter(b => b.disabled).length, 7);
  for (const card of cards.filter(b => b.disabled)) {
    assert.equal(card.getAttribute("aria-disabled"), "true");
    assert.ok(card.textContent.includes("Скоро"));
    card.click();
  }
  assert.equal(h.calls.length, 0);
  assert.equal(h.find(".messages").children.length, 1);
  for (const image of h.w.document.querySelectorAll("img")) {
    assert.ok(fs.existsSync(path.join(staticDir, image.getAttribute("src"))));
  }
  assert.equal(h.find("#author-github").hidden, false);
  assert.equal(h.find("#author-github").href, "https://github.com/GeorgiiSadunyan");
  assert.equal(h.find("#author-github").textContent, "Автор проекта");
  assert.equal(h.find("#author-placeholder"), null);
  assert.equal(h.find("h1").textContent, "Выберите бизнес");
  assert.equal(h.find('button[data-topic="cars"]').textContent, "Автосалон");
  assert.equal(h.w.document.querySelectorAll(".topic-slide").length, 8);
  assert.equal(h.w.document.querySelectorAll(".topic-track").length, 2);
  assert.equal(h.w.document.querySelectorAll('.topic-slider [aria-hidden]').length, 0);
  assert.ok([...h.w.document.querySelectorAll('img')].every(img => img.src.endsWith('.webp')));
});

test("topic and quick reply use the real message contract and keep history", async t => {
  const h = setup(t);
  h.find('button[data-topic="cars"]').click();
  await flush();
  assert.deepEqual(Object.keys(h.calls[0]).sort(), ["anonymous_id", "channel", "content", "page_title"]);
  assert.equal(h.calls[0].channel, "website");
  assert.match(h.calls[0].content, /автосалона/);
  assert.equal(h.find('button[data-topic="cars"]').getAttribute("aria-pressed"), "true");
  assert.equal(h.find(".quick-replies").children.length, 3);
  h.find(".quick-replies button").click();
  await flush();
  assert.equal(h.calls[1].content, "Новый автомобиль");
  assert.equal(h.calls[1].session_id, sessionId);
  h.find('button[data-topic="cars"]').click();
  await flush();
  assert.equal(h.find(".messages").children.length, 7);
});

test("blank, duplicate and IME submissions blocked; Enter sends, Shift+Enter stays multiline", async t => {
  let resolve;
  const h = setup(t, () => new Promise(r => { resolve = r; }));
  h.send("   "); assert.equal(h.calls.length, 0);
  const input = h.find("textarea");
  input.value = "Toyota\nCamry";
  input.dispatchEvent(new h.w.KeyboardEvent("keydown", { key: "Enter", shiftKey: true, cancelable: true }));
  input.dispatchEvent(new h.w.KeyboardEvent("keydown", { key: "Enter", isComposing: true, cancelable: true }));
  assert.equal(h.calls.length, 0);
  input.dispatchEvent(new h.w.KeyboardEvent("keydown", { key: "Enter", cancelable: true }));
  h.send("ещё");
  assert.equal(h.calls.length, 1);
  assert.match(h.find('[role="status"]').textContent, /готовит/);
  assert.equal(h.find(".send").disabled, true);
  resolve(answer("Расскажите подробнее о задаче."));
  await flush();
  assert.equal(h.find(".quick-replies").hidden, true);
});

test("error retry reuses payload and does not duplicate the visible user message", async t => {
  let attempt = 0;
  const h = setup(t, async () => { if (!attempt++) throw new TypeError("offline"); return answer(); });
  h.send("Хочу автомобиль"); await flush();
  assert.equal(h.find(".chat-error").hidden, false);
  h.find(".retry").click(); await flush();
  assert.deepEqual(h.calls[0], h.calls[1]);
  assert.equal(h.w.document.querySelectorAll(".message.user").length, 1);
  assert.equal(h.find(".chat-error").hidden, true);
});

test("clear rotates both identifiers, ignores a late response and starts a new server context", async t => {
  let resolve;
  let attempt = 0;
  const h = setup(t, async () => ++attempt === 2 ? new Promise(r => { resolve = r; }) : answer());
  h.send("первый"); await flush();
  const old = h.state();
  h.send("ожидание");
  h.find(".clear-chat").click();
  assert.notEqual(h.state().anonymousId, old.anonymousId);
  assert.equal(h.state().sessionId, null);
  assert.equal(h.state().topic, null);
  resolve(answer("Поздний ответ")); await flush();
  assert.equal(h.find(".messages").children.length, 1);
  h.send("новый"); await flush();
  assert.notEqual(h.calls[2].anonymous_id, h.calls[0].anonymous_id);
  assert.equal("session_id" in h.calls[2], false);
  assert.equal(h.find(".messages").textContent.includes("Поздний ответ"), false);
});

test("history restores, unavailable storage works, backend text is never inserted as HTML", async t => {
  const h = setup(t, async () => answer('<img src=x onerror="alert(1)">'));
  h.send("текст"); await flush();
  assert.equal(h.find(".bubble img"), null);
  const restored = setup(t, undefined, { saved: JSON.stringify(h.state()) });
  assert.equal(restored.state().anonymousId, h.state().anonymousId);
  assert.equal(restored.find(".messages").children.length, 3);
  const blocked = setup(t, undefined, { storageBlocked: true });
  blocked.send("тест"); await flush();
  assert.equal(blocked.calls.length, 1);
});

test("forbidden and malformed responses retain history and offer recovery", async t => {
  for (const response of [
    { ok: false, status: 403 },
    { ok: true, json: async () => ({ answer: "", session_id: sessionId }) },
  ]) {
    const h = setup(t, async () => response);
    h.send("вопрос"); await flush();
    assert.equal(h.find(".chat-error").hidden, false);
    assert.equal(h.find(".messages").children.length, 2);
    assert.equal(h.find(".quick-replies").hidden, true);
    assert.ok(h.state().pending);
    h.find(".clear-chat").click();
    assert.equal(h.state().pending, null);
    assert.equal(h.find("textarea").readOnly, false);
  }
});
