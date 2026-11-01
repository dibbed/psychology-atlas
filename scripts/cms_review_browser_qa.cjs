// P04 real services and browser journey, on guarded synthetic data only.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "atlas-p04-browser-"));
const output = process.env.CMS_QA_OUTPUT || temporary;
fs.mkdirSync(output, { recursive: true });
const python = process.env.CMS_QA_PYTHON || (process.platform === "win32" ? path.join(root, "backend/.venv/Scripts/python.exe") : "python");
const origin = "http://127.0.0.1:3023";
const env = { ...process.env, CMS_QA_PHASE: "p04", NEXT_PUBLIC_API_URL: "http://127.0.0.1:8023/api",
  SQLITE_PATH: path.join(temporary, "cms-journey.sqlite3"), CSRF_TRUSTED_ORIGINS: origin, DEBUG: "1" };
const report = { runtime: "Production Next / real Django session, MFA, CSRF, services / synthetic disposable SQLite / Chromium",
  checks: [], journey: [], browserErrors: [], screenshots: [], limitations: ["Chromium desktop and 320px viewport only", "Synthetic evidence, not scientific content", "Source mutation is a guarded fixture injection; P05 source editor is separate", "Local HTTP, no deployment rehearsal"] };
const check = (condition, label) => { assert(condition, label); report.checks.push(label); };
const services = [];
let browser, page;
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
async function api(apiPath, body, etag) {
  return page.evaluate(async ({ apiPath, body, etag }) => {
    const csrf = await fetch("/api/admin/auth/csrf/").then(r => r.json());
    const response = await fetch("/api/admin" + apiPath, { method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json", "X-CSRFToken": csrf.csrf_token, ...(etag ? { "If-Match": etag } : {}) } : {},
      ...(body ? { body: JSON.stringify(body) } : {}) });
    return { status: response.status, data: await response.json(), etag: response.headers.get("ETag") };
  }, { apiPath, body, etag });
}
async function login(user, index = 0) {
  await page.goto(origin + "/admin-console");
  await page.getByLabel("نام کاربری", { exact: true }).fill(user.username);
  await page.getByLabel("گذرواژه", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "ادامه با گذرواژه", exact: true }).click();
  await page.getByLabel("روش تأیید").selectOption("recovery");
  await page.getByLabel("کد تأیید", { exact: true }).fill(user.tokens[index]);
  await page.getByRole("button", { name: "تأیید و ورود", exact: true }).click();
  await page.getByRole("button", { name: "خروج", exact: true }).waitFor();
}
async function screenshot(name) {
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, name + ".png"), fullPage: true }); report.screenshots.push(name + ".png");
}
async function noOverflow(label) { check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label); }
async function waitForState(apiPath, predicate) {
  let value;
  for (let attempt = 0; attempt < 80; attempt++) {
    value = await api(apiPath);
    if (value.status === 200 && predicate(value.data)) return value;
    await pause(150);
  }
  throw new Error("Review state did not reach expected result");
}
async function main() {
  const fixture = JSON.parse(execFileSync(python, [path.join(root, "scripts/cms_browser_fixture.py")], { env, encoding: "utf8" }));
  const backend = start(python, ["manage.py", "runserver", "127.0.0.1:8023", "--noreload"], path.join(root, "backend"), "backend");
  await ready("http://127.0.0.1:8023/api/admin/auth/csrf/", backend);
  const frontend = start(process.execPath, [path.join(root, "frontend/node_modules/next/dist/bin/next"), "start", "-p", "3023"], path.join(root, "frontend"), "frontend");
  await ready(origin + "/admin-console", frontend);
  browser = await chromium.launch({ headless: true }); report.chromium = browser.version();
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on("pageerror", error => report.browserErrors.push(error.message));
  page.on("console", message => { if (message.type() === "error" && !message.text().includes("Failed to load resource")) report.browserErrors.push(message.text()); });
  await login(fixture.users.owner);
  const publicBefore = execFileSync(python, ["manage.py", "shell", "-c", "from atlas.models import Category; print(Category.objects.get(slug='cms-journey-category').description)"], { cwd: path.join(root, "backend"), env, encoding: "utf8" }).trim().split(/\r?\n/).pop();
  const legacy = await api(`/reviews/category/${fixture.category}/`);
  check(legacy.data.record.revision_status === "legacy" && legacy.data.scientific_status === "unreviewed" && !legacy.data.approval.eligible, "Legacy entering CMS is not automatically reviewed");
  check(legacy.data.canonical_public_eligible, "Category public gate requires its active synthetic child");
  await page.goto(origin + "/admin-console/content/category/new");
  await page.getByLabel("نام علمی انگلیسی (الزامی)", { exact: true }).fill("P04 synthetic proposal");
  await page.getByLabel("نام فارسی", { exact: true }).fill("پیشنهاد آزمون داوری P04");
  await page.getByLabel("توضیح", { exact: true }).fill("دادهٔ مصنوعی برای بررسی workflow؛ محتوای علمی نیست.");
  await page.getByRole("button", { name: "ذخیرهٔ پیشنهاد", exact: true }).click();
  await page.getByRole("heading", { name: "پیشنهاد آزمون داوری P04", exact: true }).waitFor();
  const id = new URL(page.url()).pathname.split("/").pop();
  const reviewPath = `/reviews/category/${id}/`;
  const reviewUrl = origin + `/admin-console/reviews/category/${id}`;
  await page.goto(reviewUrl);
  await page.getByTestId("review-evidence-form").waitFor();
  if (await page.getByRole("button", { name: "افزودن شاهد", exact: true }).isEnabled()) await page.getByRole("button", { name: "افزودن شاهد", exact: true }).click();
  await page.locator(".cms-review-sources button").first().click();
  await page.getByTestId("review-evidence-form").locator("input:not([type=checkbox])").first().fill("Synthetic locator: section 2, table 1");
  for (const box of await page.getByTestId("review-evidence-form").locator("input[type=checkbox]").all()) await box.check();
  await noOverflow("Desktop evidence editor has no document overflow");
  await page.getByTestId("review-submit").click();
  let snapshot = await waitForState(reviewPath, data => data.record.revision_status === "submitted");
  report.journey.push({ event: "submitted", version: snapshot.data.record.version, scientific_status: snapshot.data.scientific_status });
  check(snapshot.data.tasks.length === 2 && snapshot.data.tasks.every(task => task.subject_revision === snapshot.data.tasks[0].subject_revision), "Two separate review tasks bind the exact draft subject");
  await page.getByLabel("بازبین منابع").selectOption(String(fixture.owner_id));
  await page.getByTestId("review-assign-source").click();
  await waitForState(reviewPath, data => data.tasks.find(t => t.review_type === "source").status === "assigned");
  await page.getByLabel("بازبین علمی").selectOption(String(fixture.owner_id));
  await page.getByTestId("review-assign-scientific").click();
  snapshot = await waitForState(reviewPath, data => data.tasks.find(t => t.review_type === "scientific").status === "assigned");
  check(await page.getByTestId("review-approve-scientific").isDisabled(), "Scientific approval is blocked until explicit source check");
  const ack = "به‌عنوان مالک، اگر نویسندهٔ این پیشنهاد هستم، خودبازبینی آن را صریحاً می‌پذیرم.";
  await page.getByTestId("review-approve-source").locator("xpath=ancestor::form").getByLabel(ack, { exact: true }).check();
  await page.getByTestId("review-approve-source").click();
  snapshot = await waitForState(reviewPath, data => data.scientific_status === "source_checked");
  report.journey.push({ event: "source_checked", version: snapshot.data.record.version, scientific_status: snapshot.data.scientific_status });
  await page.getByTestId("review-approve-scientific").locator("xpath=ancestor::form").getByLabel(ack, { exact: true }).check();
  await page.getByTestId("review-approve-scientific").click();
  snapshot = await waitForState(reviewPath, data => data.approval.eligible);
  check(snapshot.data.scientific_status === "reviewed" && snapshot.data.record.canonical_pk === null, "Solo-owner scientific approval is fresh and creates no public canonical row");
  report.journey.push({ event: "approved", version: snapshot.data.record.version, scientific_status: snapshot.data.scientific_status, eligible: true });
  await page.getByText("بله؛ بررسی علمی تازه و معتبر است", { exact: false }).waitFor();
  await screenshot("p04-approved-desktop");
  const history = await api(reviewPath + "history/");
  check(history.data.results.filter(row => row.outcome === "approve").length === 2 && history.data.results.filter(row => row.outcome === "approve").every(row => row.self_review), "Separate explicit self-review source/science decisions are retained");
  check(new Set(history.data.results.map(row => row.revision_hash)).size === 1 && new Set(history.data.results.map(row => row.dependency_digest)).size === 1, "Decision history pins exact revision and dependency digests");
  execFileSync(python, ["manage.py", "shell", "-c", "from atlas.models import SourceReference; s=SourceReference.objects.get(title='CMS synthetic review source'); s.doi='10.5555/synthetic-source-change'; s.save()"], { cwd: path.join(root, "backend"), env, encoding: "utf8" });
  await page.reload();
  snapshot = await waitForState(reviewPath, data => data.approval.blockers.includes("DEPENDENCY_CHANGED"));
  check(!snapshot.data.approval.eligible && snapshot.data.scientific_status === "unreviewed", "A real source mutation invalidates the frozen approval without deleting history");
  report.journey.push({ event: "source_invalidated", version: snapshot.data.record.version, scientific_status: snapshot.data.scientific_status, eligible: false, blockers: snapshot.data.approval.blockers });
  await page.getByTestId("review-reopen").waitFor();
  await screenshot("p04-source-invalidated-desktop");
  await page.setViewportSize({ width: 320, height: 850 }); await noOverflow("320px stale approval detail has no document overflow"); await screenshot("p04-invalidated-320");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByTestId("review-reopen").click();
  await waitForState(reviewPath, data => data.record.revision_status === "draft");
  await page.goto(origin + "/admin-console/reviews/policy");
  await page.getByTestId("review-policy-form").waitFor();
  await page.locator("#review-policy-mode").selectOption("two_person");
  await page.locator("#review-policy-reason").selectOption("TEAM_POLICY");
  await page.locator("#review-policy-method").selectOption("recovery");
  await page.locator("#review-policy-token").fill(fixture.users.owner.tokens[1]);
  await page.getByTestId("review-policy-save").click();
  await waitForState("/reviews/policy/", data => data.mode === "two_person" && data.version === 1);
  await page.getByText("سیاست ذخیره شد و وضعیت تازهٔ سرور دریافت شد. انتشار عمومی انجام نشده است.", { exact: true }).waitFor();
  check((await api("/reviews/policy/")).data.history.count === 1, "Policy UI performs bound MFA step-up and audited versioned mutation");
  await page.goto(reviewUrl);
  await page.getByTestId("review-submit").click();
  snapshot = await waitForState(reviewPath, data => data.record.revision_status === "submitted");
  await page.getByLabel("بازبین منابع").waitFor();
  const candidates = await api(reviewPath + "reviewers/?review_type=source");
  check(candidates.data.results.find(user => user.id === fixture.owner_id)?.conflict === "TWO_PERSON_REQUIRED", "Two-person reviewer lookup reports the author conflict");
  await page.waitForFunction(owner => Array.from(document.querySelectorAll("select option")).some(option => option.value === String(owner) && option.disabled), fixture.owner_id);
  check(await page.getByLabel("بازبین منابع").locator(`option[value='${fixture.owner_id}']`).evaluate(option => option.disabled), "Two-person policy makes the author unavailable for self-assignment in UI");
  const sourceTask = snapshot.data.tasks.find(task => task.review_type === "source");
  const denied = await api(reviewPath + "assign/", { task_id: sourceTask.id, task_version: sourceTask.version, reviewer_id: fixture.owner_id }, snapshot.etag);
  check(denied.status === 409 && denied.data.code === "TWO_PERSON_REQUIRED", "Forged owner self-assignment is independently rejected by service");
  for (const type of ["source", "scientific"]) {
    await page.getByLabel(type === "source" ? "بازبین منابع" : "بازبین علمی").selectOption(String(fixture.users.reviewer.id));
    await page.getByTestId(`review-assign-${type}`).click();
    await waitForState(reviewPath, data => data.tasks.find(t => t.review_type === type).status === "assigned");
  }
  await api("/auth/logout/", {}); await login(fixture.users.reviewer);
  await page.goto(reviewUrl);
  await page.getByTestId("review-approve-source").click();
  await waitForState(reviewPath, data => data.scientific_status === "source_checked");
  await page.getByTestId("review-approve-scientific").click();
  snapshot = await waitForState(reviewPath, data => data.approval.eligible);
  check(snapshot.data.scientific_status === "reviewed", "Two-person proposal completes with an independent assigned reviewer");
  await page.getByText("بله؛ بررسی علمی تازه و معتبر است", { exact: false }).waitFor();
  await screenshot("p04-two-person-approved");
  execFileSync(python, ["manage.py", "shell", "-c", "from atlas.models import SourceReference; SourceReference.objects.get(title='CMS synthetic review source').delete()"], { cwd: path.join(root, "backend"), env, encoding: "utf8" });
  await page.reload();
  snapshot = await waitForState(reviewPath, data => data.approval.blockers.includes("EVIDENCE_MISSING"));
  check(!snapshot.data.approval.eligible, "A deleted explicit source cannot leave any approval eligible");
  await page.getByText("یکی از منابع شاهد دیگر وجود ندارد؛ شاهد جایگزین ثبت و پیشنهاد دوباره بررسی شود.", { exact: true }).waitFor();
  check(true, "Missing evidence blocker is visible in Persian");
  report.journey.push({ event: "source_deleted", version: snapshot.data.record.version,
    scientific_status: snapshot.data.scientific_status, eligible: false, blockers: snapshot.data.approval.blockers });
  await page.goto(origin + "/admin-console/reviews?mine=1");
  await noOverflow("Desktop assigned review queue has no document overflow");
  check((await api(reviewPath + "history/")).data.results.filter(row => row.outcome === "approve").length === 4, "Invalidation and re-review preserve all four approvals across two subjects");
  const publicAfter = execFileSync(python, ["manage.py", "shell", "-c", "from atlas.models import Category; print(Category.objects.get(slug='cms-journey-category').description)"], { cwd: path.join(root, "backend"), env, encoding: "utf8" }).trim().split(/\r?\n/).pop();
  check(publicBefore === publicAfter, "Review and invalidation leave legacy canonical content unchanged");
  check(await page.evaluate(() => localStorage.length) === 0, "Review workflow stores no credentials or snapshots in localStorage");
  check(report.browserErrors.length === 0, "No unexplained browser console/runtime errors");
}
main().then(() => { report.status = "passed"; }).catch(async error => {
  report.status = "failed"; report.failure = error.message; process.exitCode = 1;
  if (page && !page.isClosed()) await screenshot("p04-failure");
}).finally(async () => {
  if (browser) await browser.close();
  await Promise.all(services.reverse().map(child => new Promise(resolve => {
    if (child.exitCode !== null) { resolve(); return; }
    child.once("exit", resolve); child.kill();
  })));
  fs.writeFileSync(path.join(output, "cms-review-browser-report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: report.status, assertions: report.checks.length, failure: report.failure, report: path.join(output, "cms-review-browser-report.json") }));
  // Only known temporary fixture files are removed; screenshots/reports remain available.
  for (const name of ["cms-journey.sqlite3", "cms-journey.sqlite3-journal", "backend.log", "frontend.log"]) fs.rmSync(path.join(temporary, name), { force: true });
});
