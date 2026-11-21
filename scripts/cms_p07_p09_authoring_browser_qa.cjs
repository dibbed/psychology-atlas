// Isolated W07/W09 authoring and provenance browser acceptance. Never opens the persistent database.
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
let chromium;
try { ({ chromium } = require('playwright')); }
catch (error) {
    if (error.code !== 'MODULE_NOT_FOUND') throw error;
    ({ chromium } = require(path.join(os.tmpdir(), 'atlas-p07-browser-tools', 'node_modules', 'playwright')));
}
const root = path.resolve(__dirname, '..');
const backend = path.join(root, 'backend');
const frontend = process.env.CMS_QA_FRONTEND || path.join(root, 'frontend');
const python = process.env.CMS_QA_PYTHON || (process.platform === 'win32' ? path.join(backend, '.venv', 'Scripts', 'python.exe') : 'python');
const origin = 'http://127.0.0.1:3000';
const apiOrigin = 'http://127.0.0.1:8000';
const out = process.env.CMS_QA_OUTPUT || path.join(root, 'qa', 'p07-p09-authoring');
fs.mkdirSync(out, { recursive: true });
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-p09-browser-'));
const database = path.join(temporary, 'cms-journey.sqlite3');
const env = { ...process.env, CMS_QA_PHASE: 'p09', SQLITE_PATH: database,
    NEXT_PUBLIC_API_URL: apiOrigin + '/api', CSRF_TRUSTED_ORIGINS: origin, DEBUG: '1' };
const report = { stage: 'W07-01/W09-01', environment: 'Windows/Chromium/Next production/Django/disposable SQLite/real MFA',
    started_at: new Date().toISOString(), checks: [], screenshots: [], errors: [],
    limits: ['Synthetic NON-SCIENTIFIC fixture only', 'No canonical publication/withdrawal',
        'Local HTTP only, not production TLS', 'No actual user database is opened'] };
const services = [];
let browser;
function check(condition, label) { assert(condition, label); report.checks.push(label); }
function run(command, args, cwd, name) {
    const log = fs.openSync(path.join(temporary, name + '.log'), 'a');
    const child = spawn(command, args, { cwd, env, windowsHide: true, stdio: ['ignore', log, log] });
    fs.closeSync(log); services.push(child); return child;
}
async function ready(url, proc) {
    for (let i = 0; i < 120; i++) {
        if (proc.exitCode !== null) throw Error('Owned ' + url + ' service died before ready');
        try { if ((await fetch(url, { signal: AbortSignal.timeout(1400) })).status < 500) return; } catch {}
        await new Promise(resolve => setTimeout(resolve, 300));
    }
    throw Error('Readiness timeout for owned ' + url);
}
async function login(page, user) {
    await page.goto(origin + '/admin-console');
    await page.getByLabel('نام کاربری', { exact: true }).fill(user.username);
    await page.getByLabel('گذرواژه', { exact: true }).fill(user.password);
    await page.getByRole('button', { name: 'ادامه با گذرواژه', exact: true }).click();
    await page.getByLabel('روش تأیید').selectOption('recovery');
    await page.getByLabel('کد تأیید', { exact: true }).fill(user.tokens[0]);
    await page.getByRole('button', { name: 'تأیید و ورود', exact: true }).click();
    await page.getByRole('button', { name: 'خروج', exact: true }).waitFor();
}
async function shot(page, filename) {
    await page.screenshot({ path: path.join(out, filename + '.png'), fullPage: true });
    report.screenshots.push(filename + '.png');
}
async function noOverflow(page, label) {
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label);
}
(async () => {
    try {
        const fixture = JSON.parse(execFileSync(python, [path.join(root, 'scripts', 'cms_browser_fixture.py')],
            { cwd: backend, env, encoding: 'utf8', timeout: 180000 }));
        check(!!fixture.p09 && !!fixture.users.owner, 'Guarded NON-SCIENTIFIC P09 fixture');
        const helper = path.join(temporary, 'authoring_fixture.py');
        fs.writeFileSync(helper, String.raw`
import json, os, sys
sys.path.insert(0, r"${backend}")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from atlas import cms_content as content
from atlas.cms_content_models import ContentRevision, ContentState
from atlas.models import Concept, ConceptAlias, ResearchDataset, ResearchRecord, TimelineEvent
subject = Concept.objects.create(slug="p07-p09-non-scientific-concept",
    name_en="P07/P09 NON-SCIENTIFIC duplicate concept", simple_definition="NON-SCIENTIFIC fixture only")
duplicate = Concept.objects.create(slug="p07-p09-non-scientific-concept-copy",
    name_en="P07/P09 NON-SCIENTIFIC duplicate concept", simple_definition="NON-SCIENTIFIC duplicate fixture only")
ConceptAlias.objects.create(concept=subject, text="P07P09-NON-SCIENTIFIC-ALIAS")
state = ContentState.objects.create(kind="concept", canonical_pk=subject.pk, legacy_origin=True,
    canonical_digest=content.digest(content.canonical_snapshot("concept", subject)), publication="current")
payload = content.editable_snapshot("concept", subject)
revision = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
    base_digest=state.canonical_digest, payload=payload, payload_digest=content.digest(payload),
    dependency_digest=content.dependencies("concept", subject), status="legacy")
state.current_revision = revision
state.save(update_fields=["current_revision"])
event = TimelineEvent.objects.get(slug="p09-browser-event")
event_state = ContentState.objects.get(kind="timeline-event", canonical_pk=event.pk)
dataset = ResearchDataset.objects.create(key="p07-p09-non-scientific-dataset",
    dataset_name="P09 NON-SCIENTIFIC visible dataset", dataset_version="1",
    source_filename="non-scientific.invalid.json", source_sha256="c" * 64, ingestion_audit={})
record = ResearchRecord.objects.create(dataset=dataset, section="timeline_events",
    external_id="P09-NON-SCIENTIFIC-EXTERNAL", name_en="P09 NON-SCIENTIFIC private name",
    payload={"private_marker": "P09-NON-SCIENTIFIC-PRIVATE-PAYLOAD"},
    promoted_model="atlas.timelineevent", promoted_pk=event.pk)
print(json.dumps({"concept_state": str(state.pk), "duplicate_pk": duplicate.pk,
    "event_state": str(event_state.pk), "record_id": record.pk}))
`);
        const seeded = JSON.parse(execFileSync(python, [helper], { cwd: backend, env, encoding: 'utf8', timeout: 120000 }).trim().split(/\r?\n/).pop());
        check(seeded.concept_state && seeded.event_state && seeded.record_id, 'Synthetic duplicate and lineage rows seeded');

        const django = run(python, ['manage.py', 'runserver', '127.0.0.1:8000', '--noreload'], backend, 'backend');
        await ready(apiOrigin + '/api/admin/auth/csrf/', django);
        const next = run(process.execPath, [path.join(frontend, 'node_modules', 'next', 'dist', 'bin', 'next'), 'start',
            '-p', '3000', '-H', '127.0.0.1'], frontend, 'frontend');
        await ready(origin + '/admin-console', next);
        browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'chrome' } : {}) });
        report.browser_version = browser.version();
        const context = await browser.newContext({ viewport: { width: 1280, height: 950 } });
        const page = await context.newPage();
        page.on('pageerror', error => report.errors.push('pageerror:' + error.name));
        await login(page, fixture.users.owner);
        check(await page.getByRole('button', { name: 'خروج', exact: true }).count() === 1,
            'Actual owner signed in with MFA and session');

        await page.goto(origin + '/admin-console/content/concept/' + seeded.concept_state);
        await page.getByRole('heading', { name: 'P07/P09 NON-SCIENTIFIC duplicate concept' }).waitFor();
        const authoringTab = page.getByRole('button', { name: 'تکرار و اثر بایگانی', exact: true });
        await authoringTab.focus();
        await page.keyboard.press('Enter');
        const authoring = page.getByTestId('domain-authoring-review');
        await authoring.waitFor();
        await authoring.getByText('P07/P09 NON-SCIENTIFIC duplicate concept', { exact: true }).first().waitFor();
        check(await authoringTab.getAttribute('aria-pressed') === 'true', 'Authoring tab is keyboard reachable and selected');
        check(await authoring.evaluate(node => getComputedStyle(node).direction === 'rtl'), 'Authoring panel is RTL');
        check(await authoring.getByText('تکرار احتمالی', { exact: true }).count() === 1, 'Exact-name candidate is probable, not an identity conflict');
        check(await authoring.getByText('P07/P09 NON-SCIENTIFIC duplicate concept', { exact: true }).count() >= 1, 'Duplicate candidate label is rendered');
        check(await authoring.getByText('atlas.conceptalias.concept', { exact: true }).count() === 1, 'Live ORM dependency count is rendered');
        const duplicateRegion = page.getByRole('region', { name: 'نامزدهای تکرار' });
        await duplicateRegion.focus();
        check(await page.evaluate(() => document.activeElement?.getAttribute('aria-label') === 'نامزدهای تکرار'),
            'Duplicate table region receives keyboard focus');
        check((await authoring.textContent()).includes('canonical write: 0'), 'Authoring view states no canonical write');
        await shot(page, 'w07-authoring-desktop');
        await page.setViewportSize({ width: 320, height: 760 });
        await page.reload();
        await page.getByRole('button', { name: 'تکرار و اثر بایگانی', exact: true }).click();
        await page.getByTestId('domain-authoring-review').waitFor();
        await page.getByTestId('domain-authoring-review').getByText('P07/P09 NON-SCIENTIFIC duplicate concept', { exact: true }).first().waitFor();
        await noOverflow(page, '320px authoring view has no document overflow');
        await shot(page, 'w07-authoring-mobile');

        await page.setViewportSize({ width: 1280, height: 950 });
        await page.goto(origin + '/admin-console/content/timeline-event/' + seeded.event_state);
        await page.getByRole('heading', { name: 'P09 NON-SCIENTIFIC event' }).waitFor();
        check(await page.getByRole('button', { name: 'تکرار و اثر بایگانی', exact: true }).count() === 0,
            'Unsupported history kind does not offer duplicate authoring');
        await page.getByRole('button', { name: 'منشأ پژوهشی', exact: true }).click();
        const originPanel = page.getByTestId('domain-origin');
        await originPanel.waitFor();
        await originPanel.getByText('متصل به ResearchRecord', { exact: true }).waitFor();
        check(await originPanel.evaluate(node => getComputedStyle(node).direction === 'rtl'), 'Provenance panel is RTL');
        check(await originPanel.getByText('متصل به ResearchRecord', { exact: true }).count() === 1, 'Linked provenance state is explicit');
        check(await originPanel.getByText('P09 NON-SCIENTIFIC visible dataset', { exact: true }).count() === 1, 'Authorized dataset locator is rendered');
        check(await originPanel.getByText('P09-NON-SCIENTIFIC-EXTERNAL', { exact: true }).count() === 1, 'Persisted external locator is rendered');
        check(!(await originPanel.textContent()).includes('P09-NON-SCIENTIFIC-PRIVATE-PAYLOAD'), 'Raw payload never reaches the provenance panel');
        const originRegion = page.getByRole('region', { name: 'منشأ پژوهش' });
        await originRegion.focus();
        check(await page.evaluate(() => document.activeElement?.getAttribute('aria-label') === 'منشأ پژوهش'),
            'Provenance table region receives keyboard focus');
        await shot(page, 'w09-provenance-desktop');
        await page.setViewportSize({ width: 320, height: 760 });
        await page.reload();
        await page.getByRole('button', { name: 'منشأ پژوهشی', exact: true }).click();
        await page.getByTestId('domain-origin').waitFor();
        await page.getByTestId('domain-origin').getByText('متصل به ResearchRecord', { exact: true }).waitFor();
        await noOverflow(page, '320px provenance view has no document overflow');
        await shot(page, 'w09-provenance-mobile');

        await page.setViewportSize({ width: 1280, height: 950 });
        await page.goto(origin + '/admin-console/content/chronology');
        await page.getByRole('heading', { name: 'زمان‌بندی و ارجاعات تاریخ روان‌شناسی' }).waitFor();
        await page.getByRole('link', { name: '1 locator مجاز' }).first().waitFor();
        check(await page.getByText('1 locator مجاز', { exact: true }).count() >= 1, 'Chronology row exposes linked ResearchRecord origin');
        await shot(page, 'w09-chronology-origin-desktop');
        check(report.errors.length === 0, 'No browser runtime error');
        await context.close();
        report.status = 'PASS';
    } catch (error) {
        report.status = 'FAIL';
        report.failure = String(error?.message || error).slice(0, 900);
        process.exitCode = 1;
    } finally {
        report.completed_at = new Date().toISOString();
        fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
        for (const proc of services) { try { proc.kill(); } catch {} }
        if (browser) await browser.close().catch(() => {});
        try { fs.rmSync(temporary, { recursive: true, force: true }); } catch {}
        console.log(JSON.stringify({ status: report.status, checks: report.checks.length,
            screenshots: report.screenshots.length, errors: report.errors.length,
            failure: report.failure || null }));
    }
})();
