const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");

const base = process.env.INNOVA_DEMO_TEST_URL || "http://127.0.0.1:8017";
const output = process.env.INNOVA_DEMO_SCREENSHOTS || "/tmp/innova-visual";
const sessionId = "11111111-1111-4111-8111-111111111111";
let browser;

before(async () => {
  fs.mkdirSync(output, { recursive: true });
  browser = await chromium.launch({ channel: "chrome", headless: true, env: {} });
});
after(async () => { await browser?.close(); });

async function open(t, options = {}) {
  const context = await browser.newContext({ viewport: { width: 1680, height: 945 }, ...options });
  t.after(() => context.close());
  const page = await context.newPage();
  await page.addInitScript(() => {
    let factory;
    window.demoCarousels = [];
    Object.defineProperty(window, "EmblaCarousel", {
      get: () => factory,
      set: value => { factory = (...args) => {
        const carousel = value(...args);
        window.demoCarousels.push(carousel);
        return carousel;
      }; },
    });
  });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, []));
  await page.goto(`${base}/static/widget-demo.html`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  const slider = await page.locator(".topic-slider").boundingBox();
  await page.mouse.move(slider.x + slider.width / 2, slider.y + slider.height / 2);
  return page;
}

async function clickBusiness(page) {
  const card = await page.getByRole("button", { name: "Автосалон", exact: true }).boundingBox();
  await page.mouse.click(card.x + card.width / 2, card.y + card.height / 2);
}

test("desktop and mobile: no horizontal overflow, no broken images, desktop fits one screen", async t => {
  for (const [width, height] of [[1920, 1080], [1680, 945], [1366, 768], [1024, 768], [760, 844], [600, 844], [390, 844], [320, 740]]) {
    const page = await open(t, { viewport: { width, height }, reducedMotion: "reduce" });
    await page.locator(".topic-slider").hover();
    const metrics = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,
      looping: window.demoCarousels.map(carousel => carousel.internalEngine().options.loop),
      font: document.fonts.check('20px "Medeo Sans"'),
      broken: [...document.images].filter(image => !image.complete || !image.naturalWidth).length,
      clipped: [...document.querySelectorAll('.topic-name')]
        .filter(title => title.scrollWidth > title.clientWidth + 1).map(title => title.textContent),
      avatarFullScale: (() => {
        const avatar = document.querySelector('.avatar'), image = avatar.querySelector('img');
        const outer = avatar.getBoundingClientRect(), inner = image.getBoundingClientRect();
        return getComputedStyle(avatar).borderRadius === "50%" && getComputedStyle(avatar).overflow === "hidden"
          && getComputedStyle(image).objectFit === "contain" && getComputedStyle(image).position === "static"
          && Math.abs(outer.width - inner.width) < 1 && Math.abs(outer.height - inner.height) < 1;
      })(),
      layout: (() => {
        const cards = [...document.querySelectorAll('.topic-row')].map(row => [...row.querySelectorAll('.topic-card')]
          .map(card => card.getBoundingClientRect()).sort((a, b) => a.left - b.left));
        const step = cards[0][1].left - cards[0][0].left;
        const phase = ((cards[1][0].left - cards[0][0].left) % step + step) % step;
        const chat = document.querySelector('.chat').getBoundingClientRect();
        const clear = document.querySelector('.clear-chat');
        const button = clear.getBoundingClientRect();
        return {
          phase, step,
          horizontalGap: cards[0][1].left - cards[0][0].right,
          verticalGap: cards[1][0].top - cards[0][0].bottom,
          chatShare: chat.width / document.querySelector('.demo-layout').getBoundingClientRect().width,
          firstMessageTop: document.querySelector('.message').getBoundingClientRect().top - chat.top,
          messageSize: parseFloat(getComputedStyle(document.querySelector('.bubble')).fontSize),
          clearWidth: button.width, clearHeight: button.height, clearRadius: getComputedStyle(clear).borderRadius,
          clearText: clear.textContent.trim(), clearInComposer: Boolean(clear.closest('.composer')),
        };
      })(),
    }));
    assert.equal(metrics.width, width, `${width}: horizontal overflow`);
    if (width > 760) assert.ok(metrics.height <= height, `${width}: vertical overflow ${metrics.height}`);
    assert.deepEqual(metrics.looping, [true, true], `${width}: loop disabled`);
    assert.equal(metrics.font, true);
    assert.equal(metrics.broken, 0);
    assert.deepEqual(metrics.clipped, []);
    assert.equal(metrics.avatarFullScale, true);
    assert.ok(Math.abs(metrics.layout.phase - metrics.layout.step / 2) < 1, `${width}: staggered rows`);
    assert.ok(Math.abs(metrics.layout.horizontalGap - metrics.layout.verticalGap) < 1, `${width}: unequal card gaps`);
    if (width > 760) assert.ok(metrics.layout.chatShare > .5, `${width}: chat too narrow`);
    assert.ok(metrics.layout.firstMessageTop < 24);
    assert.ok(metrics.layout.messageSize <= 18);
    assert.equal(metrics.layout.clearWidth, 44);
    assert.equal(metrics.layout.clearHeight, 44);
    assert.equal(metrics.layout.clearRadius, "50%");
    assert.equal(metrics.layout.clearText, "");
    assert.equal(metrics.layout.clearInComposer, true);
    await page.screenshot({ path: `${output}/desktop-${width}.png`, fullPage: true });
    await page.close();
  }
});

test("carousel renders fractional movement on every frame without pixel-sized stops", async t => {
  const page = await open(t);
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  await page.mouse.move(800, 25);
  await page.clock.runFor(32);
  const card = page.locator('button[data-topic="cars"]');
  let previous = (await card.boundingBox()).x;
  for (let i = 0; i < 12; i++) {
    await page.clock.runFor(16);
    const current = (await card.boundingBox()).x;
    const step = previous - current;
    assert.ok(step > .05 && step < .95, `uneven animation frame: ${step}px`);
    previous = current;
  }
});

test("infinite carousel keeps moving on hover, pauses on focus and crosses a whole cycle without a visual jump", async t => {
  const page = await open(t);
  const row = page.locator(".topic-row").first();
  const positions = () => row.evaluate(row => [...row.querySelectorAll('.topic-card')].map(card => ({
    name: card.dataset.topic, x: card.getBoundingClientRect().x, right: card.getBoundingClientRect().right,
  })));
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  await row.hover();
  await page.clock.runFor(100);
  let progress = await page.evaluate(() => window.demoCarousels[0].scrollProgress());
  let crossedSeam = false;
  for (let i = 0; i < 90; i++) {
    const before = (await positions()).filter(card => card.x > 30 && card.right < 960);
    await page.clock.runFor(1000);
    const after = await positions();
    for (const card of before) {
      const current = after.find(other => other.name === card.name);
      assert.ok(Math.abs(card.x - current.x - 21.6) < 1.5, `seam jump: ${card.name}, step ${i}, ${card.x} → ${current.x}`);
    }
    const next = await page.evaluate(() => window.demoCarousels[0].scrollProgress());
    if (next < progress) crossedSeam = true;
    progress = next;
  }
  assert.equal(crossedSeam, true);
  await row.focus();
  await page.clock.runFor(1000);
  const paused = await positions();
  await page.clock.runFor(1000);
  assert.deepEqual(await positions(), paused);
  assert.deepEqual(await page.evaluate(() => window.demoCarousels.map(carousel => carousel.plugins().autoScroll.isPlaying())), [false, false]);
  await page.locator("textarea").focus();
  await page.clock.runFor(1000);
  assert.deepEqual(await page.evaluate(() => window.demoCarousels.map(carousel => carousel.plugins().autoScroll.isPlaying())), [true, true]);
});

test("reduced motion and keyboard: no duplicate cards, car reachable once, every business scrollable", async t => {
  const page = await open(t, { reducedMotion: "reduce", viewport: { width: 390, height: 844 } });
  const row = page.locator(".topic-row").first();
  const transform = () => page.locator(".topic-track").first().getAttribute("style");
  const initial = await transform();
  await page.waitForTimeout(150);
  assert.equal(await transform(), initial);
  assert.deepEqual(await page.evaluate(() => window.demoCarousels.map(carousel => carousel.plugins().autoScroll.isPlaying())), [false, false]);
  assert.equal(await page.getByRole("button", { name: "Автосалон", exact: true }).count(), 1);
  assert.equal(await page.locator('.topic-card').count(), 8);
  await page.keyboard.press("Tab");
  assert.equal(await page.locator(":focus").getAttribute("class"), "brand");
  await page.keyboard.press("Tab");
  assert.equal(await page.locator(":focus").getAttribute("class"), "topic-row");
  await page.keyboard.press("End");
  assert.equal(await page.evaluate(() => window.demoCarousels[0].selectedScrollSnap()), 3);
  await page.keyboard.press("Home");
  assert.equal(await page.evaluate(() => window.demoCarousels[0].selectedScrollSnap()), 0);
  await page.keyboard.press("ArrowLeft");
  assert.equal(await page.evaluate(() => window.demoCarousels[0].selectedScrollSnap()), 3);
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.evaluate(() => window.demoCarousels[0].selectedScrollSnap()), 0);
  await page.keyboard.press("Tab");
  assert.equal(await page.locator(":focus").getAttribute("data-topic"), "cars");
  const focus = await page.locator(":focus").evaluate(card => {
    const b = card.getBoundingClientRect(); return { x: b.x, right: b.right, outline: getComputedStyle(card).outlineStyle };
  });
  assert.ok(focus.x >= 0 && focus.right <= 390);
  assert.equal(focus.outline, "solid");
  await page.screenshot({ path: `${output}/mobile-reduced-motion.png`, fullPage: true });
  await page.locator("textarea").focus();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.waitForTimeout(150);
  assert.notEqual(await transform(), initial);
  assert.equal(await page.evaluate(() => window.demoCarousels[0].plugins().autoScroll.isPlaying()), true);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForTimeout(50);
  const stopped = await transform();
  await page.waitForTimeout(150);
  assert.equal(await transform(), stopped);
});

test("touch swipe pauses auto scroll, resumes after release and does not select a business", async t => {
  const page = await open(t, { hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  let requests = 0;
  await page.route(`${base}/message`, async route => {
    requests++;
    await route.fulfill({ json: { session_id: sessionId, answer: "Какой автомобиль вы ищете?" } });
  });
  const row = page.locator(".topic-row").first();
  const rect = await row.boundingBox();
  const client = await page.context().newCDPSession(page);
  const y = rect.y + rect.height / 2;
  await client.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: 290, y }] });
  assert.equal(await page.evaluate(() => window.demoCarousels[0].plugins().autoScroll.isPlaying()), false);
  const initial = await page.locator(".topic-track").first().getAttribute("style");
  for (let x = 270; x >= 190; x -= 20) {
    await client.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y }] });
    await page.waitForTimeout(30);
  }
  assert.notEqual(await page.locator(".topic-track").first().getAttribute("style"), initial);
  await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForFunction(() => window.demoCarousels[0].plugins().autoScroll.isPlaying());
  assert.equal(requests, 0);
  await page.evaluate(() => {
    const carousel = window.demoCarousels[0];
    carousel.plugins().autoScroll.stop();
    carousel.scrollTo(1, true);
    carousel.plugins().autoScroll.play();
  });
  const card = await page.getByRole("button", { name: "Автосалон", exact: true }).boundingBox();
  await page.touchscreen.tap(card.x + card.width / 2, card.y + card.height / 2);
  await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 2);
  assert.equal(requests, 1);
});

test("real test API: topic selection, Enter, multiline input, session continuity and clean context after reset", async t => {
  assert.equal(process.env.INNOVA_DEMO_LIVE_TEST, "1", "Use only the isolated _test API; set INNOVA_DEMO_LIVE_TEST=1");
  const page = await open(t, { viewport: { width: 1366, height: 768 } });
  let requests = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url() === `${base}/message`) requests++; });
  const response = page.waitForResponse(response => response.url() === `${base}/message`);
  await clickBusiness(page);
  const first = await (await response).json();
  await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 2);
  assert.equal(await page.getByRole("button", { name: "Автосалон", exact: true }).getAttribute("aria-pressed"), "true");
  assert.equal(await page.locator('button.topic-card[data-unavailable]').first().isDisabled(), true);
  await page.locator('button.topic-card[data-unavailable]').first().dispatchEvent("click");
  assert.equal(requests, 1);
  const input = page.locator("textarea");
  await input.fill("  "); await input.press("Enter"); assert.equal(requests, 1);
  await input.fill("Toyota"); await input.press("Shift+Enter"); await input.pressSequentially("Camry");
  assert.equal(await input.inputValue(), "Toyota\nCamry");
  const nextResponse = page.waitForResponse(response => response.url() === `${base}/message`);
  await input.press("Enter");
  const next = await (await nextResponse).json();
  assert.equal(next.session_id, first.session_id);
  await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 3);
  await page.getByRole("button", { name: "Очистить чат и начать новый диалог" }).click();
  assert.equal(await page.locator('.message').count(), 1);
  assert.equal(await page.getByRole("button", { name: "Автосалон", exact: true }).getAttribute("aria-pressed"), "false");
  const resetResponse = page.waitForResponse(response => response.url() === `${base}/message`);
  await input.fill("Новый диалог"); await input.press("Enter");
  const reset = await (await resetResponse).json();
  assert.notEqual(reset.session_id, first.session_id);
  assert.notEqual(reset.user_id, first.user_id);
  const history = await (await page.request.get(`${base}/sessions/${reset.session_id}/messages`)).json();
  assert.equal(history.length, 2);
  assert.equal(history[0].content, "Новый диалог");
});

test("quick replies, error recovery and long history retain a visible composer", async t => {
  const page = await open(t, { viewport: { width: 1366, height: 768 } });
  const bodies = [];
  let fail = true;
  await page.route(`${base}/message`, async route => {
    bodies.push(route.request().postDataJSON());
    if (fail) { fail = false; return route.fulfill({ status: 503, body: "unavailable" }); }
    await route.fulfill({ json: { session_id: sessionId, answer: "Конечно! Какой автомобиль вы ищете?", state: "QUALIFICATION" } });
  });
  await clickBusiness(page);
  await page.locator('.chat-error').waitFor({ state: "visible" });
  await page.screenshot({ path: `${output}/chat-error.png`, fullPage: true });
  await page.getByRole("button", { name: "Повторить запрос" }).click();
  await page.getByRole("button", { name: "Новый автомобиль", exact: true }).waitFor();
  assert.deepEqual(bodies[0], bodies[1]);
  assert.equal(await page.locator('.message.user').count(), 1);
  await page.screenshot({ path: `${output}/chat-replies.png`, fullPage: true });
  await page.getByRole("button", { name: "Новый автомобиль", exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('.message.assistant').length === 3);
  assert.equal(bodies[2].content, "Новый автомобиль");
  for (let i = 0; i < 8; i++) {
    await page.locator("textarea").fill(`Уточнение ${i}: ${"расскажите подробнее ".repeat(12)}`);
    await page.locator("textarea").press("Enter");
    await page.waitForFunction(count => document.querySelectorAll('.message.assistant').length === count, 4 + i);
  }
  const geometry = await page.evaluate(() => {
    const messages = document.querySelector('.messages'), composer = document.querySelector('.composer').getBoundingClientRect();
    return { scroll: messages.scrollHeight > messages.clientHeight, atEnd: messages.scrollHeight - messages.clientHeight - messages.scrollTop,
      composerBottom: composer.bottom, pageHeight: document.documentElement.scrollHeight };
  });
  assert.equal(geometry.scroll, true);
  assert.ok(geometry.atEnd < 2);
  assert.ok(geometry.composerBottom <= 768);
  assert.equal(geometry.pageHeight, 768);
  await page.screenshot({ path: `${output}/chat-history.png`, fullPage: true });
});
