import { writeFile } from "node:fs/promises";
import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

type Diagnostics = { maxConversationMessages: number; messages: number; estimatedBytes: number; conversations: number; tombstones: number; pending: number; limits: { conversationMessages: number; globalMessages: number; globalBytes: number; tombstones: number } };
const diagnostics = (page: Page): Promise<Diagnostics> => page.evaluate(() => {
  const root = document.querySelector("#app");
  if (!root) { throw new Error("Application root missing"); }
  const app = Reflect.get(root, "__vue_app__");
  const pinia = Object.getOwnPropertySymbols(app._context.provides).map((key) => app._context.provides[key]).find((value) => value?._s instanceof Map);
  const chat = pinia?._s.get("chat");
  if (!chat) { throw new Error("Chat store missing"); }
  const counts = new Map<string, number>();
  for (const message of chat.messages) {
    const key = JSON.stringify([message.scope, message.topic_id ?? message.source ?? message.destination ?? ""]);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return { ...chat.diagnostics, maxConversationMessages: Math.max(0, ...counts.values()) };
});

test("sustained chat stream plateaus and history scrolling bounds rendered rows", async ({ page }, info) => {
  test.setTimeout(120000);
  let stream: WebSocketRoute | undefined;
  let closed = 0;
  await page.routeWebSocket("**/messages/stream", (socket) => { stream = socket; socket.onClose(() => { closed++; }); });
  await page.route("**/events/system", (route) => route.abort());
  const timestamp = new Date().toISOString();
  const row = (id: number, topic?: string) => ({ MessageID: `fixture-${id}`, Direction: "inbound", Scope: topic ? "topic" : "broadcast", State: "received", Content: `Message ${id} ${"body ".repeat(id % 7 + 1)}`, Source: "peer", TopicID: topic ?? null, CreatedAt: timestamp, UpdatedAt: timestamp, Attachments: [] });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    let response: unknown;
    if (url.pathname === "/api/v1/app/info") { response = { name: "Chat fixture", version: "test" }; }
    else if (url.pathname === "/api/r3akt/setup/status") { response = { setup_required: false }; }
    else if (url.pathname === "/Status") { response = { status: "ok" }; }
    else if (url.pathname === "/Client") { response = []; }
    else if (url.pathname === "/Topic") { response = Array.from({ length: 10 }, (_, i) => ({ TopicID: `t${i}`, TopicName: `Topic ${i}` })); }
    else if (url.pathname === "/Chat/History") {
      const older = url.searchParams.has("cursor");
      const start = older ? 1 : 101;
      const topic = url.searchParams.get("topic_id") ?? undefined;
      response = { Messages: Array.from({ length: 100 }, (_, i) => row(start + i, topic)), NextCursor: older ? null : "1:100" };
    } else { await route.fallback(); return; }
    await route.fulfill({ json: response });
  });
  await page.goto("/chat");
  await page.getByRole("combobox", { name: "Auth Mode" }).selectOption("none");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("button", { name: "Older messages" })).toBeEnabled();
  await expect.poll(() => !!stream).toBe(true);
  await page.getByRole("button", { name: "Topics", exact: true }).click();
  await page.getByRole("button", { name: "Topic 0 Topic", exact: false }).click();
  await expect(page.getByText("Conversation: Topic 0")).toBeVisible();
  const cdp = await page.context().newCDPSession(page);
  const samples: { events: number; usedHeap: number; diagnostics: Diagnostics; domRows: number }[] = [];
  for (let batch = 0; batch < 6; batch++) {
    for (let i = 0; i < 4000; i++) {
      const id = 1000 + batch * 4000 + i;
      stream?.send(JSON.stringify({ type: "message.receive", ts: timestamp, data: { entry: row(id, `t${i % 10}`) } }));
    }
    await expect.poll(async () => (await diagnostics(page)).tombstones, { timeout: 20000 }).toBeGreaterThan(0);
    // Wait for the last event without retaining a test-only copy of the stream in the browser.
    await expect.poll(() => page.evaluate((id) => {
      const root = document.querySelector("#app"); if (!root) { return false; }
      const app = Reflect.get(root, "__vue_app__");
      const pinia = Object.getOwnPropertySymbols(app._context.provides).map((key) => app._context.provides[key]).find((value) => value?._s instanceof Map);
      return pinia?._s.get("chat").messages.some((message: { message_id?: string }) => message.message_id === `fixture-${id}`);
    }, 1000 + (batch + 1) * 4000 - 1), { timeout: 20000 }).toBe(true);
    await cdp.send("HeapProfiler.collectGarbage");
    const heap = await cdp.send("Runtime.getHeapUsage");
    const snapshot = await diagnostics(page);
    expect(snapshot.messages).toBeLessThanOrEqual(snapshot.limits.globalMessages);
    expect(snapshot.maxConversationMessages).toBeLessThanOrEqual(snapshot.limits.conversationMessages);
    expect(snapshot.estimatedBytes).toBeLessThanOrEqual(snapshot.limits.globalBytes);
    expect(snapshot.tombstones).toBeLessThanOrEqual(snapshot.limits.tombstones);
    const domRows = await page.locator(".message-card").count(); expect(domRows).toBeGreaterThan(0); expect(domRows).toBeLessThan(40);
    samples.push({ events: (batch + 1) * 4000, usedHeap: heap.usedSize, diagnostics: snapshot, domRows });
  }
  const warm = samples.slice(2).map((sample) => sample.usedHeap);
  expect(Math.max(...warm) - Math.min(...warm)).toBeLessThan(8 * 1024 * 1024);
  await page.getByRole("button", { name: "Older messages" }).click();
  await expect(page.getByRole("button", { name: "Latest messages" })).toBeVisible();
  await page.locator(".message-scroller").focus();
  await page.keyboard.press("End");
  await expect.poll(() => page.locator(".message-card").count()).toBeLessThan(40);
  await page.keyboard.press("Home");
  await expect(page.getByText("Message 100", { exact: false }).first()).toBeVisible();
  await expect.poll(() => page.locator(".message-scroller").evaluate((element) => element.scrollTop)).toBe(0);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
  const beforeLive = await diagnostics(page);
  await page.locator(".message-scroller").evaluate((element) => {
    element.scrollTop = 2507; element.dispatchEvent(new Event("scroll"));
  });
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))));
  const readingPosition = () => page.locator(".message-scroller").evaluate((element) => {
    const top = element.getBoundingClientRect().top + element.clientTop + 8;
    const row = [...element.querySelectorAll(".message-card")].find((item) => item.getBoundingClientRect().bottom > top);
    if (!row) { throw new Error("Reading row missing"); }
    return { id: row.getAttribute("data-message-id"), offset: top - row.getBoundingClientRect().top };
  });
  const anchor = await readingPosition();
  stream?.send(JSON.stringify({ type: "message.receive", ts: timestamp, data: { entry: row(27000, "t0") } }));
  await expect.poll(async () => (await diagnostics(page)).messages).toBe(beforeLive.messages + 1);
  await expect.poll(async () => (await readingPosition()).id).toBe(anchor.id);
  await expect.poll(async () => (await readingPosition()).offset).toBeCloseTo(anchor.offset, 0);
  await page.locator(".message-scroller").focus(); await page.keyboard.press("Home");
  await expect.poll(() => page.locator(".message-scroller").evaluate((element) => element.scrollTop)).toBe(0);
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  const idleMutations = await page.evaluate(() => new Promise<number>((resolve) => {
    const element = document.querySelector(".message-stack"); if (!element) { throw new Error("message stack missing"); }
    let mutations = 0;
    const observer = new MutationObserver((records) => { mutations += records.length; });
    observer.observe(element, { subtree: true, attributes: true, childList: true });
    setTimeout(() => { observer.disconnect(); resolve(mutations); }, 500);
  }));
  await page.screenshot({ path: info.outputPath("chat-history.png") });
  const samplesPath = info.outputPath("browser-resource-samples.json");
  await writeFile(samplesPath, JSON.stringify({ samples, idleMutations }, null, 2));
  await info.attach("browser-resource-samples", { path: samplesPath, contentType: "application/json" });
  expect(idleMutations).toBeLessThan(10);
  await page.getByRole("button", { name: "Topics", exact: true }).click();
  await page.getByRole("button", { name: "Topic 0 Topic", exact: false }).click();
  await expect(page.getByText("Conversation: Topic 0")).toBeVisible();
  await page.getByRole("link", { name: "About", exact: true }).click();
  await expect.poll(() => closed).toBeGreaterThan(0);
  await page.evaluate(() => {
    const root = document.querySelector("#app"); if (!root) { throw new Error("root missing"); }
    const app = Reflect.get(root, "__vue_app__");
    const pinia = Object.getOwnPropertySymbols(app._context.provides).map((key) => app._context.provides[key]).find((value) => value?._s instanceof Map);
    pinia._s.get("connection").setAuthStatus("unauthenticated");
  });
  expect(await diagnostics(page)).toMatchObject({ messages: 0, estimatedBytes: 0, tombstones: 0 });
});
