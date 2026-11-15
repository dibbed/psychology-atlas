// Isolated P07 owner/browser acceptance. NEVER use the configured persistent database.
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
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-p07-browser-'));
const out = process.env.CMS_QA_OUTPUT || path.join(root, 'qa', 'p07-browser');
fs.mkdirSync(out, { recursive: true });
const python = process.env.CMS_QA_PYTHON || (process.platform === 'win32' ? path.join(root, 'backend', '.venv', 'Scripts', 'python.exe') : 'python');
const origin = process.env.CMS_QA_ORIGIN || 'http://127.0.0.1:3000';
const builtRewrites = JSON.parse(fs.readFileSync(path.join(root, 'frontend/.next/routes-manifest.json'), 'utf8')).rewrites.afterFiles;
const bakedApi = builtRewrites.find(rule => rule.source === '/api/admin/:path*');
assert(bakedApi, 'Production Next build has no CMS API rewrite');
const expectedApiOrigin = new URL(bakedApi.destination).origin;
const backendOrigin = process.env.CMS_QA_API_ORIGIN || expectedApiOrigin;
assert(backendOrigin === expectedApiOrigin && new URL(backendOrigin).hostname === '127.0.0.1',
  'Backend origin must match production build loopback API rewrite');
const frontendPort = new URL(origin).port, backendPort = new URL(backendOrigin).port;
const env = { ...process.env, CMS_QA_PHASE: 'p07',
    SQLITE_PATH: path.join(temporary, 'cms-journey.sqlite3'),
    NEXT_PUBLIC_API_URL: backendOrigin + '/api', CSRF_TRUSTED_ORIGINS: origin, DEBUG: '1' };
const report = { stage: 'P07', environment: 'Windows/Chromium/Next production/Django/disposable SQLite/real MFA',
    started_at: new Date().toISOString(), checks: [], screenshots: [], errors: [], limits:
    ['Synthetic NON-SCIENTIFIC fixture only', 'No canonical publication/withdrawal (P16)',
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
    for (let i = 0; i < 100; i++) {
        if (proc.exitCode !== null) throw Error('Owned '+url+' service died before ready');
        try { if ((await fetch(url, { signal: AbortSignal.timeout(1400) })).status < 500) return; } catch {}
        await new Promise(resolve => setTimeout(resolve, 300));
    }
    throw Error('Readiness timeout for owned '+url);
}
async function login(page, user) {
    await page.goto(origin+'/admin-console');
    await page.getByLabel('نام کاربری', {exact:true}).fill(user.username);
    await page.getByLabel('گذرواژه', {exact:true}).fill(user.password);
    await page.getByRole('button', {name:'ادامه با گذرواژه', exact:true}).click();
    await page.getByLabel('روش تأیید').selectOption('recovery');
    await page.getByLabel('کد تأیید', {exact:true}).fill(user.tokens[0]);
    await page.getByRole('button', {name:'تأیید و ورود', exact:true}).click();
    await page.getByRole('button', {name:'خروج', exact:true}).waitFor();
}
async function api(page, route, body, etag) {
    return page.evaluate(async ({ route, body, etag }) => {
        const csrf = await fetch('/api/admin/auth/csrf/').then(r=>r.json());
        const response = await fetch('/api/admin'+route, {method: body === undefined ? 'GET' : 'POST',
           headers: body === undefined ? {} : {'Content-Type':'application/json', 'X-CSRFToken':csrf.csrf_token,
                ...(etag ? {'If-Match':etag} : {})},
           ...(body === undefined ? {} : {body: JSON.stringify(body)})});
        return { status:response.status, json:await response.json(), etag:response.headers.get('ETag') };
    }, {route,body,etag});
}
async function shot(page, filename) {
    await page.screenshot({path:path.join(out,filename+'.png'), fullPage:true});
    report.screenshots.push(filename+'.png');
}
(async () => {
  try {
    const fixture=JSON.parse(execFileSync(python,[path.join(root,'scripts','cms_browser_fixture.py')],
       {cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:120000}));
    assert(fixture.p07 && fixture.users.owner);
    const django=run(python,['manage.py','runserver','127.0.0.1:'+backendPort,'--noreload'],
       path.join(root,'backend'),'backend');
    await ready(backendOrigin+'/api/admin/auth/csrf/',django);
    const next=run(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-p',frontendPort],
       path.join(root,'frontend'),'frontend');
    await ready(origin+'/admin-console',next);
    browser=await chromium.launch({headless:true, ...(process.platform === 'win32' ? {channel:'chrome'} : {})});
    report.browser_version=browser.version();
    const context=await browser.newContext({viewport:{width:1280,height:950}});
    const page=await context.newPage();
    page.on('pageerror', e=>report.errors.push('pageerror:'+e.name));
    await login(page,fixture.users.owner);
    check(await page.getByRole('button',{name:'خروج',exact:true}).count()===1,
      'Actual owner signed in with MFA and session');
    let result=await api(page,'/content/schema/');
    check(result.status===200 && result.json.kinds.filter(k=>['core','dsm'].includes(k.domain)).length===17,'Schema response includes all 17 P07 core/DSM kinds');
    const names=result.json.kinds.map(k=>k.kind);
    check(names.includes('concept') && names.includes('dsm-record-relation'),
        'Concept and DSM relations are authorized typed schemas');
    await page.goto(origin+'/admin-console/content/concept/new');
    await page.locator('input[name=slug]').fill('p07-browser-created-non-scientific');
    await page.locator('input[name=name_en]').fill('P07 NON-SCIENTIFIC new concept');
    await page.locator('textarea[name=simple_definition]').fill('P07 browser fixture only, not scientific evidence');
    await page.getByRole('button',{name:'ذخیرهٔ پیشنهاد'}).click();
    await page.waitForURL(/\/admin-console\/content\/concept\/[0-9a-f-]+/);
    const id=page.url().split('/').pop();
    result=await api(page,'/content/concept/'+id+'/');
    check(result.status===200 && result.json.canonical_pk===null && result.json.revision_status==='draft',
      'Browser creates Concept draft without canonical write');
    await page.getByRole('button',{name:'ویرایش پیشنهاد'}).click();
    await page.locator('input[name=name_en]').fill('P07 NON-SCIENTIFIC edited concept');
    await page.getByRole('button',{name:'ذخیرهٔ پیشنهاد'}).click();
    await page.getByText('نسخه 2', {exact:true}).waitFor({timeout:15000});
    result=await api(page,'/content/concept/'+id+'/');
    check(result.status===200 && result.json.version===2 && result.json.canonical_pk===null,
      'Browser edits Concept draft revision with ETag');
    await page.getByRole('button',{name:'پیش‌نمایش و اختلاف'}).click();
    await page.getByRole('button',{name:'اعتبارسنجی پیشنهاد در سرور'}).click();
    await page.getByText('انتشار canonical در این مرحله در دسترس نیست', {exact:false}).first().waitFor();
    check(true,'Candidate validate uses real backend and shows P16 publication blocker');
    await page.getByRole('button',{name:'پیش‌نمایش نامزد از سرور'}).click();
    check((await api(page,'/content/concept/'+id+'/')).json.canonical_pk===null,
      'Private Concept preview has no canonical side effect');
    await shot(page,'p07-concept-preview-desktop');
    await page.goto(origin+'/admin-console/content/dsm');
    await page.getByRole('heading',{name:/DSM؛ درخت و مقایسه/}).waitFor();
    let tree=await api(page,'/content/dsm/tree/?corpus='+fixture.p07.corpus);
    check(tree.status===200 && tree.json.results.some(x=>x.id===fixture.p07.record),
      'DSM tree reads real canonical metadata by corpus');
    let compare=await api(page,'/content/dsm/compare/?left='+fixture.p07.corpus+'&right='+fixture.p07.other_corpus);
    check(compare.status===200 && compare.json.results.some(x=>x.status==='changed'),
      'DSM version comparison exposes changed fields without raw archive');
    let study=await api(page,'/content/dsm/study/?record='+fixture.p07.record);
    let graph=await api(page,'/content/dsm/graph/?corpus='+fixture.p07.corpus+'&record='+fixture.p07.record);
    check(study.status===200 && graph.status===200 && study.json.publication_available===false,
      'DSM study and graph previews are real, private, no-publication');
    check(!JSON.stringify(tree.json).includes('PRIVATE-NON-SCIENTIFIC')
        && !JSON.stringify(compare.json).includes('PRIVATE-NON-SCIENTIFIC'),
      'DSM raw archive is omitted from ordinary viewers');
    const corpusPicker=page.getByRole('combobox',{name:/corpus مبنا/}).first();
    await corpusPicker.selectOption(String(fixture.p07.corpus));
    await page.getByText('P07 NON-SCIENTIFIC parent').first().waitFor();
    await shot(page,'p07-dsm-tree-desktop');
    await page.setViewportSize({width:320,height:760});
    await page.reload();
    await page.getByRole('heading',{name:/DSM؛ درخت و مقایسه/}).waitFor();
    await page.getByRole('combobox',{name:/corpus مبنا/}).first().selectOption(String(fixture.p07.corpus));
    await page.getByText('P07 NON-SCIENTIFIC parent').first().waitFor();
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),
      '320px DSM workspace has no horizontal document overflow');
    await shot(page,'p07-dsm-mobile');
    const limited=await browser.newContext({viewport:{width:320,height:760}});
    const restricted=await limited.newPage();
    await login(restricted,fixture.users.scoped);
    const denied=await api(restricted,'/content/schema/');
    check(denied.status===200
      && denied.json.kinds.filter(k=>['core','dsm'].includes(k.domain)).length===0
      && denied.json.kinds.some(k=>k.domain==='brain'),
      'Scoped Brain staff sees zero Core/DSM schemas while retaining authorized Brain');
    const denial=await api(restricted,'/content/dsm/tree/?corpus='+fixture.p07.corpus);
    check(denial.status===403,'Scoped staff cannot read DSM tree via direct API');
    await restricted.goto(origin+'/admin-console/content/concept');
    check(!(await restricted.getByText('P07 NON-SCIENTIFIC new concept').count()),
      'Scoped staff cannot see Concept draft through direct page');
    await limited.close();
    check(report.errors.length===0,'No unexpected uncaught browser page errors');
    report.status='PASS';
    await context.close();
  } catch(e) {
    report.status='FAIL';
    report.failure=String(e && e.message || e).slice(0,550);
    process.exitCode=1;
  } finally {
    report.completed_at=new Date().toISOString();
    fs.writeFileSync(path.join(root,'docs','v1.0-p07-browser-report.json'),JSON.stringify(report,null,2)+'\n');
    fs.writeFileSync(path.join(out,'p07-browser-report.json'),JSON.stringify(report,null,2)+'\n');
    for(const p of services) { try {p.kill()} catch {} }
    if(browser) await browser.close().catch(()=>{});
    try { fs.rmSync(temporary,{recursive:true,force:true}); } catch {}
    console.log(JSON.stringify({status:report.status,checks:report.checks.length,
       screenshots:report.screenshots.length,errors:report.errors.length,
       failure:report.failure||null,report:'docs/v1.0-p07-browser-report.json'}));
  }
})();
