// CI adapter for the existing page-function harnesses; artifacts contain no database.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const output = process.env.BROWSER_QA_OUTPUT;
assert(output && process.env.SQLITE_PATH && process.env.EMPTY_SQLITE_PATH, "CI validation paths required");
fs.mkdirSync(output, { recursive: true });
const origin = "http://127.0.0.1:3015";
const api = "http://127.0.0.1:8015/api";
const services = new Set();
const report = { sha: process.env.GITHUB_SHA, runtime: "Next production / Django / disposable SQLite / Chromium", harnesses: {}, checks: [], diagnostics: [] };
let browser;
let backend;
let page;
let phase = "startup";
const check = (ok, label) => { assert(ok, label); report.checks.push(label); };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function start(command, args, cwd, env, name) {
  const log = fs.openSync(path.join(output, name + ".log"), "a");
  const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, detached: true, stdio: ["ignore", log, log] });
  fs.closeSync(log);
  child.on("error", error => { report.diagnostics.push({ phase: name, kind: "service", text: error.message }); });
  services.add(child);
  return child;
}
async function stop(child) {
  if (!child?.pid || child.exitCode !== null || child.signalCode !== null) { services.delete(child); return; }
  process.kill(-child.pid, "SIGCONT");
  process.kill(-child.pid, "SIGTERM");
  const exited = new Promise(resolve => child.once("exit", resolve));
  await Promise.race([exited, delay(5000)]);
  if (child.exitCode === null && child.signalCode === null) { process.kill(-child.pid, "SIGKILL"); await exited; }
  services.delete(child);
}
async function ready(url, child) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    assert(child.exitCode === null && child.signalCode === null, "Server exited before readiness: " + url);
    try { if ((await fetch(url, { signal: AbortSignal.timeout(2000) })).ok) return; } catch {}
    await delay(250);
  }
  throw new Error("Readiness deadline: " + url);
}
async function startBackend(database = process.env.SQLITE_PATH) {
  backend = start("python", ["manage.py", "runserver", "127.0.0.1:8015", "--noreload"], path.join(root, "backend"), { SQLITE_PATH: database }, "backend");
  await ready(api + "/brain-anatomy/", backend);
}
async function newPage() {
  if (page) await page.context().close();
  const context = await browser.newContext();
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  let navigation = 0;
  const requestNavigation = new WeakMap();
  const observedPage = page;
  page.on("request", request => {
    if (request.isNavigationRequest() && request.frame() === observedPage.mainFrame()) navigation++;
    requestNavigation.set(request, navigation);
  });
  page.on("pageerror", error => report.diagnostics.push({ phase, kind: "pageerror", text: error.message }));
  page.on("console", message => {
    if (["warning", "error"].includes(message.type())) report.diagnostics.push({ phase, kind: "console", text: message.text(), url: message.location().url });
  });
  page.on("requestfailed", request => report.diagnostics.push({ phase, kind: "requestfailed", url: request.url(), text: request.failure()?.errorText, prefetch: !!request.headers()["next-router-prefetch"], flight: request.headers().rsc === "1", supersededByNavigation: requestNavigation.get(request) < navigation }));
  page.on("response", response => {
    if (response.status() >= 400) report.diagnostics.push({ phase, kind: "http", url: response.url(), status: response.status() });
  });
  await page.goto(origin + "/brain");
}
async function goto(route, selector = "main:visible h1") {
  await page.goto(origin + route);
  await page.locator(selector).first().waitFor();
}
async function json(route) {
  const response = await page.request.get(api + route);
  assert(response.ok(), route);
  return response.json();
}

async function main() {
  await startBackend();
  const frontend = start(process.execPath, ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3015"], path.join(root, "frontend"), {}, "frontend");
  await ready(origin + "/brain", frontend);
  browser = await chromium.launch();
  report.browser = browser.version();
  for (const name of ["brain_browser_checks", "atlas_browser_checks", "atlas_browser_resilience_checks"]) {
    phase = name;
    await newPage();
    const harness = vm.runInThisContext(fs.readFileSync(path.join(__dirname, name + ".js"), "utf8"), { filename: name + ".js" });
    const started = Date.now();
    report.harnesses[name] = { ...await harness(page), durationMs: Date.now() - started };
    console.log(name + ": PASS " + JSON.stringify(report.harnesses[name]));
  }

  phase = "accessibility-real-data";
  await newPage();
  const anatomy = await json("/brain-anatomy/?page_size=300");
  const longest = anatomy.results.reduce((a, b) => a.name_en.length > b.name_en.length ? a : b);
  const graph = await json("/concept-map/");
  report.corpus = { anatomy: anatomy.count, assessments: (await json("/assessments/")).count, graphNodes: graph.nodes.length, graphEdges: graph.edges.length };
  check(report.corpus.anatomy === 87 && report.corpus.assessments === 4, "pinned public entity counts");
  const phqNode = graph.nodes.find(node => node.type === "assessment" && node.slug === "patient-health-questionnaire");
  const routes = ["/brain", "/brain/" + longest.slug, "/assessments", "/assessments/patient-health-questionnaire", "/search?q=PHQ-9", "/map?node=" + encodeURIComponent(phqNode.id)];
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: width === 1280 ? 800 : 844 });
    for (const [index, route] of routes.entries()) {
      await goto(route, route.startsWith("/map") ? ".map-stage h2" : route.startsWith("/search") ? ".results-count" : route === "/brain" ? ".brain-card" : route === "/assessments" ? ".assessment-card" : "main:visible h1");
      const scope = width + "px " + route;
      check(await page.locator("main:visible").count() === 1 && await page.locator("main:visible h1").count() === 1, "landmarks/headings " + scope);
      check(await page.locator("html").getAttribute("lang") === "fa" && await page.locator("html").getAttribute("dir") === "rtl", "Persian RTL " + scope);
      if (route.startsWith("/map")) check(await page.locator('.relation-filter-row button[aria-pressed="true"]').count() === 1, "relation selection has explicit state " + scope);
      if (route.startsWith("/search")) {
        check(await page.getByLabel("جست‌وجوی سراسری اطلس").evaluate(element => element === document.activeElement), "Search entry focus " + scope);
        for (let step = 0; step < 20; step++) {
          await page.keyboard.press("Shift+Tab");
          if (await page.evaluate(() => document.activeElement.classList.contains("skip-link"))) break;
        }
      } else await page.keyboard.press("Tab");
      await page.waitForFunction(() => document.activeElement.classList.contains("skip-link") && getComputedStyle(document.activeElement).outlineStyle !== "none" && document.activeElement.getBoundingClientRect().top >= 0);
      check(true, "visible keyboard focus " + scope);
      if (index === 0) await page.screenshot({ path: path.join(output, "focus-" + width + ".png") });
      await page.keyboard.press("Enter");
      check(await page.evaluate(() => document.activeElement.id === "main-content"), "skip link targets content " + scope);
      const defects = await page.locator("main:visible").evaluate(main => {
        const visible = element => element.checkVisibility();
        const named = element => element.getAttribute("aria-label") || element.getAttribute("aria-labelledby") || element.labels?.length;
        return {
          unlabeled: [...main.querySelectorAll("input:not([type=hidden]), select, textarea")].filter(visible).filter(element => !named(element)).length,
          smallControls: [...main.querySelectorAll("input:not([type=hidden]), select, button")].filter(visible).filter(element => { const rect = element.getBoundingClientRect(); return rect.width < 24 || rect.height < 24; }).length,
          unsafeExternal: [...main.querySelectorAll("a[target=_blank]")].filter(element => !/noopener|noreferrer/.test(element.rel)).length,
          unnamedLinks: [...main.querySelectorAll("a[href]")].filter(visible).filter(element => !(element.textContent.trim() || element.getAttribute("aria-label") || element.querySelector("img[alt]")?.alt)).length,
        };
      });
      check(Object.values(defects).every(value => value === 0), "labels, primary touch targets, named/safe links " + scope + " " + JSON.stringify(defects));
      const summary = page.locator("main:visible details > summary:visible").first();
      if (await summary.count()) {
        await summary.focus();
        const before = await summary.evaluate(element => element.parentElement.open);
        await page.keyboard.press("Enter");
        check(await summary.evaluate(element => element.parentElement.open) !== before, "keyboard disclosure " + scope);
      }
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "no horizontal overflow " + scope);
      await page.screenshot({ path: path.join(output, "viewport-" + width + "-" + index + ".png"), fullPage: true });
      fs.writeFileSync(path.join(output, "accessibility-" + width + "-" + index + ".txt"), await page.locator("body").ariaSnapshot());
    }
    await goto("/brain", ".brain-card");
    const menu = page.locator(width === 1280 ? ".site-menu > summary" : ".site-mobile-menu > summary");
    await menu.focus();
    await page.keyboard.press("Enter");
    const nav = page.locator(width === 1280 ? ".site-atlas-menu" : ".site-mobile-panel");
    check(await nav.isVisible(), "keyboard header navigation " + width);
    await nav.locator('a[href="/assessments"]').click();
    await page.locator(".assessment-card").first().waitFor();
    check(new URL(page.url()).pathname === "/assessments", "header route navigation " + width);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  await goto("/assessments", ".assessment-card");
  check(await page.locator(".assessment-card").first().evaluate(element => parseFloat(getComputedStyle(element).transitionDuration) <= .01), "Assessment reduced motion");
  await goto("/map", ".map-stage h2");
  check(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches), "Graph reduced-motion preference");
  await page.getByLabel("جست‌وجوی گره‌های نقشه").fill("zzzz-release-no-match");
  await page.getByText("گرهی مطابق این انتخاب پیدا نشد. عبارت یا فیلترها را تغییر دهید.").waitFor();
  check(await page.locator(".map-list-node").count() === 0, "graph no-results recovery state");
  await goto("/search?q=zzzz-release-no-match", ".results-count");
  await page.getByText("نتیجه‌ای مطابق این عبارت پیدا نشد. نام یا اختصار دیگری را امتحان کنید.").waitFor();
  check(await page.locator('main:visible [role="alert"]').count() === 0, "search no-results is not error");
  const relatedBrain = graph.nodes.find(node => node.type === "brain_anatomy" && node.degree > 0);
  await goto("/map?node=" + encodeURIComponent(relatedBrain.id), ".map-stage h2");
  await page.locator(".relation-filter-row button").last().click();
  check(await page.locator(".relation-filter-row button").first().getAttribute("aria-pressed") === "false" && await page.locator(".relation-filter-row button").last().getAttribute("aria-pressed") === "true", "source-backed relation filter exposes changed selection");

  phase = "supplemental-server-states";
  await newPage();
  for (const domain of ["brain", "assessments"]) {
    process.kill(backend.pid, "SIGSTOP");
    try {
      await page.goto(origin + "/" + domain, { waitUntil: "commit" });
      await page.locator("." + (domain === "brain" ? "brain" : "assessment") + "-loading:visible").first().waitFor();
      check(true, domain + " real server loading state");
    } finally { process.kill(backend.pid, "SIGCONT"); }
    await page.locator("." + (domain === "brain" ? "brain" : "assessment") + "-card").first().waitFor();
    await stop(backend);
    await goto("/" + domain, 'main:visible [role="alert"]');
    check(await page.getByRole("link", { name: "تلاش دوباره", exact: true }).count() === 1, domain + " server outage has retry");
    await startBackend();
    await page.getByRole("link", { name: "تلاش دوباره", exact: true }).click();
    await page.locator("." + (domain === "brain" ? "brain" : "assessment") + "-card").first().waitFor();
    check(true, domain + " retry restores actual publication");
  }
  await stop(backend);
  await startBackend(process.env.EMPTY_SQLITE_PATH);
  for (const [route, text] of [["/brain", "هنوز ساختاری منتشر نشده است"], ["/assessments", "هنوز ابزاری در این مجموعه منتشر نشده است"], ["/map", "نقشه هنوز داده‌ای ندارد."]]) {
    await goto(route);
    await page.getByText(text, { exact: true }).waitFor();
    check(await page.locator('main:visible [role="alert"]').count() === 0, "empty migrated database " + route);
  }
  await stop(backend);
  await startBackend();
  phase = "post-qa-real-data-smoke";
  await newPage();
  for (const route of ["/brain-anatomy/", "/brain-anatomy/amygdala/", "/assessments/", "/assessments/patient-health-questionnaire/"]) { await json(route); check(true, "final API smoke " + route); }
  check((await json("/search/?q=Amygdala")).brain_entities.length > 0, "final Brain Search");
  check((await json("/search/?q=PHQ-9")).assessments.length > 0, "final Assessment Search");
  const finalGraph = await json("/concept-map/");
  check(finalGraph.nodes.some(node => node.type === "brain_anatomy") && finalGraph.nodes.some(node => node.type === "assessment"), "final Graph discovery");
  const unexpected = report.diagnostics.filter(item => {
    if (item.phase === "atlas_browser_resilience_checks" && /127\.0\.0\.1:8015\/api\/(search|concept-map)\//.test(item.url || "") && (item.kind === "requestfailed" && /ERR_FAILED|ERR_CONNECTION_REFUSED/.test(item.text) || item.kind === "console" && /net::ERR_|Failed to load resource/.test(item.text))) return false;
    if (item.kind === "requestfailed" && /ERR_ABORTED/.test(item.text) && (item.prefetch || item.flight && item.supersededByNavigation) && new URL(item.url).origin === origin && new URL(item.url).searchParams.has("_rsc")) return false;
    if (item.kind === "http" && item.status === 404 && /not-an-approved-entity|v095-unknown-slug/.test(item.url)) return false;
    if (item.kind === "console" && /404 \(Not Found\)/.test(item.text) && /not-an-approved-entity|v095-unknown-slug/.test(item.url || "")) return false;
    return true;
  });
  report.unexpectedDiagnostics = unexpected;
  check(unexpected.length === 0, "no unexpected console/network/hydration/runtime diagnostics: " + JSON.stringify(unexpected));
  report.status = "PASS";
}

main().catch(async error => {
  report.status = "FAIL";
  report.failure = { phase, message: error.message, stack: error.stack, url: page?.url(), focus: await page?.evaluate(() => document.activeElement.outerHTML).catch(() => "unavailable") };
  console.error(error);
  process.exitCode = 1;
  if (page) {
    await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true }).catch(() => {});
    fs.writeFileSync(path.join(output, "failure-accessibility.txt"), await page.locator("body").ariaSnapshot().catch(() => "unavailable"));
  }
}).finally(async () => {
  if (browser) await browser.close();
  for (const child of services) await stop(child);
  fs.writeFileSync(path.join(output, "report.json"), JSON.stringify(report, null, 2));
  console.log("Browser release QA: " + report.status + "; supplemental assertions: " + report.checks.length);
});
