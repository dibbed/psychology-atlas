// Real P06 production UI/API/worker journey. No HTTP response mocking or canonical promotion.
// Parent handoff: CMS_QA_BUILD_ID=<completed BUILD_ID> NODE_PATH=<bundled tooling> node scripts/cms_intake_browser_qa.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const net = require("node:net");
const crypto = require("node:crypto");
const { spawn, execFileSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const frontendDir = path.resolve(process.env.CMS_QA_FRONTEND_DIR || path.join(root, "frontend"));
const origin = "http://127.0.0.1:3023";
const output = process.env.CMS_QA_OUTPUT ? path.join(process.env.CMS_QA_OUTPUT, "p06") : path.join(root, "qa/p06-browser");
const python = process.env.CMS_QA_PYTHON || (process.platform === "win32" ? path.join(root, "backend/.venv/Scripts/python.exe") : "python");
const report = { phase: "P06", started_at: new Date().toISOString(),
  runtime: "Production Next / real Django session, MFA, CSRF, API and cms_worker --once / owned disposable SQLite and private storage / Chromium",
  viewports: [{ width: 1440, height: 1000 }, { width: 320, height: 850 }],
  checks: [], journey: [], browserErrors: [], expectedHttpErrors: [], screenshots: [],
  limitations: ["NON-SCIENTIFIC .invalid fixtures; no scientific or legal attestation",
    "Chromium desktop and 320px viewport only; no physical mobile, screen reader, Firefox or WebKit",
    "Local HTTP and SQLite; no production deployment, PostgreSQL, proxy/HTTPS or full regression suite",
    "Worker finishes a small three-record job; queued and completed counters/polling are tested, not a visible intermediate running checkpoint",
    "Governance private evidence covers upload/validation/attachment to an unknown rights proposal; no legal attestation or rights approval"] };
const services = [], secrets = [], recoveryUsed = new Map();
const expectedResponses = new Set(), badResponses = [], resourceErrors = [];
let temporary, env, browser, page;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const check = (condition, label) => { assert(condition, label); report.checks.push(label); };
const sanitize = value => secrets.filter(Boolean).reduce((text, secret) => text.split(secret).join("[redacted]"), String(value));
const responsePath = url => new URL(url, origin).pathname.replace(/\/$/, "");
const fa = value => String(value).replace(/[0-9]/g, n => "۰۱۲۳۴۵۶۷۸۹"[n]);
const sha = value => crypto.createHash("sha256").update(value).digest("hex");
function guardEnvironment(value, owned) {
  const resolved = path.resolve(owned);
  assert.equal(path.dirname(resolved), fs.realpathSync(os.tmpdir()), "QA directory must be directly under host TEMP");
  assert(/^atlas-p06-browser-[A-Za-z0-9]+$/.test(path.basename(resolved)), "P06 accepts its exact temporary prefix only");
  assert.equal(value.DB_ENGINE, "sqlite");
  assert.equal(path.resolve(value.SQLITE_PATH), path.join(resolved, "cms-journey.sqlite3"));
  assert.equal(path.resolve(value.CMS_ARTIFACT_ROOT), path.join(resolved, "private"));
}
function runPython(args) {
  guardEnvironment(env, temporary);
  try { return execFileSync(python, args, { cwd: path.join(root, "backend"), env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 120000 }); }
  catch { throw new Error("Guarded Python command failed: " + (args[0] === "manage.py" ? args[1] : "fixture") + "; private output suppressed"); }
}
function artifactFixture(action, id) {
  return JSON.parse(runPython([path.join(root, "scripts/cms_browser_fixture.py"), "--p06-artifact", action, id]));
}
function privateInventory() {
  guardEnvironment(env, temporary);
  const directory = path.join(temporary, "private");
  assert.equal(fs.realpathSync(directory), directory);
  return fs.readdirSync(directory).sort().map(name => {
    assert(/^[0-9a-f]{32}\.json$/.test(name), "Only synthetic artifact storage keys belong to this run");
    const file = path.join(directory, name), stat = fs.lstatSync(file);
    assert(stat.isFile() && !stat.isSymbolicLink() && stat.nlink === 1, "Owned bytes must be ordinary unlinked files");
    return { name, sha256: sha(fs.readFileSync(file)) };
  });
}
function dbState() {
  const source = `import hashlib,json
from django.core.serializers.json import DjangoJSONEncoder
from atlas.models import Category,Disorder,Concept,SourceReference,ResearchDataset,ResearchRecord
from atlas.cms_models import AdminAuditEvent
from atlas.cms_job_models import AdminJob,ResearchRecordDecision
canonical={m.__name__:list(m.objects.order_by('pk').values()) for m in (Category,Disorder,Concept,SourceReference)}
datasets=list(ResearchDataset.objects.order_by('pk'))
print(json.dumps({'canonical':hashlib.sha256(json.dumps(canonical,cls=DjangoJSONEncoder,sort_keys=True).encode()).hexdigest(),'datasets':len(datasets),'archive_hashes':[hashlib.sha256(d.raw_text.encode()).hexdigest() for d in datasets],'inactive':all(not d.is_active for d in datasets),'records':ResearchRecord.objects.count(),'unpromoted':not ResearchRecord.objects.exclude(promoted_pk__isnull=True).exists(),'payload_digest':hashlib.sha256(json.dumps(list(ResearchRecord.objects.order_by('pk').values_list('payload',flat=True)),sort_keys=True).encode()).hexdigest(),'decisions':ResearchRecordDecision.objects.count(),'jobs':list(AdminJob.objects.values('status','progress_done','progress_total','attempt')),'raw_audits':AdminAuditEvent.objects.filter(action='research.raw').count(),'download_audits':AdminAuditEvent.objects.filter(action='artifact.download').count()}))`;
  return JSON.parse(runPython(["manage.py", "shell", "-c", source]).trim().split(/\r?\n/).pop());
}
function start(command, args, cwd, name) {
  guardEnvironment(env, temporary);
  const log = fs.openSync(path.join(temporary, name + ".log"), "a");
  const child = spawn(command, args, { cwd, env, windowsHide: true, stdio: ["ignore", log, log] });
  fs.closeSync(log); services.push(child); return child;
}
async function ready(url, child) {
  for (let i = 0; i < 100; i++) {
    assert(child.exitCode === null, "Owned service exited before readiness");
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1500) })).status === 200) return; } catch {}
    await pause(300);
  }
  throw new Error("Owned service readiness timeout");
}
async function freePort(port) {
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", () => reject(new Error(`QA requires unused loopback port ${port}`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}
async function api(apiPath, body, etag, expected = 200) {
  if (expected >= 400) expectedResponses.add(responsePath("/api/admin" + apiPath) + ":" + expected);
  const http = page.context().request;
  const csrf = body !== undefined ? await (await http.get(origin + "/api/admin/auth/csrf/")).json() : null;
  const response = body === undefined ? await http.get(origin + "/api/admin" + apiPath) : await http.post(origin + "/api/admin" + apiPath,
    { data: body, headers: { Origin: origin, "X-CSRFToken": csrf.csrf_token, ...(etag ? { "If-Match": etag } : {}) } });
  assert.equal(response.status(), expected, `API ${apiPath}: expected ${expected}, received ${response.status()}`);
  return { status: response.status(), data: await response.json(), etag: response.headers().etag };
}
async function uiResponse(apiPath, button, status = 200) {
  const key = responsePath("/api/admin" + apiPath);
  if (status >= 400) expectedResponses.add(key + ":" + status);
  const [result] = await Promise.all([
    page.waitForResponse(response => responsePath(response.url()) === key && ["POST", "PATCH"].includes(response.request().method()) && (response.status() < 300 || response.status() >= 400))
      .then(async response => ({ status: response.status(), data: await response.json(), etag: response.headers().etag,
        request: apiPath === "/research/imports/" || apiPath.endsWith("/cleanup/") ? response.request().postDataJSON() : undefined,
        ifMatch: await response.request().headerValue("if-match") })),
    button.click(),
  ]);
  assert.equal(result.status, status, `UI ${apiPath}: received ${result.status} (${result.data.code || "no error code"})`);
  return result;
}
async function configurePage() {
  page = await browser.newPage({ viewport: report.viewports[0] });
  page.setDefaultTimeout(15000); page.setDefaultNavigationTimeout(30000);
  page.on("pageerror", error => report.browserErrors.push(sanitize(error.message)));
  page.on("console", message => { if (message.type() === "error") {
    if (message.text().includes("Failed to load resource")) resourceErrors.push(message.text());
    else report.browserErrors.push(sanitize(message.text()));
  } });
  page.on("response", response => { if (response.status() >= 400) badResponses.push({ path: responsePath(response.url()), status: response.status() }); });
  page.on("requestfailed", request => { if (request.failure()?.errorText !== "net::ERR_ABORTED") report.browserErrors.push(sanitize(new URL(request.url()).pathname + ": " + request.failure()?.errorText)); });
  page.on("dialog", async dialog => {
    if (dialog.type() === "beforeunload") await dialog.accept();
    else { report.browserErrors.push("Unexpected dialog: " + dialog.type()); await dialog.dismiss(); }
  });
}
async function login(user) {
  const index = recoveryUsed.get(user.username) || 0;
  expectedResponses.add("/api/admin/me:403");
  await page.goto(origin + "/admin-console");
  await page.getByLabel("نام کاربری", { exact: true }).fill(user.username);
  await page.getByLabel("گذرواژه", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "ادامه با گذرواژه", exact: true }).click();
  await page.getByLabel("روش تأیید").waitFor();
  assert.equal((await api("/me/", undefined, undefined, 403)).data.code, "UNAUTHENTICATED");
  await page.getByLabel("روش تأیید").selectOption("recovery");
  await page.getByLabel("کد تأیید", { exact: true }).fill(user.tokens[index]);
  await page.getByRole("button", { name: "تأیید و ورود", exact: true }).click();
  await page.getByRole("button", { name: "خروج", exact: true }).waitFor();
  recoveryUsed.set(user.username, index + 1);
}
async function screenshot(name) {
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, name + ".png"), fullPage: true,
    mask: [page.locator(".cms-account bdi, input, pre, [aria-label='پیش‌نمایش خام خصوصی'], .cms-history-entry bdi")] });
  report.screenshots.push(process.env.CMS_QA_OUTPUT ? path.resolve(output, name + ".png") : "qa/p06-browser/" + name + ".png");
}
async function layout(label) {
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label + ": no document overflow");
  check(await page.locator("main").evaluate(element => getComputedStyle(element).direction === "rtl"), label + ": RTL layout");
}
async function keyboardReach(target, label) {
  await page.evaluate(() => { document.activeElement?.blur(); document.body.tabIndex = -1; document.body.focus(); });
  for (let i = 0; i < 100; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate(element => element === document.activeElement)) { check(true, label); return; }
  }
  throw new Error(label);
}
async function decide(id, action, expected = 200) {
  await page.getByRole("combobox", { name: /^اقدام صریح/ }).selectOption(action);
  if (action === "map") {
    await page.getByLabel("کلید معنایی مشتق", { exact: true }).fill("concept:p06-non-scientific.invalid");
    await page.getByLabel("نام انگلیسی مشتق", { exact: true }).fill("P06 NON-SCIENTIFIC derived .invalid");
    await page.getByLabel("نام فارسی مشتق", { exact: true }).fill("نام مشتق غیرعلمی آزمون");
  }
  await page.getByRole("button", { name: "بررسی تصمیم پیش از ثبت", exact: true }).click();
  await page.getByRole("heading", { name: /^تأیید / }).waitFor();
  const result = await uiResponse(`/research/records/${id}/decisions/`, page.getByRole("button", { name: "ثبت نهایی تصمیم", exact: true }), expected);
  if (expected === 200) await page.waitForFunction(version =>
    document.querySelectorAll("[aria-label='تاریخچهٔ تصمیم‌های مشتق'] details").length === version, result.data.record.version);
  return result;
}
async function testJourney(fixture) {
  const rawMarker = "P06_PRIVATE_RAW_NON_SCIENTIFIC.invalid";
  secrets.push(rawMarker);
  const document = { dataset_metadata: { dataset_name: "P06 NON-SCIENTIFIC isolated .invalid", dataset_version: "p06-qa-1" },
    concepts: [0, 1, 2].map(index => ({ id: `P06-NON-SCIENTIFIC-${index}`, name_en: `P06 NON-SCIENTIFIC .invalid ${index}`,
      name_fa: `رکورد مصنوعی غیرعلمی ${fa(index)}`, definition_en: rawMarker + " " + index, url: "https://p06-qa.invalid/non-scientific" })) };
  const bytes = Buffer.from(JSON.stringify(document, null, 2) + "\n");
  const baseline = dbState();
  await login(fixture.users.intake);
  check((await page.context().cookies()).some(cookie => cookie.name === "admin_sessionid" && cookie.httpOnly && cookie.sameSite === "Lax"), "Password and one-time MFA establish a real HttpOnly CMS session");
  await page.goto(origin + "/admin-console/research/intake");
  await page.getByRole("heading", { name: "ورود و فایل‌های خصوصی", exact: true }).waitFor();
  const uploadButton = page.getByRole("button", { name: "بارگذاری فایل؛ بدون اعتبارسنجی خودکار", exact: true });
  check(await uploadButton.isDisabled(), "UI prevents uploading without a selected file");
  await page.locator("#artifact-file").setInputFiles({ name: "P06-NON-SCIENTIFIC.invalid.json", mimeType: "application/json", buffer: bytes });
  const uploaded = await uiResponse("/artifacts/", uploadButton, 201);
  const artifact = uploaded.data.artifact;
  check(typeof artifact.cleanup_supported === "boolean", "Real artifact metadata exposes typed cleanup_supported platform capability");
  check(artifact.state === "quarantine" && artifact.sha256 === sha(bytes), "Real multipart UI upload creates quarantined bytes with matching SHA-256");
  const card = page.getByRole("region", { name: "جزئیات فایل خصوصی", exact: true });
  await card.getByText("قرنطینه؛ هنوز اعتبارسنجی نشده", { exact: true }).waitFor();
  check(await card.getByRole("button", { name: "بررسی ایجاد کار ورود", exact: true }).count() === 0, "Quarantine has no enqueue control before separate validation");
  expectedResponses.add("/api/admin/research/imports:403");
  const csrf = await page.evaluate(async id => {
    const response = await fetch("/api/admin/research/imports/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ artifact_id: id, request_key: crypto.randomUUID() }) });
    return response.status;
  }, artifact.id);
  check(csrf === 403 && dbState().jobs.length === 0, "Missing-CSRF native browser mutation is denied without creating a job");
  await page.setViewportSize(report.viewports[1]);
  await layout("320px quarantine upload");
  const validate = card.getByRole("button", { name: "اعتبارسنجی جداگانهٔ فایل", exact: true });
  await keyboardReach(validate, "320px validation is reachable with Tab");
  const valid = await uiResponse(`/artifacts/${artifact.id}/validate/`, { click: () => page.keyboard.press("Enter") });
  check(valid.data.artifact.state === "ready" && valid.data.artifact.version > artifact.version, "Keyboard validation transitions quarantine to ready with a new server version");
  await card.getByText("قالب معتبر؛ آمادهٔ استفادهٔ مجاز", { exact: true }).waitFor();
  await screenshot("p06-mobile-ready");
  const [download] = await Promise.all([page.waitForEvent("download"), card.getByRole("link", { name: "دریافت خصوصی با مجوز جاری", exact: true }).click()]);
  check(await download.failure() === null && sha(fs.readFileSync(await download.path())) === sha(bytes), "Authorised UI download returns the exact uploaded bytes");
  await download.delete();
  check(dbState().download_audits === 1, "Private UI download records a real audit event");
  await card.getByRole("button", { name: "بررسی ایجاد کار ورود", exact: true }).click();
  const enqueued = await uiResponse("/research/imports/", card.getByRole("button", { name: "تأیید ایجاد کار", exact: true }), 202);
  const jobId = enqueued.data.job.id;
  check(enqueued.data.job.status === "queued" && dbState().records === 0, "UI creates a durable queued job without running intake in the request");
  check((await api("/research/imports/", enqueued.request, undefined, 202)).data.job.id === jobId && dbState().jobs.length === 1, "Real same-key replay returns the existing job without duplication");
  await card.getByRole("link", { name: "پیگیری کار ایجادشده ←", exact: true }).click();
  await page.getByRole("heading", { name: "در صف", exact: true }).waitFor();
  await page.getByText("پردازش‌شده: ۰ از تعداد کل نامعلوم", { exact: true }).waitFor();
  check(true, "Queued job UI shows actual zero numerator and unknown total");
  await layout("320px queued job");
  const polling = page.waitForResponse(response => responsePath(response.url()) === `/api/admin/jobs/${jobId}` && response.request().method() === "GET" && response.status() === 200, { timeout: 12000 });
  const queuedPoll = await polling;
  check((await queuedPoll.json()).job.status === "queued", "Visible job page performs real automatic queued-state polling");
  runPython(["manage.py", "cms_worker", "--once"]);
  await page.getByRole("heading", { name: "پایان‌یافته", exact: true }).waitFor({ timeout: 20000 });
  await page.getByText("پردازش‌شده: ۳ از ۳", { exact: true }).waitFor();
  const completed = (await api(`/jobs/${jobId}/`)).data.job;
  const imported = dbState();
  check(completed.status === "succeeded" && completed.progress_done === 3 && completed.progress_total === 3 && imported.records === 3, "DB-backed cms_worker --once completes three records and UI polling shows the true numerator");
  check(imported.datasets === 1 && imported.inactive && imported.unpromoted && imported.archive_hashes[0] === sha(bytes), "Intake preserves exact original JSON, an inactive archive and unpromoted records");
  await screenshot("p06-mobile-job-complete");
  await page.goto(origin + "/admin-console/jobs");
  await page.getByRole("combobox", { name: /^وضعیت کار/ }).selectOption("succeeded");
  await page.getByRole("link", { name: /جزئیات ورود پژوهش/ }).waitFor();
  check(await page.getByText("پردازش‌شده: ۳ از ۳", { exact: true }).isVisible(), "Jobs list filters succeeded work and displays persisted progress");
  await layout("320px jobs list");
  const datasetId = completed.result.dataset_id;
  await page.goto(origin + "/admin-console/research");
  await page.getByRole("link", { name: /P06 NON-SCIENTIFIC isolated/ }).waitFor();
  check(await page.getByText("ورود کامل", { exact: true }).isVisible(), "Research dataset UI displays the actual completed import");
  await page.getByRole("link", { name: /P06 NON-SCIENTIFIC isolated/ }).click();
  await page.getByRole("heading", { name: "رکوردهای مجموعهٔ پژوهشی", exact: true }).waitFor();
  await page.locator("tbody tr").first().waitFor();
  check(await page.locator("tbody tr").count() === 3, "Dataset records UI contains all three imported records");
  await layout("320px dataset records");
  const records = (await api(`/research/datasets/${datasetId}/records/`)).data.results;
  check(!JSON.stringify(records).includes(rawMarker) && records.every(record => !("payload" in record)), "Research metadata API omits private payload and raw text");
  const record = records[0];
  await page.getByRole("link", { name: /رکورد مصنوعی غیرعلمی ۰/ }).click();
  await page.getByRole("button", { name: "بازخوانی رکورد و تاریخچه", exact: true }).waitFor();
  check(await page.getByRole("button", { name: "دریافت متن خام؛ با ثبت رویداد دسترسی", exact: true }).count() === 0 && !(await page.locator("body").innerText()).includes(rawMarker), "Metadata-only actor sees neither raw control nor private raw text");
  await api(`/research/records/${record.id}/raw-preview/`, { purpose: "research_review", reason: "RESEARCH_RAW" }, undefined, 403);
  check(dbState().raw_audits === 0, "Direct raw-preview is denied without raw_read and creates no successful access audit");
  const mapped = await decide(record.id, "map");
  check(mapped.data.record.decision.action === "map" && mapped.data.record.version === 1, "Explicit two-step UI mapping appends the first immutable decision");
  await page.getByText("ثبت نگاشت مشتق · نسخهٔ ۱", { exact: false }).waitFor();
  const staged = await decide(record.id, "stage");
  check(staged.data.record.staging_state === "stage" && staged.data.record.version === 2, "UI stages the prior mapping for future review without canonical promotion");
  await page.getByRole("button", { name: "بازخوانی رکورد و تاریخچه", exact: true }).waitFor();
  await screenshot("p06-mobile-staged-record");
  await layout("320px research decision and history");
  await keyboardReach(page.getByRole("combobox", { name: /^اقدام صریح/ }), "320px research decision selector is reachable with Tab");
  const stale = await api(`/research/records/${record.id}/decisions/`, { action: "defer", mapping: {}, reason: "RESEARCH_DEFER" }, '"0"', 412);
  check(stale.data.code === "STALE_REVISION", "Server rejects a stale decision version instead of overwriting history");
  for (const [index, action] of [[1, "defer"], [2, "reject"]]) {
    await page.goto(origin + `/admin-console/research/records/${records[index].id}`);
    await page.getByRole("combobox", { name: /^اقدام صریح/ }).waitFor();
    const decision = await decide(records[index].id, action);
    check(decision.data.record.decision.action === action, `Explicit UI ${action} appends a derived decision while preserving the archive`);
  }
  const afterDecisions = dbState();
  check(afterDecisions.decisions === 4 && afterDecisions.canonical === baseline.canonical && afterDecisions.payload_digest === imported.payload_digest && afterDecisions.archive_hashes[0] === sha(bytes) && afterDecisions.unpromoted, "Map/stage/defer/reject leave canonical rows, all raw payloads and archived bytes unchanged");
  check((await api(`/research/records/${record.id}/history/`)).data.results.map(entry => entry.action).join(",") === "map,stage", "Server history retains both immutable mapping and stage decisions in order");
  const intakePage = page;
  await configurePage();
  await login(fixture.users.foreign);
  check((await api("/research/datasets/")).data.count === 0 && (await api("/artifacts/")).data.count === 0 && (await api("/jobs/")).data.count === 0, "Equally permitted foreign actor cannot enumerate another user's datasets, jobs or artifacts");
  for (const route of [`/artifacts/${artifact.id}/`, `/artifacts/${artifact.id}/download/?purpose=research_review`, `/jobs/${jobId}/`, `/research/datasets/${datasetId}/records/`, `/research/records/${record.id}/`]) await api(route, undefined, undefined, 404);
  check(true, "Foreign actor direct artifact/download/job/dataset/record requests all fail closed with 404");
  await api(`/research/records/${record.id}/raw-preview/`, { purpose: "research_review", reason: "RESEARCH_RAW" }, undefined, 404);
  await api(`/research/records/${record.id}/decisions/`, { action: "defer", mapping: {}, reason: "RESEARCH_DEFER" }, '"2"', 404);
  check(dbState().raw_audits === 0 && dbState().decisions === 4, "Foreign actor with raw_read and decision permissions still cannot read or mutate another actor's private record");
  await page.goto(origin + `/admin-console/jobs/${jobId}`);
  await page.getByRole("heading", { name: "این بخش در دسترس شما نیست", exact: true }).waitFor();
  check(!(await page.locator("body").innerText()).includes(artifact.filename), "Foreign job deep link renders an error without leaking artifact metadata");
  await screenshot("p06-foreign-job-denied");
  await page.close();
  await configurePage();
  await login(fixture.users.owner);
  await page.goto(origin + `/admin-console/research/records/${record.id}`);
  const raw = await uiResponse(`/research/records/${record.id}/raw-preview/`, page.getByRole("button", { name: "دریافت متن خام؛ با ثبت رویداد دسترسی", exact: true }));
  check(raw.data.record.payload.definition_en === document.concepts[0].definition_en && dbState().raw_audits === 1, "Authorised owner UI raw-preview returns preserved payload and records a real access audit");
  await screenshot("p06-owner-raw-masked");
  await page.getByRole("button", { name: "بستن و پاک کردن پیش‌نمایش خام", exact: true }).click();
  check(await page.getByRole("region", { name: "پیش‌نمایش خام خصوصی", exact: true }).count() === 0, "Closing private raw preview removes it from the rendered page");
  await page.goto(origin + "/admin-console/research/intake");
  await page.getByRole("button", { name: "جزئیات و اقدامات فایل", exact: true }).click();
  await page.getByRole("button", { name: "بررسی لغو دسترسی فایل", exact: true }).click();
  const revoked = await uiResponse(`/artifacts/${artifact.id}/revoke/`, page.getByRole("button", { name: "تأیید لغو دسترسی", exact: true }));
  check(revoked.data.artifact.state === "revoked", "Explicit UI revocation changes the current private artifact state");
  await page.getByText("دسترسی لغو شده", { exact: true }).first().waitFor();
  check(await page.getByRole("link", { name: "دریافت خصوصی با مجوز جاری", exact: true }).count() === 0, "Revoked artifact removes the UI download control");
  const denied = await api(`/artifacts/${artifact.id}/download/?purpose=research_review`, undefined, undefined, 409);
  check(denied.data.code === "ARTIFACT_NOT_READY" && !JSON.stringify(denied.data).includes(rawMarker), "Previously valid download URL is denied after revocation without returning bytes");
  check(dbState().records === 3 && dbState().archive_hashes[0] === sha(bytes), "Revocation preserves already imported historical records and original JSON");
  await screenshot("p06-artifact-revoked");
  check(await page.evaluate(() => localStorage.length === 0 && sessionStorage.length === 0), "Private CMS flow stores no credentials or raw data in browser local/session storage");
  await page.close(); page = intakePage;
  report.archiveArtifactId = artifact.id;
  report.journey.push("multipart quarantine", "separate validation", "authorised audited download", "queued durable job", "same-key replay", "real worker", "automatic UI polling and true progress", "dataset and record UI", "map/stage/defer/reject", "raw permission denial and audited owner access", "foreign ownership denials", "revocation denial", "320px RTL keyboard and overflow", "canonical and raw preservation");
}
async function testBrainStaging(fixture) {
  const previousPage = page;
  await configurePage();
  await login(fixture.users.owner);
  const before = dbState();
  const document = { schema_version: "brain-staging-v1",
    dataset_metadata: { key: "synthetic-brain-cms-qa", version: "v1" },
    records: [{ id: "brain-test-one", category: "anatomy", slug: "synthetic-brain-qa",
      name_en: "Synthetic Brain QA Only", kind: "structure", laterality: "bilateral",
      source_version: "synthetic-v1", spatial_scope: "synthetic-only", review_status: "unreviewed",
      source_ids: ["no-source"], source_notes: {"no-source": "unverified synthetic reference"} }] };
  const bytes = Buffer.from(JSON.stringify(document, null, 2) + "\n");
  await page.goto(origin + "/admin-console/research/intake");
  await page.locator("#artifact-kind").selectOption("brain_json");
  await page.locator("#artifact-file").setInputFiles({
    name: "P06-NON-SCIENTIFIC-brain.json", mimeType: "application/json", buffer: bytes,
  });
  const uploaded = await uiResponse("/artifacts/", page.getByRole("button", { name: "بارگذاری فایل؛ بدون اعتبارسنجی خودکار", exact: true }), 201);
  check(uploaded.data.artifact.kind === "brain_json" && uploaded.data.artifact.sha256 === sha(bytes),
    "Brain UI uploads brain-staging-v1 to private quarantine with exact raw checksum");
  const id = uploaded.data.artifact.id;
  const card = page.getByRole("region", { name: "جزئیات فایل خصوصی", exact: true });
  const validated = await uiResponse(`/artifacts/${id}/validate/`,
    card.getByRole("button", { name: "اعتبارسنجی جداگانهٔ فایل", exact: true }));
  check(validated.data.artifact.state === "ready", "Brain structural validation creates ready private artifact only");
  await card.getByRole("button", { name: "بررسی ایجاد کار ورود", exact: true }).click();
  const enqueued = await uiResponse("/research/imports/", card.getByRole("button", { name: "تأیید ایجاد کار", exact: true }), 202);
  await card.getByRole("link", { name: "پیگیری کار ایجادشده ←", exact: true }).click();
  await page.getByRole("heading", { name: "در صف", exact: true }).waitFor();
  runPython(["manage.py", "cms_worker", "--once"]);
  await page.getByRole("heading", { name: "پایان‌یافته", exact: true }).waitFor({timeout:20000});
  const job = (await api(`/jobs/${enqueued.data.job.id}/`)).data.job;
  check(job.status === "succeeded" && job.result.records === 1 && job.progress_done === 1,
    "Real Brain durable worker completes one research staging record");
  const detail = (await api(`/research/datasets/${job.result.dataset_id}/`)).data;
  check(detail.dataset.brain_staging && detail.brain_validation.canonical_writes === 0
    && detail.brain_validation.issues.some(issue => issue.record === "brain-test-one" && issue.code === "unresolved_source"),
    "Brain scoped validation exposes unresolved-source code but no canonical publication");
  await page.goto(origin + `/admin-console/research/${job.result.dataset_id}`);
  await page.getByRole("heading", { name: "اعتبارسنجی ساختار Brain در محیط خصوصی", exact: true }).waitFor();
  await page.getByText("unresolved_source", {exact: true}).waitFor();
  await page.setViewportSize(report.viewports[1]);
  await layout("320px Brain staging validation");
  await screenshot("w06-brain-mobile-validation");
  check(dbState().canonical === before.canonical && dbState().datasets === before.datasets + 1,
    "Brain UI/worker staging does not modify canonical content");
  report.journey.push("Brain JSON multipart upload, validation, durable job, worker, scoped dataset/record and issue report");
  await page.close();
  page = previousPage;
}
async function testGovernanceEvidence(fixture) {
  const previousPage = page;
  await configurePage(); await login(fixture.users.owner);
  let capture;
  const createdResponse = new Promise(resolve => { capture = resolve; });
  await page.exposeBinding("p06CaptureGovernance", (_context, result) => capture(result));
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      if (args[1]?.method === "POST" && new URL(response.url).pathname.replace(/\/$/, "") === "/api/admin/governance/rights") {
        await window.p06CaptureGovernance({ status: response.status, data: await response.clone().json(), etag: response.headers.get("ETag") });
      }
      return response;
    };
  });
  const before = dbState();
  const binding = (await api("/governance/resources/?resource_type=category")).data.results
    .find(item => item.name_en === "P06 NON-SCIENTIFIC .invalid isolated category");
  assert(binding, "Isolated NON-SCIENTIFIC category binding must exist");
  await page.goto(origin + "/admin-console/rights/new");
  await page.getByRole("combobox", { name: /^نوع هدف/ }).selectOption("category");
  await page.getByRole("button", { name: "انتخاب هدف " + fa(binding.resource_id), exact: true }).click();
  const status = page.locator("#rights-status");
  await status.selectOption("restricted");
  check(await status.inputValue() === "restricted", "Governance UI retains restricted as a distinct rights state");
  await status.selectOption("unknown");
  await page.locator("#rights-public_access").selectOption("private");
  await page.locator("#rights-limitations").fill("NON-SCIENTIFIC .invalid QA ONLY; no legal permission, scientific evidence or real rightsholder claim.");
  const evidence = page.locator("#rights-evidence");
  const manifest = Buffer.from(JSON.stringify({ schema_version: "psychology-atlas-evidence-v1",
    title: "P06 NON-SCIENTIFIC private evidence .invalid; no legal permission",
    source_url: "https://p06-qa.invalid/non-scientific-evidence", locator: "NON-SCIENTIFIC QA section 1; not legal or scientific attestation" }));
  await evidence.locator("#rights-evidence-file").setInputFiles({ name: "P06-NON-SCIENTIFIC-private-evidence.invalid.json", mimeType: "application/json", buffer: manifest });
  check(await evidence.getByRole("button", { name: "افزودن فایل آماده به شواهد", exact: true }).isDisabled(), "Governance UI prevents attaching an unvalidated private manifest");
  const upload = await uiResponse("/artifacts/", evidence.getByRole("button", { name: "بارگذاری در قرنطینه", exact: true }), 201);
  const artifact = upload.data.artifact;
  check(artifact.kind === "evidence_json" && artifact.state === "quarantine" && artifact.resource_type === binding.resource_type && artifact.resource_id === binding.resource_id && artifact.resource_version === binding.resource_version && !("storage_key" in artifact), "Governance multipart upload binds a quarantined private manifest to the exact server target version without exposing storage");
  const validated = await uiResponse(`/artifacts/${artifact.id}/validate/`, evidence.getByRole("button", { name: "بررسی ساختار فایل", exact: true }));
  check(validated.data.artifact.state === "ready", "Governance separate schema validation makes the evidence manifest ready");
  await evidence.getByRole("button", { name: "افزودن فایل آماده به شواهد", exact: true }).click();
  await evidence.locator("#rights-evidence-0-locator").fill("NON-SCIENTIFIC QA section 1 .invalid; no legal permission.");
  check(await evidence.getByText("منبع شاهد ۱:", { exact: false }).count() === 1, "Governance UI attaches the validated private manifest as an explicit evidence item");
  await page.setViewportSize(report.viewports[1]);
  await layout("320px governance private evidence form");
  await screenshot("p06-governance-private-evidence-form");
  // Capture a clone of the native response before the real UI's location.assign unloads it.
  let timer;
  let created;
  try {
    [created] = await Promise.all([
      Promise.race([createdResponse, new Promise((_resolve, reject) => { timer = setTimeout(() => reject(new Error("Governance create response timeout")), 30000); })]),
      page.getByRole("button", { name: "ارسال پیشنهاد برای بررسی", exact: true }).click(),
    ]);
  } finally { clearTimeout(timer); }
  assert.equal(created.status, 201, "Governance UI proposal creation HTTP status");
  const proposal = created.data.record;
  await page.waitForURL(origin + `/admin-console/rights/${proposal.id}`);
  await page.getByRole("button", { name: "نمای کلی و موانع", exact: true }).waitFor();
  check(proposal.resource_version === binding.resource_version && proposal.payload.status === "unknown" && proposal.payload.public_access === "private" && proposal.payload.evidence[0].artifact_id === artifact.id && !proposal.eligible && proposal.status === "submitted", "Real governance UI creates an exact-version unknown rights proposal with the private artifact attached and no permission granted");
  const downloaded = await page.context().request.get(origin + `/api/admin/artifacts/${artifact.id}/download/?purpose=rights_review`);
  check(downloaded.status() === 200 && sha(await downloaded.body()) === sha(manifest), "Authorised rights_review download returns the exact private evidence manifest through the guarded endpoint");
  check(dbState().canonical === before.canonical && dbState().decisions === before.decisions, "Private governance evidence creates no canonical change or scientific research decision");
  await screenshot("p06-governance-unknown-proposal");
  report.governanceArtifactId = artifact.id;
  report.journey.push("governance exact-version private manifest upload, validation, attachment and unknown rights proposal");
  await page.close(); page = previousPage;
}
async function testCleanup(fixture) {
  const previousPage = page;
  await configurePage(); await login(fixture.users.owner);
  const baseline = dbState();
  const historicalInventory = privateInventory();
  for (const [id, label] of [[report.archiveArtifactId, "Research archive"], [report.governanceArtifactId, "Governance evidence"]]) {
    const before = artifactFixture("age", id);
    check(before.age_days >= 8 && before.expired && before.bytes_exist, label + ": guarded fixture ages only synthetic owned bytes beyond seven days");
    const snapshot = await api(`/artifacts/${id}/`);
    const held = await api(`/artifacts/${id}/cleanup/`, {}, snapshot.etag, 409);
    const after = artifactFixture("state", id);
    check(held.data.code === "ARTIFACT_RETENTION_HOLD" && after.purged_at === null && after.bytes_sha256 === before.bytes_sha256 && dbState().jobs.length === baseline.jobs.length,
      label + ": real cleanup API returns 409 ARTIFACT_RETENTION_HOLD without a job or byte deletion");
  }
  assert.deepEqual(privateInventory(), historicalInventory, "Retention probes must preserve every owned private file");
  await page.goto(origin + "/admin-console/research/intake");
  const bytes = Buffer.from(JSON.stringify({ dataset_metadata: { dataset_name: "P06 NON-SCIENTIFIC cleanup-only .invalid", dataset_version: "1" },
    concepts: [{ id: "P06-CLEANUP-ONLY.invalid", name_en: "P06 NON-SCIENTIFIC unreferenced cleanup .invalid" }] }));
  await page.locator("#artifact-file").setInputFiles({ name: "P06-NON-SCIENTIFIC-cleanup-only.invalid.json", mimeType: "application/json", buffer: bytes });
  const uploaded = await uiResponse("/artifacts/", page.getByRole("button", { name: "بارگذاری فایل؛ بدون اعتبارسنجی خودکار", exact: true }), 201);
  const artifact = uploaded.data.artifact;
  assert.equal(typeof artifact.cleanup_supported, "boolean", "Cleanup must branch on the actual server capability");
  const card = page.getByRole("region", { name: "جزئیات فایل خصوصی", exact: true });
  const cleanup = card.getByRole("button", { name: "پاکسازی فایل منقضی بدون وابستگی", exact: true });
  await cleanup.waitFor();
  check(await cleanup.isDisabled(), "Fresh quarantine cannot request cleanup through the UI");
  const notExpired = await api(`/artifacts/${artifact.id}/cleanup/`, {}, uploaded.etag, 409);
  check(notExpired.data.code === "ARTIFACT_NOT_EXPIRED", "Real cleanup API denies a fresh artifact with 409 ARTIFACT_NOT_EXPIRED");
  const aged = artifactFixture("age", artifact.id);
  check(aged.age_days >= 8 && aged.expired && aged.bytes_sha256 === sha(bytes) && aged.purged_at === null,
    "One unreferenced synthetic UI upload is aged beyond seven days inside the owned fixture only");
  await card.getByRole("button", { name: "بازخوانی فراداده", exact: true }).click();
  await cleanup.waitFor({ state: "visible" });
  if (artifact.cleanup_supported === false) {
    await card.getByText("پاکسازی فیزیکی در این محیط آماده نیست؛ فایل قابل دریافت نیست و نگهداری می‌شود.", { exact: true }).waitFor();
    check(await cleanup.isDisabled(), "Unsupported cleanup displays the unavailable notice and disables the desktop action");
    await layout("Desktop unsupported cleanup");
    await screenshot("p06-desktop-cleanup-unsupported");
    await page.setViewportSize(report.viewports[1]);
    await layout("320px unsupported cleanup");
    const inventory = privateInventory();
    const before = dbState();
    let cleanupPosts = 0;
    const observe = request => { if (request.method() === "POST" && responsePath(request.url()) === `/api/admin/artifacts/${artifact.id}/cleanup`) cleanupPosts++; };
    page.on("request", observe);
    check(await cleanup.isDisabled(), "Unsupported cleanup remains disabled at 320px");
    await cleanup.click({ force: true });
    await pause(500);
    const metadata = (await api(`/artifacts/${artifact.id}/`)).data.artifact;
    const persisted = artifactFixture("state", artifact.id);
    assert.deepEqual(privateInventory(), inventory, "Unsupported cleanup must preserve all owned private bytes");
    assert.deepEqual(dbState(), before, "Unsupported cleanup must not create a job or change persisted content");
    check(cleanupPosts === 0 && await page.getByRole("heading", { name: "تأیید پاکسازی فایل منقضی بدون وابستگی", exact: true }).count() === 0,
      "Attempted click on disabled unsupported cleanup sends no UI POST and opens no confirmation");
    check(metadata.cleanup_supported === false && metadata.state === "expired" && metadata.purged_at === null
      && persisted.bytes_exist && persisted.bytes_sha256 === aged.bytes_sha256 && persisted.version === aged.version,
      "Unsupported cleanup retains expired metadata and identical physical bytes without a purge receipt");
    check(await card.getByRole("link", { name: "دریافت خصوصی با مجوز جاری", exact: true }).count() === 0,
      "Unsupported expired artifact exposes no download link");
    await screenshot("p06-mobile-cleanup-unsupported");
    page.off("request", observe);
    report.cleanup_evidence = { cleanup_supported: false, unavailable_notice: true, ui_cleanup_posts: cleanupPosts,
      owned_physical_bytes_preserved: true, cleanup_job_created: false, purged_at_persisted: false,
      acceptance: "fail-closed UI only; native Windows deletion not exercised" };
    report.limitations.push("Server reports physical cleanup unavailable; native Windows deletion, native calls and identity receipts were not exercised in this run");
    delete report.archiveArtifactId; delete report.governanceArtifactId;
    report.journey.push("unsupported cleanup notice and disabled UI send no POST and preserve all owned bytes",
      "expired research archive and governance evidence retention holds preserve owned bytes");
    await page.close(); page = previousPage;
    return;
  }
  check(process.platform === "win32" && artifact.cleanup_supported === true,
    "Native Windows runtime and real artifact cleanup_supported:true are required for physical cleanup acceptance");
  report.limitations.push("Unsupported-POSIX cleanup refusal and its disabled UI notice are not exercised by this native Windows browser run");
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some(button => button.textContent === "پاکسازی فایل منقضی بدون وابستگی" && !button.disabled));
  await layout("Desktop expired cleanup");
  await screenshot("p06-desktop-cleanup-expired");
  await page.setViewportSize(report.viewports[1]);
  await layout("320px expired cleanup");
  await keyboardReach(cleanup, "320px cleanup action is reachable with Tab");
  await page.keyboard.press("Enter");
  await page.getByRole("heading", { name: "تأیید پاکسازی فایل منقضی بدون وابستگی", exact: true }).waitFor();
  check(dbState().jobs.length === baseline.jobs.length && artifactFixture("state", artifact.id).bytes_exist,
    "Cleanup first step shows irreversible-deletion confirmation without enqueueing or deleting");
  await screenshot("p06-mobile-cleanup-confirmation");
  const inventory = privateInventory();
  const enqueued = await uiResponse(`/artifacts/${artifact.id}/cleanup/`, page.getByRole("button", { name: "تأیید ایجاد کار پاکسازی", exact: true }), 202);
  assert.deepEqual(enqueued.request, {}, "Cleanup UI POST must have an empty JSON object");
  assert.equal(enqueued.ifMatch, uploaded.etag, "Real UI cleanup If-Match must equal the unchanged uploaded artifact ETag");
  assert.equal(enqueued.data.job.kind, "artifact_cleanup", "Real UI must enqueue the cleanup job kind");
  assert.equal(enqueued.data.job.status, "queued", "Real UI cleanup job must initially be queued");
  check(artifactFixture("state", artifact.id).bytes_exist, "Real UI sends empty JSON and current If-Match, enqueues artifact_cleanup and leaves bytes for the worker");
  await card.getByRole("link", { name: "پیگیری کار پاکسازی ←", exact: true }).click();
  await page.getByRole("heading", { name: "در صف", exact: true }).waitFor();
  const coverage = path.join(temporary, "native-cleanup.cover");
  assert(!fs.existsSync(coverage), "Native deletion trace must be fresh for this worker only");
  runPython(["-m", "trace", "--count", "--file", coverage, "--coverdir", path.join(temporary, "native-coverage"), "manage.py", "cms_worker", "--once"]);
  const completed = (await api(`/jobs/${enqueued.data.job.id}/`)).data.job;
  assert.equal(completed.status, "succeeded", `backend/atlas/cms_artifacts.py process_cleanup via cms_jobs.run_once: ${completed.error_code || completed.status}`);
  check(completed.status === "succeeded" && completed.result.cleaned === true && completed.result.artifact_id === artifact.id
    && completed.progress_done === 1 && completed.progress_total === 1,
    "Actual DB-backed cms_worker --once completes artifact_cleanup with succeeded, cleaned:true and 1/1 progress");
  await page.getByRole("heading", { name: "پایان‌یافته", exact: true }).waitFor({ timeout: 20000 });
  await page.getByText("سرور حذف بایت‌های فایل را تأیید کرده است؛ فراداده و تاریخچه حفظ شده‌اند.", { exact: true }).waitFor();
  check(true, "Cleanup job UI polls the actual successful receipt and displays server-confirmed deletion");
  await layout("320px cleanup receipt");
  await screenshot("p06-mobile-cleanup-complete");
  const persisted = artifactFixture("state", artifact.id);
  check(Object.values(persisted.native_calls).length === 5 && Object.values(persisted.native_calls).every(count => count > 0),
    "Stdlib execution trace proves real Windows CreateFileW/GetFileInformationByHandle/ReadFile/SetFileInformationByHandle/CloseHandle call sites ran without adapter mocks");
  assert.deepEqual(persisted.cleanup_receipt.file_identity, aged.file_identity, "Durable cleanup receipt must pin the exact original owned file identity");
  check(persisted.cleanup_receipt.complete && persisted.cleanup_receipt.directory_identity_matches,
    "Persisted native cleanup receipt is complete and matches the current owned private directory and original file identity");
  const metadata = (await api(`/artifacts/${artifact.id}/`)).data.artifact;
  check(persisted.purged_at !== null && persisted.state === "expired" && !persisted.bytes_exist && Date.parse(metadata.purged_at) === Date.parse(persisted.purged_at)
    && metadata.state === "expired" && persisted.sha256 === sha(bytes) && persisted.size === bytes.length,
    "DB and real metadata API persist purged_at/expired and retained hash/size while the exact owned physical bytes are gone");
  assert.deepEqual(privateInventory(), inventory.filter(item => item.name !== artifact.id.replaceAll("-", "") + ".json"));
  check(true, "Retention worker deletes only the one unreferenced synthetic private file; historical private bytes remain identical");
  const after = dbState();
  check(after.canonical === baseline.canonical && after.payload_digest === baseline.payload_digest && after.decisions === baseline.decisions
    && JSON.stringify(after.archive_hashes) === JSON.stringify(baseline.archive_hashes) && after.jobs.length === baseline.jobs.length + 1,
    "Cleanup and retention denials preserve canonical data, immutable decisions and research archives with only one new cleanup job");
  await page.goto(origin + "/admin-console/research/intake");
  await page.getByRole("row").filter({ hasText: artifact.filename }).getByRole("button", { name: "جزئیات و اقدامات فایل", exact: true }).click();
  await card.getByText("پاکسازی بایت‌های فایل", { exact: true }).waitFor();
  check(await cleanup.isDisabled() && await card.getByRole("link", { name: "دریافت خصوصی با مجوز جاری", exact: true }).count() === 0,
    "Purged artifact UI retains metadata and timestamp, disables repeated cleanup and exposes no download link");
  await screenshot("p06-mobile-artifact-purged");
  report.cleanup_evidence = { age_days: aged.age_days, job_status: completed.status, result_cleaned: completed.result.cleaned,
    progress_done: completed.progress_done, progress_total: completed.progress_total, artifact_state: persisted.state,
    purged_at_persisted: !!persisted.purged_at, owned_physical_bytes_removed: !persisted.bytes_exist,
    historical_private_files_unchanged: true, archive_hold: "409 ARTIFACT_RETENTION_HOLD", governance_hold: "409 ARTIFACT_RETENTION_HOLD" };
  report.cleanup_evidence.native_windows_calls = persisted.native_calls;
  report.cleanup_evidence.adapter_source = "backend/atlas/cms_artifacts.py";
  report.cleanup_evidence.adapter_source_sha256 = persisted.native_source_sha256;
  report.cleanup_evidence.directory_and_file_identity_receipt_verified = true;
  report.cleanup_evidence.acceptance = "passed on current native Windows adapter";
  delete report.archiveArtifactId; delete report.governanceArtifactId;
  report.journey.push("real two-step cleanup UI, empty If-Match POST, durable worker receipt and physical byte removal",
    "expired research archive and governance evidence retention holds preserve owned bytes");
  await page.close(); page = previousPage;
}
async function main() {
  // An exact build ID from the parent is the run authorisation and prevents stale-build claims.
  const build = fs.readFileSync(path.join(frontendDir, ".next/BUILD_ID"), "utf8").trim();
  assert(process.env.CMS_QA_BUILD_ID && process.env.CMS_QA_BUILD_ID === build, "Parent production-build handoff required: set CMS_QA_BUILD_ID to the ready BUILD_ID");
  const manifest = JSON.parse(fs.readFileSync(path.join(frontendDir, ".next/routes-manifest.json"), "utf8"));
  const rewrites = Array.isArray(manifest.rewrites) ? manifest.rewrites : Object.values(manifest.rewrites).flat();
  assert(rewrites.some(rule => rule.source === "/api/admin/:path*" && rule.destination.startsWith("http://127.0.0.1:8023/api/admin/")), "Production admin rewrite must target isolated QA API 8023");
  const routes = Object.keys(JSON.parse(fs.readFileSync(path.join(frontendDir, ".next/server/app-paths-manifest.json"), "utf8")));
  for (const route of ["/admin-console/research/page", "/admin-console/research/intake/page", "/admin-console/research/[id]/page", "/admin-console/research/records/[id]/page", "/admin-console/jobs/page", "/admin-console/jobs/[id]/page"]) assert(routes.includes(route), "Production build missing " + route);
  report.build_id = build;
  await freePort(8023); await freePort(3023);
  temporary = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), "atlas-p06-browser-"));
  secrets.push(temporary);
  env = { ...process.env, CMS_QA_PHASE: "p06", DB_ENGINE: "sqlite", DEBUG: "1", PYTHONIOENCODING: "utf-8",
    SQLITE_PATH: path.join(temporary, "cms-journey.sqlite3"), CMS_ARTIFACT_ROOT: path.join(temporary, "private"), CMS_QA_OWNER_TOKEN: crypto.randomBytes(32).toString("hex"),
    NEXT_PUBLIC_API_URL: "http://127.0.0.1:8023/api", CSRF_TRUSTED_ORIGINS: origin, ALLOWED_HOSTS: "127.0.0.1,localhost" };
  guardEnvironment(env, temporary);
  secrets.push(env.CMS_QA_OWNER_TOKEN);
  const fixture = JSON.parse(runPython([path.join(root, "scripts/cms_browser_fixture.py")]));
  for (const user of Object.values(fixture.users)) secrets.push(user.username, user.password, ...user.tokens);
  const migration = runPython(["manage.py", "shell", "-c", "from django.db.migrations.recorder import MigrationRecorder; print(MigrationRecorder.Migration.objects.filter(app='atlas',name='0043_v100_p06_artifact_cleanup').exists())"]).trim().split(/\r?\n/).pop();
  check(migration === "True", "Fresh owned SQLite fixture applies actual migration 0043 with purged_at");
  runPython(["manage.py", "check"]);
  runPython(["manage.py", "makemigrations", "--check", "--dry-run"]);
  report.backend_checks = { system_check: "passed", migration_drift_check: "passed", migration_0043_applied: true };
  report.isolation = { database: "new TEMP/atlas-p06-browser-*/cms-journey.sqlite3", private_storage: "same owned directory/private", original_database_selected: false, response_mocks: false };
  const backend = start(python, ["manage.py", "runserver", "127.0.0.1:8023", "--noreload"], path.join(root, "backend"), "backend");
  await ready("http://127.0.0.1:8023/api/admin/auth/csrf/", backend);
  const frontend = start(process.execPath, [path.join(frontendDir, "node_modules/next/dist/bin/next"), "start", "-p", "3023"], frontendDir, "frontend");
  await ready(origin + "/admin-console", frontend);
  const { chromium } = require("playwright");
  browser = await chromium.launch({ headless: true, ...(process.env.CMS_QA_CHROME_PATH ? { executablePath: process.env.CMS_QA_CHROME_PATH } : {}) }); report.chromium = browser.version();
  await configurePage(); await testJourney(fixture); await testBrainStaging(fixture); await testGovernanceEvidence(fixture); await testCleanup(fixture);
  report.expectedHttpErrors = badResponses.filter(response => expectedResponses.has(response.path + ":" + response.status));
  check(badResponses.every(response => expectedResponses.has(response.path + ":" + response.status)), "All browser HTTP errors correspond to explicit MFA/CSRF/ownership/retention denial probes");
  check(resourceErrors.length <= report.expectedHttpErrors.length, "Browser resource errors are accounted for by expected denials");
  check(report.browserErrors.length === 0, "No unexplained browser console, runtime or request errors");
}
async function finish() {
  if (browser) await browser.close();
  await Promise.all(services.reverse().map(child => new Promise((resolve, reject) => {
    if (child.exitCode !== null) return resolve();
    const timer = setTimeout(() => reject(new Error("Owned service cleanup timed out")), 10000);
    child.once("exit", () => { clearTimeout(timer); resolve(); }); child.kill();
  })));
  if (temporary) {
    guardEnvironment(env, temporary);
    assert.equal(fs.realpathSync(temporary), path.resolve(temporary), "Refuse cleanup through a substituted path");
    fs.rmSync(temporary, { recursive: true, force: true });
    report.cleanup = { services_stopped: true, disposable_database_and_private_bytes_removed: !fs.existsSync(temporary) };
  }
}
if (process.argv.includes("--self-check")) {
  const temp = path.join(fs.realpathSync(os.tmpdir()), "atlas-p06-browser-selfcheck");
  const safe = { DB_ENGINE: "sqlite", SQLITE_PATH: path.join(temp, "cms-journey.sqlite3"), CMS_ARTIFACT_ROOT: path.join(temp, "private") };
  guardEnvironment(safe, temp);
  assert.throws(() => guardEnvironment({ ...safe, SQLITE_PATH: path.join(root, "backend/data/psychology_atlas.sqlite3") }, temp));
  assert.throws(() => guardEnvironment({ ...safe, CMS_ARTIFACT_ROOT: path.join(root, ".private-artifacts") }, temp));
  assert.throws(() => guardEnvironment(safe, path.join(os.tmpdir(), "atlas-p05-browser-selfcheck")));
  assert.throws(() => guardEnvironment({ ...safe, DB_ENGINE: "postgres" }, temp));
  console.log("P06 guard self-check passed; no app, browser, database or fixture was started.");
} else {
  fs.mkdirSync(output, { recursive: true });
  main().then(() => { report.status = "passed"; }).catch(async error => {
    report.status = "failed"; report.failure = sanitize(error.message); process.exitCode = 1;
    if (page && !page.isClosed()) { try { await screenshot("p06-failure"); } catch {} }
  }).finally(async () => {
    try { await finish(); } catch (error) { report.status = "failed"; report.cleanup_failure = sanitize(error.message); process.exitCode = 1; }
    report.finished_at = new Date().toISOString();
    const serialized = sanitize(JSON.stringify(report, null, 2));
    fs.writeFileSync(path.join(output, "cms-intake-browser-report.json"), serialized);
    if (process.platform === "win32" && !process.env.CMS_QA_OUTPUT) fs.writeFileSync(path.join(root, "docs/v1.0-p06-browser-report.json"), serialized);
    console.log(JSON.stringify({ status: report.status, assertions: report.checks.length, failure: report.failure,
      report: process.platform === "win32" && !process.env.CMS_QA_OUTPUT ? "docs/v1.0-p06-browser-report.json" : path.resolve(output, "cms-intake-browser-report.json") }));
  });
}
