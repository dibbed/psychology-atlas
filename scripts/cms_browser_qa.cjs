// Real P03 journey; synthetic disposable SQLite, existing bundled Playwright, production Next.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "atlas-p03-browser-"));
const output = process.env.CMS_QA_OUTPUT || temporary;
fs.mkdirSync(output, { recursive: true });
const python = process.env.CMS_QA_PYTHON || (process.platform === "win32" ? path.join(root, "backend/.venv/Scripts/python.exe") : "python");
const origin = "http://127.0.0.1:3023";
const env = { ...process.env, NEXT_PUBLIC_API_URL: "http://127.0.0.1:8023/api", SQLITE_PATH: path.join(temporary, "cms-journey.sqlite3"), CSRF_TRUSTED_ORIGINS: origin, DEBUG: "1" };
const report = { runtime: "Production Next / real Django / migrated synthetic disposable SQLite / Chromium", checks: [], expectedHttpErrors: [], browserErrors: [], screenshots: [], limitations: ["Chromium only; no Firefox, WebKit, real mobile device or screen reader", "Local HTTP; no target HTTPS/proxy/deployment rehearsal", "Loading/error/unknown-outcome checks use explicit network fault injection; normal journey uses real API"] };
const check = (condition, label) => { assert(condition, label); report.checks.push(label); };
const services = [];
let browser;
let observedPage;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function start(command, args, cwd, name) {
  const log = fs.openSync(path.join(temporary, name + ".log"), "a");
  const child = spawn(command, args, { cwd, env, windowsHide: true, stdio: ["ignore", log, log] });
  fs.closeSync(log); services.push(child); return child;
}
async function ready(url, child) {
  for (let attempt = 0; attempt < 100; attempt++) {
    assert(child.exitCode === null, "Service stopped before readiness");
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1500) })).status < 500) return; } catch {}
    await pause(300);
  }
  throw new Error("Service readiness timeout");
}
async function waitText(page, text) { await page.getByText(text, { exact: true }).first().waitFor(); }
async function login(page, user, index = 0) {
  await page.goto(origin + "/admin-console");
  await page.getByLabel("نام کاربری", { exact: true }).fill(user.username);
  await page.getByLabel("گذرواژه", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "ادامه با گذرواژه", exact: true }).click();
  await page.getByLabel("روش تأیید").selectOption("recovery");
  await page.getByLabel("کد تأیید", { exact: true }).fill(user.tokens[index]);
  await page.getByRole("button", { name: "تأیید و ورود", exact: true }).click();
  await page.getByRole("button", { name: "خروج", exact: true }).waitFor();
}
async function screenshot(page, name) {
  await page.evaluate(() => scrollTo(0, 0));
  const file = path.join(output, name + ".png"); await page.screenshot({ path: file, fullPage: true }); report.screenshots.push(name + ".png");
}
async function noOverflow(page, label) {
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label + ": no document overflow");
}
async function request(page, apiPath, body, etag) {
  return page.evaluate(async ({ apiPath, body, etag }) => {
    const csrf = await fetch("/api/admin/auth/csrf/").then(r => r.json());
    const response = await fetch("/api/admin" + apiPath, { method: body ? "POST" : "GET", headers: body ? { "Content-Type": "application/json", "X-CSRFToken": csrf.csrf_token, ...(etag ? { "If-Match": etag } : {}) } : {}, ...(body ? { body: JSON.stringify(body) } : {}) });
    return { status: response.status, data: await response.json(), etag: response.headers.get("ETag"), cache: response.headers.get("Cache-Control") };
  }, { apiPath, body, etag });
}
async function main() {
  const fixture = JSON.parse(execFileSync(python, [path.join(root, "scripts/cms_browser_fixture.py")], { env, encoding: "utf8" }));
  const backend = start(python, ["manage.py", "runserver", "127.0.0.1:8023", "--noreload"], path.join(root, "backend"), "backend");
  await ready("http://127.0.0.1:8023/api/admin/auth/csrf/", backend);
  const frontend = start(process.execPath, [path.join(root, "frontend/node_modules/next/dist/bin/next"), "start", "-p", "3023"], path.join(root, "frontend"), "frontend");
  await ready(origin + "/admin-console", frontend);
  browser = await chromium.launch(); report.browserVersion = browser.version();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage(); page.setDefaultTimeout(15000);
  observedPage = page;
  const observe = page => {
    page.on("pageerror", error => report.browserErrors.push(error.message));
    page.on("console", message => {
      if (message.type() === "error" && !message.text().startsWith("Failed to load resource") && !message.text().startsWith("Failed to fetch")) report.browserErrors.push(message.text());
    });
    page.on("response", response => { if (response.status() >= 400 && response.url().includes("/api/admin/")) report.expectedHttpErrors.push({ path: new URL(response.url()).pathname, status: response.status() }); });
  };
  observe(page);
  await page.goto(origin + "/admin-console");
  await page.getByRole("heading", { name: "ورود به کنسول", exact: true }).waitFor();
  check(await page.locator(".site-nav").count() === 0, "Public chrome separated from CMS");
  await page.setViewportSize({ width: 320, height: 850 }); await noOverflow(page, "320px login"); await screenshot(page, "cms-login-320"); await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, fixture.users.owner);
  await page.getByRole("heading", { name: "خانهٔ مدیریت", exact: true }).waitFor();
  const cookies = await context.cookies();
  check(cookies.some(cookie => cookie.name === "admin_sessionid" && cookie.httpOnly && cookie.sameSite === "Lax"), "Real MFA session uses HttpOnly/Lax cookie");
  check(await page.evaluate(() => localStorage.length) === 0, "CMS stores no tokens or snapshots in localStorage");
  const maintained = await page.request.get(origin + "/account/two_factor/");
  check(maintained.status() === 200 && new URL(maintained.url()).origin === origin, "Maintained MFA profile is reachable through same-origin proxy");
  const dashboard = await request(page, "/dashboard/");
  check(dashboard.cache === "no-store" && dashboard.data.content.find(row => row.kind === "category").total === 1, "Dashboard reconciles real API counts and no-store");
  const document = await page.request.get(origin + "/admin-console");
  check(document.headers()["cache-control"].includes("no-store"), "Console HTML is no-store");
  await noOverflow(page, "Desktop dashboard"); await screenshot(page, "cms-dashboard-desktop");
  await page.getByRole("link", { name: "محتوای مرجع", exact: true }).click();
  await page.getByRole("link", { name: /باز کردن دسته‌بندی‌ها/ }).click();
  await page.getByRole("link", { name: "پیش‌نویس جدید", exact: true }).click();
  await page.getByLabel("نام علمی انگلیسی (الزامی)", { exact: true }).fill("   ");
  await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click();
  await page.locator(".cms-error[role=alert]").waitFor();
  check(await page.locator(".cms-error[role=alert]").evaluate(node => node === document.activeElement), "Real validation failure focuses form error summary");
  check(await page.getByLabel("نام علمی انگلیسی (الزامی)", { exact: true }).getAttribute("aria-invalid") === "true", "Server field error is associated with labelled input");
  await page.getByLabel("نام علمی انگلیسی (الزامی)", { exact: true }).fill("CMS new draft");
  await page.getByLabel("نام فارسی", { exact: true }).fill("پیش‌نویس آزمون CMS");
  await page.getByLabel("توضیح", { exact: true }).fill("دادهٔ مصنوعی آزمون؛ ادعای علمی نیست.");
  await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click();
  await page.getByRole("heading", { name: "پیش‌نویس آزمون CMS", exact: true }).waitFor();
  const draftId = new URL(page.url()).pathname.split("/").pop();
  const draft = await request(page, `/content/category/${draftId}/`);
  check(draft.data.canonical_pk === null && draft.data.version === 1, "UI creates actual revision without canonical publication");
  await page.getByRole("button", { name: "تاریخچهٔ نسخه‌ها", exact: true }).click();
  await page.locator(".cms-history-entry").first().waitFor();
  await page.locator(".cms-history-entry summary").first().click();
  check(await page.locator(".cms-history-entry").count() === 1, "Created draft appears in immutable history");
  await page.getByRole("button", { name: "ویرایش پیشنهاد", exact: true }).click();
  await page.getByLabel("توضیح", { exact: true }).fill("تغییر ذخیره‌نشدهٔ آزمون");
  let nativeGuard = false;
  page.once("dialog", async dialog => { nativeGuard = dialog.type() === "beforeunload"; await dialog.dismiss(); });
  await page.reload({ timeout: 3000 }).catch(() => {});
  check(nativeGuard && await page.getByLabel("توضیح", { exact: true }).inputValue() === "تغییر ذخیره‌نشدهٔ آزمون", "Native reload guard retains unsaved form");
  await page.getByRole("link", { name: "خانهٔ مدیریت", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  check(await page.getByRole("button", { name: "ادامهٔ ویرایش", exact: true }).evaluate(node => node === document.activeElement), "Unsaved dialog moves focus to safe action");
  await page.keyboard.press("Escape");
  check(await page.getByLabel("توضیح", { exact: true }).inputValue() === "تغییر ذخیره‌نشدهٔ آزمون", "Escape cancels leave without losing draft");
  await page.getByRole("button", { name: "بازگرداندن فرم به نسخهٔ ذخیره‌شده", exact: true }).click();
  await page.getByRole("button", { name: "ترک بدون ذخیره", exact: true }).click();
  const recordPath = `/admin-console/content/category/${fixture.category}`;
  await page.goto(origin + recordPath);
  await page.getByRole("button", { name: "ویرایش پیشنهاد", exact: true }).click();
  check(await page.getByLabel("نام علمی انگلیسی (الزامی)").evaluate(node => getComputedStyle(node).direction) === "ltr", "Scientific name input is independently LTR");
  const second = await context.newPage(); observe(second);
  await second.goto(origin + recordPath); await second.getByRole("button", { name: "ویرایش پیشنهاد", exact: true }).click();
  await page.getByLabel("توضیح", { exact: true }).fill("پیشنهاد ویرایشگر اول");
  const input = page.getByLabel("توضیح", { exact: true });
  await input.focus(); await page.keyboard.press("Tab"); await page.keyboard.press("Shift+Tab");
  check(await input.evaluate(node => getComputedStyle(node).outlineStyle !== "none"), "Keyboard focus has visible outline");
  await second.getByLabel("توضیح", { exact: true }).fill("پیشنهاد ویرایشگر دوم");
  await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click();
  await waitText(page, "پیشنهاد ذخیره شد. محتوای عمومی بدون تغییر است.");
  await second.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click();
  await second.getByRole("heading", { name: "نسخه تغییر کرده است", exact: true }).waitFor();
  check(await second.getByLabel("توضیح", { exact: true }).inputValue() === "پیشنهاد ویرایشگر دوم", "412 retains unsaved editor text");
  await second.getByRole("button", { name: "دریافت نسخهٔ سرور و مقایسه", exact: true }).click();
  await second.getByLabel("انتخاب توضیح", { exact: true }).waitFor();
  check(await second.getByLabel("انتخاب توضیح", { exact: true }).inputValue() === "", "Overlapping conflict requires explicit field choice");
  await second.getByLabel("انتخاب توضیح", { exact: true }).selectOption("mine");
  await second.getByRole("button", { name: "پذیرش مقایسه و ادامهٔ ویرایش", exact: true }).click();
  await second.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click();
  await waitText(second, "پیشنهاد ذخیره شد. محتوای عمومی بدون تغییر است.");
  check((await request(second, `/content/category/${fixture.category}/`)).data.version === 2, "Explicit rebase saves against new server ETag");
  await second.setViewportSize({ width: 320, height: 850 }); await noOverflow(second, "320px editor"); await screenshot(second, "cms-editor-320");
  await second.getByRole("button", { name: "پیش‌نمایش و اختلاف", exact: true }).click(); await noOverflow(second, "320px preview");
  await second.getByRole("button", { name: "تاریخچهٔ نسخه‌ها", exact: true }).click();
  await second.locator(".cms-history-entry").first().waitFor(); check(await second.locator(".cms-history-entry").count() === 3, "Legacy and both proposals retained in history");
  await noOverflow(second, "320px history");
  await second.getByRole("link", { name: "تاریخچهٔ عملیات", exact: true }).click();
  await second.locator(".cms-table tbody tr").first().waitFor(); await noOverflow(second, "320px audit table");
  await second.getByRole("link", { name: /revision.created/ }).first().click(); await second.locator(".cms-audit-detail").waitFor();
  check(await second.locator(".cms-audit-detail").innerText().then(text => text.includes("description") && !text.includes("پیشنهاد ویرایشگر دوم")), "UI audit shows field diff without content values");
  await noOverflow(second, "320px audit detail"); await screenshot(second, "cms-audit-320");
  // Drop a real success response after commit, then reconcile instead of blind retry.
  await page.goto(origin + recordPath); await page.getByRole("button", { name: "ویرایش پیشنهاد", exact: true }).click();
  await page.getByLabel("توضیح", { exact: true }).fill("ذخیره با پاسخ ازدست‌رفته");
  await page.route("**/api/admin/content/category/*/revisions/", async route => { await route.fetch(); await route.abort("failed"); });
  await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click();
  await page.getByText(/نتیجهٔ ذخیره نامعلوم است/).waitFor();
  check(await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).isDisabled(), "Unknown write outcome disables blind resubmit");
  await page.unroute("**/api/admin/content/category/*/revisions/");
  await page.getByRole("button", { name: "دریافت نسخهٔ سرور و مقایسه", exact: true }).click();
  await page.getByRole("button", { name: "پذیرش مقایسه و ادامهٔ ویرایش", exact: true }).click();
  check(await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).isDisabled(), "Committed lost response reconciles without duplicate revision");
  check((await request(page, `/content/category/${fixture.category}/`)).data.version === 3, "Lost-response reconciliation leaves exactly one new revision");
  await page.goto(origin + "/admin-console/content/category?q=absent-cms-name"); await page.getByRole("heading", { name: "موردی یافت نشد", exact: true }).waitFor(); check(true, "Server-filtered empty state distinct from loading/error");
  await page.goto(origin + "/admin-console/content/category"); await page.locator(".cms-table tbody tr").first().waitFor();
  await page.setViewportSize({ width: 320, height: 850 }); await noOverflow(page, "320px list"); await screenshot(page, "cms-list-320");
  await page.locator(".cms-record-link").first().focus(); await page.keyboard.press("Enter"); await page.getByRole("button", { name: "تاریخچهٔ نسخه‌ها", exact: true }).waitFor(); check(true, "Keyboard opens detail from list");
  await page.goto(origin + "/admin-console"); await page.getByRole("heading", { name: "خانهٔ مدیریت", exact: true }).waitFor(); await noOverflow(page, "320px dashboard"); await screenshot(page, "cms-dashboard-320");
  await page.route("**/api/admin/content/category/?*", route => route.abort("failed"));
  await page.goto(origin + "/admin-console/content/category"); await page.getByText("ارتباط با سرور برقرار نشد؛ دوباره تلاش کنید.", { exact: true }).waitFor();
  await page.unroute("**/api/admin/content/category/?*"); await page.getByRole("button", { name: "تلاش دوباره", exact: true }).click(); await page.locator(".cms-table tbody tr").first().waitFor(); check(true, "Read network error has working retry");
  await page.route("**/api/admin/content/category/?*", async route => { await pause(900); await route.continue(); });
  await page.reload(); await page.getByRole("status").filter({ hasText: "در حال دریافت داده از سرور" }).waitFor(); await page.unroute("**/api/admin/content/category/?*"); await page.locator(".cms-table tbody tr").first().waitFor(); check(true, "Loading state visible while actual read delayed");
  await page.goto(origin + recordPath); await page.getByRole("button", { name: "ویرایش پیشنهاد", exact: true }).click(); await page.getByLabel("توضیح", { exact: true }).fill("این متن نباید به حساب بعدی برسد");
  await request(page, "/auth/logout/", {});
  await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click(); await page.getByRole("heading", { name: "نشست مدیریت پایان یافته است", exact: true }).waitFor();
  check(await page.locator("textarea").count() === 0, "Expired session clears private draft UI");
  await noOverflow(page, "320px expired session"); await screenshot(page, "cms-session-expired-320");
  await login(page, fixture.users.reader);
  await second.getByRole("heading", { name: "نشست مدیریت پایان یافته است", exact: true }).waitFor();
  check(await second.locator("textarea").count() === 0, "Cross-tab session/account change clears old editor snapshots");
  await page.goto(origin + recordPath); await page.getByRole("heading", { name: "آخرین پیشنهاد ذخیره‌شده", exact: true }).waitFor();
  check(await page.getByRole("button", { name: "ویرایش پیشنهاد", exact: true }).count() === 0, "Read-only capability exposes no editor action");
  const deniedWrite = await request(page, `/content/category/${fixture.category}/revisions/`, { payload: { description: "forbidden" }, base_digest: "" }, '"3"');
  check(deniedWrite.status === 403 && deniedWrite.data.code === "PERMISSION_DENIED", "Real backend rejects forged read-only write");
  await request(page, "/auth/logout/", {}); await login(page, fixture.users.scoped); await page.goto(origin + recordPath); await page.getByRole("heading", { name: "این بخش در دسترس شما نیست", exact: true }).waitFor();
  check((await request(page, `/content/category/${fixture.category}/`)).status === 404, "Direct foreign-scope URL/API denied independently");
  await noOverflow(page, "320px forbidden"); await screenshot(page, "cms-forbidden-320");
  await page.goto(origin + "/"); await page.locator(".site-nav").waitFor(); check(true, "Public navigation still renders outside CMS");
  const canonical = execFileSync(python, ["manage.py", "shell", "-c", "from atlas.models import Category; from atlas.cms_content_models import ContentRevision; import json; print(json.dumps({'description': Category.objects.get(slug='cms-journey-category').description, 'revisions': ContentRevision.objects.count(), 'canonical_count': Category.objects.count()}))"], { cwd: path.join(root, "backend"), env, encoding: "utf8" });
  const verified = JSON.parse(canonical.trim().split(/\r?\n/).pop());
  check(verified.description === "دادهٔ آزمون؛ محتوای علمی نیست." && verified.canonical_count === 1 && verified.revisions === 5, "Database confirms preserved canonical and expected five revisions");
  check(report.browserErrors.length === 0, "No unexplained browser console/runtime errors");
}
main().then(() => { report.status = "passed"; }).catch(async error => { report.status = "failed"; report.failure = error.message; process.exitCode = 1; if (observedPage) await screenshot(observedPage, "cms-failure"); }).finally(async () => {
  if (browser) await browser.close();
  await Promise.all(services.reverse().map(child => new Promise(resolve => {
    if (child.exitCode !== null) { resolve(); return; }
    child.once("exit", resolve); child.kill();
  })));
  fs.writeFileSync(path.join(output, "cms-browser-report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: report.status, assertions: report.checks.length, failure: report.failure, report: path.join(output, "cms-browser-report.json") }));
  for (const name of ["cms-journey.sqlite3", "cms-journey.sqlite3-journal", "backend.log", "frontend.log"]) fs.rmSync(path.join(temporary, name), { force: true });
});
