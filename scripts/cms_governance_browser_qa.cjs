// P05 real production services, session/CSRF/MFA, and visibly synthetic governance data.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const net = require("node:net");
const { spawn, execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "atlas-p05-browser-"));
const output = path.join(root, "qa/p05-browser");
fs.mkdirSync(output, { recursive: true });
const python = process.env.CMS_QA_PYTHON || (process.platform === "win32" ? path.join(root, "backend/.venv/Scripts/python.exe") : "python");
const origin = "http://127.0.0.1:3023";
const env = { ...process.env, CMS_QA_PHASE: "p05", DB_ENGINE: "sqlite", DEBUG: "1",
  NEXT_PUBLIC_API_URL: "http://127.0.0.1:8023/api", SQLITE_PATH: path.join(temporary, "cms-journey.sqlite3"),
  CSRF_TRUSTED_ORIGINS: origin, ALLOWED_HOSTS: "127.0.0.1,localhost" };
const report = { phase: "P05", started_at: new Date().toISOString(), runtime: "Production Next / real Django session, CSRF, MFA, services / disposable SQLite / Chromium",
  browserPath: "Existing bundled Playwright QA harness", viewports: [{ width: 1440, height: 1000 }, { width: 320, height: 850 }],
  checks: [], journey: [], browserErrors: [], expectedHttpErrors: [], screenshots: [],
  limitations: ["Visibly synthetic .invalid evidence; no scientific or legal validation", "Chromium only, no real mobile device or screen reader", "Local HTTP; no deployment rehearsal"] };
const check = (condition, label) => { assert(condition, label); report.checks.push(label); };
const mutationObservers = new Map();
const services = [], secretValues = [], expectedResponses = new Set(), badResponses = [], resourceErrors = [];
const recoveryUsed = new Map();
let browser, page;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const sanitize = value => secretValues.reduce((text, secret) => text.split(secret).join("[redacted]"), String(value));
const responsePath = url => new URL(url, origin).pathname.replace(/\/$/, "");
function expectResponse(apiPath, status) { expectedResponses.add(`${responsePath("/api/admin" + apiPath)}:${status}`); }
function start(command, args, cwd, name) {
  const log = fs.openSync(path.join(temporary, name + ".log"), "a");
  const child = spawn(command, args, { cwd, env, windowsHide: true, stdio: ["ignore", log, log] });
  fs.closeSync(log); services.push(child); return child;
}
async function ready(url, child) {
  for (let attempt = 0; attempt < 100; attempt++) {
    assert(child.exitCode === null, "Service stopped before readiness");
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1500) })).status === 200) return; } catch {}
    await pause(300);
  }
  throw new Error("Service readiness timeout");
}
async function requireFreePort(port) {
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", () => reject(new Error(`QA requires unused loopback port ${port}`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}
async function api(apiPath, body, etag, expected = 200) {
  if (expected >= 400) expectResponse(apiPath, expected);
  const http = page.context().request;
  const mutating = body !== undefined;
  const csrf = mutating ? await (await http.get(origin + "/api/admin/auth/csrf/")).json() : null;
  const response = mutating ? await http.post(origin + "/api/admin" + apiPath, { data: body,
    headers: { Origin: origin, "X-CSRFToken": csrf.csrf_token, ...(etag ? { "If-Match": etag } : {}) } })
    : await http.get(origin + "/api/admin" + apiPath);
  const headers = response.headers();
  assert(headers["content-type"]?.includes("application/json"), `Non-JSON API response: ${apiPath} (${response.status()})`);
  const result = { status: response.status(), data: await response.json(), etag: headers.etag, cache: headers["cache-control"] };
  assert.equal(result.status, expected, `${apiPath}: expected ${expected}, received ${result.status} (${result.data.code || "no error code"})`);
  return result;
}
async function waitForState(apiPath, predicate) {
  for (let attempt = 0; attempt < 80; attempt++) {
    const value = await api(apiPath);
    if (predicate(value.data)) return value;
    await pause(150);
  }
  throw new Error(`State did not reach expected result: ${apiPath}`);
}
async function login(user) {
  const index = recoveryUsed.get(user.username) || 0;
  assert(index < user.tokens.length, "Synthetic one-time recovery tokens exhausted");
  expectResponse("/me/", 403);
  await page.goto(origin + "/admin-console");
  await page.getByLabel("نام کاربری", { exact: true }).fill(user.username);
  await page.getByLabel("گذرواژه", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "ادامه با گذرواژه", exact: true }).click();
  await page.getByLabel("روش تأیید").waitFor();
  const beforeMfa = await api("/me/", undefined, undefined, 403);
  check(beforeMfa.data.code === "UNAUTHENTICATED", "Password-only session remains outside the authenticated CMS boundary");
  await page.getByLabel("روش تأیید").selectOption("recovery");
  await page.getByLabel("کد تأیید", { exact: true }).fill(user.tokens[index]);
  await page.getByRole("button", { name: "تأیید و ورود", exact: true }).click();
  await page.getByRole("button", { name: "خروج", exact: true }).waitFor();
  recoveryUsed.set(user.username, index + 1);
}
async function screenshot(name) {
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, name + ".png"), fullPage: true,
    mask: [page.locator(".cms-account bdi, input[name=username], input[type=password], input[name=token], input[autocomplete=one-time-code]")] });
  report.screenshots.push("qa/p05-browser/" + name + ".png");
}
async function noOverflow(label) {
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label);
  check(await page.locator("nextjs-portal").count() === 0, `${label}: no framework overlay`);
}
async function keyboardReach(target) {
  await page.evaluate(() => { document.activeElement?.blur(); document.body.tabIndex = -1; document.body.focus(); });
  for (let attempt = 0; attempt < 80; attempt++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate(element => element === document.activeElement)) {
      check(true, "320px primary governance action is reachable with Tab"); return;
    }
  }
  throw new Error("Primary governance action is not keyboard reachable");
}
async function uiResponse(apiPath, button, status = 200) {
  if (status >= 400) expectResponse(apiPath, status);
  const key = responsePath("/api/admin" + apiPath);
  let timer;
  const received = new Promise((resolve, reject) => {
    mutationObservers.set(key, resolve);
    timer = setTimeout(() => reject(new Error("UI mutation response timeout: " + apiPath)), 30000);
  });
  let result;
  try { [result] = await Promise.all([received, button.click()]); }
  finally { clearTimeout(timer); mutationObservers.delete(key); }
  assert.equal(result.status, status, `${apiPath}: UI received ${result.status} (${result.data.code || "no error code"})`);
  return result;
}
function fixtureState() {
  return JSON.parse(execFileSync(python, ["manage.py", "shell", "-c",
    "import json; from atlas.assessment_models import AssessmentInstrument,AssessmentVersion,AssessmentAccess,AssessmentLanguageForm; i=AssessmentInstrument.objects.get(slug='p05-synthetic-assessment'); v=AssessmentVersion.objects.get(key='p05-synthetic-version'); a=AssessmentAccess.objects.get(key='p05-synthetic-access'); f=AssessmentLanguageForm.objects.get(key='p05-synthetic-fa'); print(json.dumps({'instrument':i.review_status,'version':v.review_status,'access':a.review_status,'availability':a.availability,'license_status':a.license_status,'language_form':f.review_status,'form_authorization':f.authorization_status,'name_en':i.name_en,'name_fa':i.name_fa}))"],
    { cwd: path.join(root, "backend"), env, encoding: "utf8" }).trim().split(/\r?\n/).pop());
}
async function publicAssessment(expected) {
  const response = await fetch("http://127.0.0.1:8023/api/assessments/p05-synthetic-assessment/");
  assert.equal(response.status, expected, "Exact public assessment metadata gate");
  const text = await response.text();
  check(!text.includes("P05_PRIVATE_HISTORY_SENTINEL") && !text.includes("dependency_digest") && !text.includes("actor_ref"), "Public assessment response leaks no private metadata or governance histories");
  return text;
}
const persianNumber = value => String(value).replace(/[0-9]/g, digit => "۰۱۲۳۴۵۶۷۸۹"[digit]);
async function chooseResource(binding) {
  await page.getByLabel("نوع هدف").selectOption(binding.resource_type);
  await page.locator("li").filter({ has: page.getByText(binding.name_en, { exact: true }) })
    .getByRole("button", { name: "انتخاب هدف " + persianNumber(binding.resource_id), exact: true }).click();
}
async function addEvidence(prefix, sourceId) {
  const fieldset = page.locator("#" + prefix);
  await fieldset.getByRole("button", { name: "افزودن شاهد", exact: true }).click();
  await fieldset.getByRole("button", { name: "انتخاب مدرک " + persianNumber(sourceId), exact: true }).click();
  await fieldset.locator(`#${prefix}-0-locator`).fill("SYNTHETIC QA ONLY, section 1; no scientific or legal evidence.");
}
async function fillRights(fixture, status, material, expired = false) {
  await chooseResource(fixture.assessment_binding);
  await page.locator("#rights-material").selectOption(material);
  await page.locator("#rights-intended_use").selectOption("public_display");
  await page.locator("#rights-status").selectOption(status);
  await page.locator("#rights-rightsholder").fill("SYNTHETIC QA ONLY — NO REAL RIGHTSHOLDER");
  await page.locator("#rights-holder_identification").fill("Synthetic test identity; no real owner or legal permission.");
  await page.locator("#rights-public_access").selectOption("public");
  // Dates are anchored to the server's actual local date, not the machine's UTC boundary.
  const today = fixture.today;
  await page.locator("#rights-reviewed_on").fill(today);
  await page.locator("#rights-effective_on").fill(expired ? "2020-01-01" : today);
  if (expired) await page.locator("#rights-expires_on").fill("2020-01-02");
  await page.locator("#rights-limitations").fill("SYNTHETIC QA ONLY; exact scope test, not scientific evidence or legal permission.");
  if (status === "conflict") await page.locator("#rights-conflict_note").fill("Synthetic conflicting claims; no actual ownership dispute.");
  await addEvidence("rights-holder_evidence", fixture.sources.assessment);
  await addEvidence("rights-evidence", fixture.sources.assessment);
}
async function sourcePreview() {
  return uiResponse("/sources/preview/", page.getByRole("button", { name: "ساخت پیش‌نمایش و اعتبارسنجی سرور", exact: true }), 201);
}
async function applyPlan(plan, status = 200) {
  await page.getByLabel("اثر و نگاشت همین طرح را بررسی کرده‌ام و اعمال آن را می‌پذیرم.", { exact: true }).check();
  const result = await uiResponse(`/sources/plans/${plan.id}/apply/`, page.getByRole("button", { name: "اعمال طرح اعتبارسنجی‌شده", exact: true }), status);
  if (status === 200 && plan.operation === "create") await page.waitForURL(origin + `/admin-console/sources/${result.data.receipt.source_ids[0]}`);
  return result;
}
async function sourceEditor(sourceId) {
  await page.goto(origin + `/admin-console/sources/${sourceId}`);
  await page.getByRole("button", { name: "عملیات و پیش‌نمایش", exact: true }).click();
  await page.locator("#source-title").waitFor();
}
async function testSources(fixture) {
  await page.goto(origin + "/admin-console/sources");
  await page.getByRole("link", { name: "ثبت منبع", exact: true }).click();
  await page.locator("#source-title").fill("  P05 SYNTHETIC NON-SCIENTIFIC created source  ");
  await page.locator("#source-citation").fill("SYNTHETIC QA ONLY; not scientific evidence or rights permission.");
  await page.locator("#source-url").fill("https://p05-qa.invalid/created");
  let preview = await sourcePreview();
  check(preview.data.preview.can_apply && preview.data.status === "preview", "Owner source form persists a validated preview before any canonical creation");
  await noOverflow("Desktop source create preview has no overflow");
  await screenshot("p05-source-create-preview");
  const applied = await applyPlan(preview.data);
  check(applied.data.status === "applied" && applied.data.version === 2 && applied.data.receipt.source_ids.length === 1, "Owner applies the exact persisted source plan through the real UI");
  const createdId = applied.data.receipt.source_ids[0];
  const created = await api(`/sources/${createdId}/`);
  check(created.data.source.title === "P05 SYNTHETIC NON-SCIENTIFIC created source" && created.data.source.url.endsWith(".invalid/created"), "Source creation preserves normalized title and visibly synthetic provenance");
  report.journey.push({ event: "source_created", operation: "create", plan_version: applied.data.version });

  await sourceEditor(fixture.sources.mutable);
  await page.locator("#source-title").fill("P05 SYNTHETIC source change must be refused after impact mutation");
  preview = await sourcePreview();
  check(preview.data.preview.can_apply, "Source update has a valid persisted preview before impact changes");
  execFileSync(python, ["manage.py", "shell", "-c",
    `from atlas.models import DisorderSource; link=DisorderSource.objects.get(disorder_id=${fixture.disorder_pk},source_id=${fixture.sources.mutable}); link.note='SYNTHETIC changed claim context after preview; no scientific evidence'; link.save()`],
    { cwd: path.join(root, "backend"), env, encoding: "utf8" });
  const stale = await applyPlan(preview.data, 412);
  check(stale.data.code === "STALE_SOURCE_PLAN", "A real claim-context mutation rejects an otherwise unchanged source preview");
  await page.getByRole("alert").first().waitFor();
  check(await page.getByRole("button", { name: "اعمال طرح اعتبارسنجی‌شده", exact: true }).isDisabled(), "Stale source UI disables replay and requires a new preview");
  const retained = await api(`/sources/plans/${preview.data.id}/`);
  check(retained.data.status === "preview" && retained.data.receipt === null, "Stale apply leaves the retained plan unapplied without a receipt");
  check((await api(`/sources/${fixture.sources.mutable}/`)).data.source.title === "P05 SYNTHETIC NON-SCIENTIFIC mutable source", "Stale apply preserves original canonical source values");
  report.journey.push({ event: "impact_mutation_stale_preview", error: stale.data.code });
  await screenshot("p05-source-stale-impact");

  execFileSync(python, ["manage.py", "shell", "-c",
    `from atlas.models import SourceReference; source=SourceReference.objects.get(pk=${fixture.sources.duplicate}); source.doi=SourceReference.objects.get(pk=${fixture.sources.mutable}).doi; source.save()`],
    { cwd: path.join(root, "backend"), env, encoding: "utf8" });
  await sourceEditor(fixture.sources.mutable);
  await page.getByLabel("عملیات منبع").selectOption("merge");
  await page.getByLabel("شناسهٔ منابع نامزد ادغام؛ منبع فعلی باقی می‌ماند", { exact: true }).fill(String(fixture.sources.duplicate));
  await page.getByRole("button", { name: "دریافت مشخصات و اثر منابع انتخاب‌شده", exact: true }).click();
  await page.locator("input[name='choice-title']").first().waitFor();
  for (const field of ["title", "organization", "citation", "url", "publication_year", "source_type", "authors", "doi", "pmid", "verification_status", "resource_version"]) {
    const choice = page.locator(`input[name='choice-${field}']`).first();
    if (await choice.count()) await choice.check();
  }
  preview = await sourcePreview();
  check(preview.data.operation === "merge" && preview.data.preview.can_apply && preview.data.request.field_choices.title === fixture.sources.mutable, "Merge UI persists explicit per-field survivor choices for matching synthetic identity");
  await page.getByText("مقایسهٔ هویت و فیلدها", { exact: true }).click();
  await screenshot("p05-source-merge-plan");
  report.journey.push({ event: "merge_plan_visible", can_apply: true });

  await sourceEditor(fixture.sources.mutable);
  await page.getByLabel("عملیات منبع").selectOption("split");
  await page.getByLabel("شناسهٔ منابع مقصد تفکیک؛ حداقل دو منبع", { exact: true }).fill(`${createdId}, ${fixture.sources.terminology}`);
  await page.getByRole("button", { name: "دریافت مشخصات و اثر منابع انتخاب‌شده", exact: true }).click();
  await page.getByRole("button", { name: "انتخاب صریح حفظ همهٔ مراجع؛ سپس اصلاح نگاشت‌های لازم", exact: true }).click();
  const mappings = page.locator("[aria-label='اثر تغییر منبع و وابستگی‌ها'] select");
  await mappings.first().waitFor();
  for (const mapping of await mappings.all()) await mapping.selectOption(String(createdId));
  preview = await sourcePreview();
  check(preview.data.operation === "split" && preview.data.preview.can_apply && preview.data.preview.counts.moved === 1 && preview.data.request.mapping.every(row => row.action === "move" && row.target_id === createdId), "Split UI shows a server-validated explicit claim mapping to distinct synthetic publications");
  await page.getByText("نگاشت اعتبارسنجی‌شده", { exact: true }).click();
  await noOverflow("Desktop split plan has no document overflow");
  await screenshot("p05-source-split-plan");
  await page.setViewportSize(report.viewports[1]);
  await noOverflow("320px split mapping and persisted plan have no document overflow");
  await keyboardReach(page.getByRole("button", { name: "ساخت پیش‌نمایش و اعتبارسنجی سرور", exact: true }));
  const [keyboardPreview] = await Promise.all([
    page.waitForResponse(response => responsePath(response.url()) === "/api/admin/sources/preview" && response.request().method() === "POST" && (response.status() < 300 || response.status() >= 400)),
    page.keyboard.press("Enter"),
  ]);
  const keyboardPlan = await keyboardPreview.json();
  check(keyboardPreview.status() === 201 && keyboardPlan.id !== preview.data.id && keyboardPlan.operation === "split", "320px keyboard Enter creates a fresh real server preview from the focused action");
  await page.getByText(keyboardPlan.id, { exact: true }).waitFor();
  await noOverflow("320px keyboard-generated plan remains within the document viewport");
  await screenshot("p05-source-split-320");
  await page.setViewportSize(report.viewports[0]);
  report.journey.push({ event: "split_plan_visible", can_apply: true, moved: 1 });
  report.limitations.push("Claim-context and duplicate-identity setup use guarded synthetic fixture injection; source operations use real UI plans", "Mutation response capture observes a clone of the native browser fetch response before navigation; no HTTP response is mocked", "Merge/split canonical application is outside this browser run");
  return createdId;
}
async function assignGovernance(kind, id, reviewerId) {
  await page.getByRole("button", { name: "بررسی و تصمیم", exact: true }).click();
  await page.getByLabel("بازبین").selectOption(String(reviewerId));
  const result = await uiResponse(`/governance/${kind}/${id}/assign/`, page.getByRole("button", { name: "تخصیص بازبین همین نسخه", exact: true }));
  check(result.data.record.status === "in_review" && result.data.record.assignee_id === reviewerId, `${kind}: real UI assigns the exact immutable proposal to the selected reviewer`);
  return result;
}
async function decideGovernance(kind, id, selfReview, expected = 200) {
  await page.getByLabel("نتیجه").selectOption("approve");
  if (selfReview) await page.getByLabel("اگر مشارکت‌کنندهٔ این پیشنهاد هستم، به‌عنوان مالک خودبازبینی همین نسخه را صریحاً می‌پذیرم.", { exact: true }).check();
  return uiResponse(`/governance/${kind}/${id}/decide/`, page.getByRole("button", { name: /^ثبت تصمیم نسخهٔ / }), expected);
}
async function createRights(fixture, status, material, expired = false) {
  await page.goto(origin + "/admin-console/rights");
  await page.getByRole("link", { name: "پیشنهاد تازه", exact: true }).click();
  await fillRights(fixture, status, material, expired);
  const result = await uiResponse("/governance/rights/", page.getByRole("button", { name: "ارسال پیشنهاد برای بررسی", exact: true }), 201);
  await page.waitForURL(origin + `/admin-console/rights/${result.data.record.id}`);
  await page.getByRole("button", { name: "نمای کلی و موانع", exact: true }).waitFor();
  check(result.data.record.resource_version === fixture.assessment_binding.resource_version && result.data.record.payload.material === material && result.data.record.payload.intended_use === "public_display", "Rights UI binds the selected server resource version, material and use exactly");
  return result.data.record;
}
function scopeEligibility(fixture, material, intendedUse = "public_display", version = fixture.assessment_binding.resource_version) {
  return JSON.parse(execFileSync(python, ["manage.py", "shell", "-c",
    `import json; from atlas.cms_governance import rights_eligibility; print(json.dumps(rights_eligibility('assessment_instrument',${fixture.assessment_binding.resource_id},${JSON.stringify(version)},${JSON.stringify(material)},${JSON.stringify(intendedUse)})))`],
    { cwd: path.join(root, "backend"), env, encoding: "utf8" }).trim().split(/\r?\n/).pop());
}
async function revokeRights(id) {
  await page.goto(origin + `/admin-console/rights/${id}`);
  await page.getByRole("button", { name: "بررسی و تصمیم", exact: true }).click();
  await page.getByLabel("دلیل لغو").selectOption("CORRECTION_REQUIRED");
  const result = await uiResponse(`/governance/rights/${id}/revoke/`, page.getByRole("button", { name: "لغو اجازهٔ همین دامنه", exact: true }));
  check(result.data.record.status === "revoked" && !result.data.record.eligible && result.data.record.blockers.includes("RIGHTS_REVOKED"), "Rights revocation through UI immediately denies the exact scope");
  return result.data.record;
}
async function testRights(fixture) {
  for (const [status, material] of [["unknown", "image"], ["restricted", "text"], ["conflict", "translation"]]) {
    const record = await createRights(fixture, status, material);
    await assignGovernance("rights", record.id, fixture.owner_id);
    const approved = await decideGovernance("rights", record.id, true);
    check(approved.data.record.status === "approved" && approved.data.record.computed_status === status && !approved.data.record.eligible, `${status}: an approved proposal and publicly accessible evidence do not imply permission`);
    const exact = scopeEligibility(fixture, material);
    check(!exact.eligible && !exact.permitted && exact.status === status, `${status}: real exact-scope rights selector remains fail closed`);
    report.journey.push({ event: "rights_" + status, material, eligible: false });
  }
  const expired = await createRights(fixture, "allowed", "instruction", true);
  check(expired.computed_status === "expired" && expired.blockers.includes("RIGHTS_EXPIRED") && !expired.eligible, "An expired allowed proposal is visibly ineligible before decision");
  await assignGovernance("rights", expired.id, fixture.owner_id);
  const refused = await decideGovernance("rights", expired.id, true, 409);
  check(refused.data.code === "RIGHTS_NOT_ELIGIBLE" && refused.data.blockers.includes("RIGHTS_EXPIRED"), "Real UI cannot approve an expired permission scope");
  await page.getByRole("alert").first().waitFor();
  await screenshot("p05-rights-expired-rejected");
  report.journey.push({ event: "rights_expired_approval_denied", material: "instruction", error: refused.data.code });

  const metadata = await createRights(fixture, "allowed", "metadata");
  await publicAssessment(200);
  check(!scopeEligibility(fixture, "metadata").permitted, "A pending metadata proposal preserves legacy public eligibility and grants no permission");
  await assignGovernance("rights", metadata.id, fixture.owner_id);
  const allowed = await decideGovernance("rights", metadata.id, true);
  check(allowed.data.record.eligible && allowed.data.record.computed_status === "allowed", "Fresh metadata permission is approved through explicit owner self-review in UI");
  await publicAssessment(200);
  check(scopeEligibility(fixture, "metadata").permitted && !scopeEligibility(fixture, "metadata", "commercial").permitted && !scopeEligibility(fixture, "metadata", "public_display", "SYNTHETIC-WRONG-VERSION").eligible, "Allowed metadata/public-display rights grant neither commercial use nor a different resource version");
  check(!scopeEligibility(fixture, "item").permitted, "Metadata permission does not manufacture item permission");
  await screenshot("p05-rights-metadata-allowed");
  report.journey.push({ event: "metadata_allowed", public_metadata: true });

  const item = await createRights(fixture, "allowed", "item");
  await publicAssessment(200);
  await assignGovernance("rights", item.id, fixture.owner_id);
  check((await decideGovernance("rights", item.id, true)).data.record.eligible, "Item permission requires its own exact approval");
  await revokeRights(item.id);
  check(!scopeEligibility(fixture, "item").eligible && scopeEligibility(fixture, "metadata").permitted, "Item revocation denies items while the independent metadata permission remains valid");
  await publicAssessment(200);
  report.journey.push({ event: "item_revoked", public_metadata: true });
  await revokeRights(metadata.id);
  await publicAssessment(404);
  check(!scopeEligibility(fixture, "metadata").eligible, "Metadata revocation hides public Assessment metadata immediately");
  await page.getByRole("button", { name: "تاریخچه", exact: true }).click();
  await page.getByRole("heading", { name: "تاریخچهٔ ثبت‌شده در سرور", exact: true }).waitFor();
  const history = await api(`/governance/rights/${metadata.id}/history/`);
  check(history.data.count >= 4 && history.data.results.some(row => row.decisions.some(decision => decision.outcome === "approve")) && history.data.results.some(row => row.decisions.some(decision => decision.outcome === "revoked")), "Metadata approval and revocation remain in immutable server history and visible UI");
  await screenshot("p05-rights-revoked-history");
  report.journey.push({ event: "metadata_revoked", public_metadata: false });
  assert.deepEqual(fixtureState(), fixture.assessment_baseline, "Rights decisions/revocations leave canonical Assessment science, rights fields, names and translation authorization unchanged");
  check(true, "Governance rights actions preserve all canonical Assessment scientific and authorization fields");
  return metadata.id;
}
async function testTerminology(fixture) {
  await page.goto(origin + "/admin-console/terminology");
  await page.getByRole("link", { name: "پیشنهاد تازه", exact: true }).click();
  await chooseResource(fixture.assessment_binding);
  const nameEn = "P05 SYNTHETIC NON-SCIENTIFIC English terminology proposal";
  const nameFa = "پیشنهاد فارسی مصنوعی آزمون؛ علمی و منتشرشده نیست";
  const alternatives = ["گزینهٔ مصنوعی نخست", "گزینهٔ مصنوعی دوم"];
  await page.locator("#terminology-name_en").fill(nameEn);
  await page.locator("#terminology-name_fa").fill(nameFa);
  await page.locator("#terminology-alternatives").fill(alternatives.join("\n"));
  await page.locator("#terminology-selection_note").fill("دلیل انتخاب مصنوعی برای آزمون UI؛ شاهد علمی یا مجوز ترجمه نیست.");
  await addEvidence("terminology-evidence", fixture.sources.terminology);
  check(await page.locator("#terminology-name_en").getAttribute("dir") === "ltr" && await page.locator("#terminology-name_fa").getAttribute("dir") === "rtl", "English and Persian terminology fields retain their explicit writing direction");
  await page.getByRole("region", { name: "پیش‌نمایش راست‌به‌چپ اصطلاح پیشنهادی", exact: true }).getByText(nameFa, { exact: true }).waitFor();
  await page.setViewportSize(report.viewports[1]);
  await noOverflow("320px EN/FA proposal, alternatives and source evidence form have no document overflow");
  await screenshot("p05-terminology-form-320");
  await page.setViewportSize(report.viewports[0]);
  const created = await uiResponse("/governance/terminology/", page.getByRole("button", { name: "ارسال پیشنهاد برای بررسی", exact: true }), 201);
  const id = created.data.record.id;
  check(created.data.record.preview.name_en === nameEn && created.data.record.preview.name_fa === nameFa && JSON.stringify(created.data.record.preview.alternatives) === JSON.stringify(alternatives), "Real terminology submission preserves EN/FA, alternatives and the plain-text proposal preview");
  await page.waitForURL(origin + `/admin-console/terminology/${id}`);
  await assignGovernance("terminology", id, fixture.users.reviewer.id);
  await api("/auth/logout/", {});
  await login(fixture.users.reviewer);
  await page.goto(origin + "/admin-console/terminology");
  await page.getByRole("heading", { name: "اصطلاحات فارسی", exact: true }).waitFor();
  check(await page.getByRole("link", { name: "پیشنهاد تازه", exact: true }).count() === 0, "Reviewer with domain view/decision authority has no proposal creation control");
  await api("/governance/terminology/", created.data.record.payload, undefined, 403);
  check(true, "Forged terminology creation by a non-editor reviewer is independently denied by the service");
  await page.goto(origin + `/admin-console/terminology/${id}`);
  await page.getByRole("button", { name: "بررسی و تصمیم", exact: true }).click();
  const approved = await decideGovernance("terminology", id, false);
  check(approved.data.record.status === "approved" && approved.data.record.eligible, "Independent assigned reviewer approves the exact terminology revision through real UI");
  const before = await api(`/governance/terminology/${id}/history/`);
  check(before.data.results.some(row => row.decisions.some(decision => decision.outcome === "approve" && !decision.self_review)), "Terminology history records independent approval without implicit self-review");
  await page.getByRole("button", { name: "نمای کلی و موانع", exact: true }).click();
  await page.getByText("واجد شرایط همین دامنه در سرور", { exact: true }).waitFor();
  await screenshot("p05-terminology-approved");
  report.journey.push({ event: "terminology_independent_approval", eligible: true, alternatives: alternatives.length });
  await api("/auth/logout/", {});
  await login(fixture.users.owner);
  await sourceEditor(fixture.sources.terminology);
  await page.locator("#source-citation").fill("SYNTHETIC QA evidence mutated through owner UI after terminology approval. No scientific evidence.");
  const preview = await sourcePreview();
  check(preview.data.preview.can_apply, "Terminology evidence mutation has a real validated source-edit preview");
  await applyPlan(preview.data);
  await page.goto(origin + `/admin-console/terminology/${id}`);
  const stale = await waitForState(`/governance/terminology/${id}/`, data => data.record.computed_status === "stale");
  check(!stale.data.record.eligible && stale.data.record.blockers.includes("DEPENDENCY_CHANGED"), "Real source-edit UI invalidates prior terminology approval when its exact evidence changes");
  const after = await api(`/governance/terminology/${id}/history/`);
  check(JSON.stringify(before.data.results) === JSON.stringify(after.data.results), "Evidence invalidation preserves every frozen terminology revision and decision");
  await page.getByText("منبع یا شواهد تغییر کرده؛ بازبینی تازه لازم است", { exact: true }).waitFor();
  await screenshot("p05-terminology-evidence-stale");
  await page.setViewportSize(report.viewports[1]);
  await noOverflow("320px stale terminology detail has no document overflow");
  await screenshot("p05-terminology-stale-320");
  await page.setViewportSize(report.viewports[0]);
  assert.deepEqual(fixtureState(), fixture.assessment_baseline, "Terminology proposal, approval and evidence mutation preserve Assessment names, science, rights and exact-form authorization");
  check(true, "Terminology approval changes no canonical Assessment name or scientific/rights/translation status");
  report.journey.push({ event: "terminology_evidence_mutation_stale", eligible: false, blockers: stale.data.record.blockers });
  return id;
}
async function testAccess(fixture, rightsId, terminologyId) {
  for (const apiPath of [`/sources/${fixture.sources.terminology}/`, `/sources/${fixture.sources.terminology}/history/`, "/sources/export/", "/governance/evidence/"]) {
    const result = await api(apiPath);
    const json = JSON.stringify(result.data);
    check(result.cache.includes("no-store") && !json.includes("P05_PRIVATE_HISTORY_SENTINEL") && !json.includes("private_fixture_marker"), `${apiPath}: owner-facing bibliography/history exposes no raw private legacy metadata and is not cached`);
  }
  const anonymous = await fetch(origin + `/api/admin/governance/rights/${rightsId}/history/`);
  check(anonymous.status === 403 && !(await anonymous.text()).includes("dependency_digest"), "Anonymous session cannot access private governance history");
  await api("/auth/logout/", {});
  await login(fixture.users.reader);
  await page.goto(origin + "/admin-console/sources/new");
  await page.getByRole("heading", { name: "این بخش در دسترس شما نیست", exact: true }).waitFor();
  check(await page.locator("#source-title").count() === 0 && await page.getByRole("button", { name: "ساخت پیش‌نمایش و اعتبارسنجی سرور", exact: true }).count() === 0, "Denied source role sees no source editing or preview controls");
  await api("/sources/", undefined, undefined, 403);
  await api("/sources/preview/", { operation: "create", changes: { title: "SYNTHETIC denied role creation" } }, undefined, 403);
  await api("/governance/resources/?resource_type=assessment_instrument", undefined, undefined, 404);
  for (const [kind, id] of [["rights", rightsId], ["terminology", terminologyId]]) {
    const denied = await api(`/governance/${kind}/${id}/history/`, undefined, undefined, 404);
    check(denied.data.code === "NOT_FOUND" && !denied.data.results && !denied.data.record, `${kind}: out-of-domain reader receives no private history or record existence details`);
    const queue = await api(`/governance/${kind}/`);
    check(queue.data.count === 0 && queue.data.results.length === 0, `${kind}: queue counts and pagination exclude inaccessible Assessment records`);
  }
  expectResponse(`/governance/rights/${rightsId}/`, 404);
  await page.goto(origin + `/admin-console/rights/${rightsId}`);
  await page.getByRole("heading", { name: "این بخش در دسترس شما نیست", exact: true }).waitFor();
  check(!(await page.locator("main").innerText()).includes("SYNTHETIC QA ONLY") && await page.getByRole("button", { name: "تاریخچه", exact: true }).count() === 0, "Denied rights UI contains no proposal payload or private-history tab");
  await page.setViewportSize(report.viewports[1]);
  await noOverflow("320px denied rights page has no document overflow");
  await screenshot("p05-denied-rights-320");
  await page.setViewportSize(report.viewports[0]);
  await api("/auth/logout/", {});
  await login(fixture.users.scoped);
  await api(`/governance/terminology/${terminologyId}/history/`, undefined, undefined, 404);
  check((await api("/governance/rights/")).data.count === 0, "Brain-only role cannot infer Assessment rights counts or terminology histories");
  check(await page.evaluate(() => localStorage.length === 0 && sessionStorage.length === 0), "Governance/auth flows store no credentials, private histories or proposal snapshots in browser storage");
  report.journey.push({ event: "denied_roles_and_private_histories", private_leakage: false });
}
async function main() {
  for (const contract of ["docs/v1.0-p05-source-api.md", "docs/v1.0-p05-governance-api.md"]) assert(fs.existsSync(path.join(root, contract)), "P05 API contracts must be present before execution");
  assert(fs.existsSync(path.join(root, "frontend/.next/BUILD_ID")), "Parent must build production Next before execution");
  report.build_id = fs.readFileSync(path.join(root, "frontend/.next/BUILD_ID"), "utf8").trim();
  const manifest = JSON.parse(fs.readFileSync(path.join(root, "frontend/.next/routes-manifest.json"), "utf8"));
  const rewrites = Array.isArray(manifest.rewrites) ? manifest.rewrites : Object.values(manifest.rewrites).flat();
  assert(rewrites.some(rule => rule.source === "/api/admin/:path*" && rule.destination.startsWith("http://127.0.0.1:8023/api/admin/")), "Production build must rewrite admin traffic only to the disposable QA service on port 8023");
  const routes = Object.keys(JSON.parse(fs.readFileSync(path.join(root, "frontend/.next/server/app-paths-manifest.json"), "utf8")));
  for (const route of ["/admin-console/sources/new/page", "/admin-console/rights/[id]/page", "/admin-console/terminology/[id]/page"]) assert(routes.includes(route), "Production build is missing P05 route " + route);
  await requireFreePort(8023); await requireFreePort(3023);
  const fixture = JSON.parse(execFileSync(python, [path.join(root, "scripts/cms_browser_fixture.py")], { env, encoding: "utf8" }));
  for (const user of Object.values(fixture.users)) secretValues.push(user.username, user.password, ...user.tokens);
  const backend = start(python, ["manage.py", "runserver", "127.0.0.1:8023", "--noreload"], path.join(root, "backend"), "backend");
  await ready("http://127.0.0.1:8023/api/admin/auth/csrf/", backend);
  const frontend = start(process.execPath, [path.join(root, "frontend/node_modules/next/dist/bin/next"), "start", "-p", "3023"], path.join(root, "frontend"), "frontend");
  await ready(origin + "/admin-console", frontend);
  browser = await chromium.launch({ headless: true }); report.chromium = browser.version();
  page = await browser.newPage({ viewport: report.viewports[0] });
  page.setDefaultNavigationTimeout(30000);
  await page.exposeBinding("p05CaptureMutation", (_context, result) => mutationObservers.get(responsePath(result.url))?.(result));
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      const method = args[1]?.method || "GET";
      if (["POST", "PATCH"].includes(method) && /\/api\/admin\/(sources|governance)\//.test(response.url)) {
        const data = await response.clone().json();
        await window.p05CaptureMutation({ url: response.url, status: response.status, data, etag: response.headers.get("ETag") });
      }
      return response;
    };
  });
  page.on("dialog", async dialog => {
    if (dialog.type() === "beforeunload") await dialog.accept();
    else { report.browserErrors.push("Unexpected browser dialog: " + dialog.type()); await dialog.dismiss(); }
  });
  page.on("pageerror", error => report.browserErrors.push(sanitize(error.message)));
  page.on("console", message => { if (message.type() === "error") {
    if (message.text().includes("Failed to load resource")) resourceErrors.push(message.text());
    else report.browserErrors.push(sanitize(message.text()));
  } });
  page.on("response", response => { if (response.status() >= 400) badResponses.push({ path: responsePath(response.url()), status: response.status() }); });
  page.on("requestfailed", request => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") report.browserErrors.push(sanitize(`${new URL(request.url()).pathname}: ${request.failure()?.errorText}`));
  });
  await login(fixture.users.owner);
  const cookies = await page.context().cookies();
  check(cookies.some(cookie => cookie.name === "admin_sessionid" && cookie.httpOnly && cookie.sameSite === "Lax"), "Real MFA login establishes the private HttpOnly admin session");
  expectResponse("/sources/preview/", 403);
  const csrfDenied = await page.evaluate(async () => {
    const response = await fetch("/api/admin/sources/preview/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ operation: "create", changes: { title: "SYNTHETIC blocked CSRF" } }) });
    return { status: response.status, data: await response.json() };
  });
  check(csrfDenied.status === 403, "Source mutation without CSRF is rejected before any preview or canonical write");
  assert.deepEqual(fixtureState(), fixture.assessment_baseline, "Synthetic Assessment baseline is stable before governance");
  await publicAssessment(200);
  await testSources(fixture);
  const rightsId = await testRights(fixture);
  const terminologyId = await testTerminology(fixture);
  await testAccess(fixture, rightsId, terminologyId);
  for (const event of ["source_created", "impact_mutation_stale_preview", "merge_plan_visible", "split_plan_visible", "rights_unknown", "rights_restricted", "rights_conflict", "rights_expired_approval_denied", "metadata_allowed", "item_revoked", "metadata_revoked", "terminology_independent_approval", "terminology_evidence_mutation_stale", "denied_roles_and_private_histories"]) assert(report.journey.some(entry => entry.event === event), "Missing assigned P05 journey: " + event);
  const unexpected = badResponses.filter(response => !expectedResponses.has(response.path + ":" + response.status));
  report.expectedHttpErrors = badResponses.filter(response => expectedResponses.has(response.path + ":" + response.status));
  check(unexpected.length === 0, "All HTTP failures are explicit CSRF/MFA/stale/expired/role-denial probes");
  check(resourceErrors.length <= report.expectedHttpErrors.length, "Resource console errors are accounted for by explicit expected HTTP denials");
  check(report.browserErrors.length === 0, "No unexplained Chromium console, runtime or request errors");
  assert.deepEqual(fixtureState(), fixture.assessment_baseline, "All P05 UI and denied-role journeys preserve canonical Assessment state");
}
main().then(() => { report.status = "passed"; }).catch(async error => {
  report.status = "failed"; report.failure = sanitize(error.message); process.exitCode = 1;
  if (page && !page.isClosed()) { try { await screenshot("p05-failure"); } catch {} }
}).finally(async () => {
  if (browser) await browser.close();
  await Promise.all(services.reverse().map(child => new Promise(resolve => {
    if (child.exitCode !== null) { resolve(); return; }
    child.once("exit", resolve); child.kill();
  })));
  const serialized = sanitize(JSON.stringify(report, null, 2));
  fs.writeFileSync(path.join(output, "cms-governance-browser-report.json"), serialized);
  if (report.status === "passed") fs.writeFileSync(path.join(root, "docs/v1.0-p05-browser-report.json"), serialized);
  console.log(JSON.stringify({ status: report.status, assertions: report.checks.length, failure: report.failure, report: path.join(output, "cms-governance-browser-report.json") }));
  for (const name of ["cms-journey.sqlite3", "cms-journey.sqlite3-journal", "cms-journey.sqlite3-wal", "cms-journey.sqlite3-shm", "backend.log", "frontend.log"]) fs.rmSync(path.join(temporary, name), { force: true });
});
