// Actual account/role/session/MFA controls against synthetic TEMP users only.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
let chromium;try{({chromium}=require('playwright'));}catch(error){if(error.code!=='MODULE_NOT_FOUND')throw error;({chromium}=require(path.join(os.tmpdir(),'atlas-p07-browser-tools/node_modules/playwright')));}
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-p14-browser-'));
const out=process.env.CMS_QA_OUTPUT||path.join(root,'qa/p14-browser');fs.mkdirSync(out,{recursive:true});
const py=process.env.CMS_QA_PYTHON||(process.platform==='win32'?path.join(root,'backend/.venv/Scripts/python.exe'):'python');
const origin=process.env.CMS_QA_ORIGIN||'http://127.0.0.1:3014',api=process.env.CMS_QA_API_ORIGIN||'http://127.0.0.1:8000';
assert(new URL(origin).hostname==='127.0.0.1'&&new URL(api).hostname==='127.0.0.1');
const env={...process.env,DB_ENGINE:'sqlite',SQLITE_PATH:path.join(tmp,'cms-journey.sqlite3'),SQLITE_TEST_PATH:path.join(tmp,'tests.sqlite3'),
  CMS_ARTIFACT_ROOT:path.join(tmp,'private'),CMS_QA_PHASE:'p14',NEXT_PUBLIC_API_URL:api+'/api',CSRF_TRUSTED_ORIGINS:origin,CORS_ALLOWED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P14/P15',status:'RUNNING',checks:[],screenshots:[],errors:[],limits:['Synthetic accounts only','Erase and approved retention remain separate gates','No offline owner identity approval or production recovery']};
let browser;const processes=[];
function check(ok,message){assert(ok,message);report.checks.push(message);}
function start(exe,args,cwd,name){const fd=fs.openSync(path.join(tmp,name+'.log'),'a');const proc=spawn(exe,args,{cwd,env,windowsHide:true,stdio:['ignore',fd,fd]});fs.closeSync(fd);processes.push(proc);return proc;}
async function ready(url,proc){for(let n=0;n<100;n++){assert(proc.exitCode===null,'Owned server exited');try{if((await fetch(url,{signal:AbortSignal.timeout(1500)})).status<500)return;}catch{}await new Promise(resolve=>setTimeout(resolve,300));}throw Error('Owned readiness timeout');}
async function request(page,route,body,etag){return page.evaluate(async({route,body,etag})=>{
  const headers={};if(body!==undefined){headers['X-CSRFToken']=(await(await fetch('/api/admin/auth/csrf/',{cache:'no-store'})).json()).csrf_token;headers['Content-Type']='application/json';if(etag)headers['If-Match']=etag;}
  const response=await fetch('/api/admin'+route,{cache:'no-store',credentials:'same-origin',headers,...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)})});
  return {status:response.status,data:await response.json(),etag:response.headers.get('ETag')};
},{route,body,etag});}
function postResponse(page,suffix){return page.waitForResponse(response=>response.url().replace(/\/$/,'').endsWith(suffix)&&response.request().method()==='POST'&&!(response.status()>=300&&response.status()<400));}
async function visibility(page,hidden){
  await page.evaluate(hidden=>{
    if(hidden){Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>'hidden'});}
    else{delete document.hidden;delete document.visibilityState;}
    document.dispatchEvent(new Event('visibilitychange'));
  },hidden);
}
function privacyState(){return JSON.parse(execFileSync(py,['-c',[
  'import os,json,sqlite3,hashlib','from pathlib import Path',
  'c=sqlite3.connect(Path(os.environ["SQLITE_PATH"]).as_uri()+"?mode=ro",uri=True)',
  'rows=c.execute("SELECT * FROM atlas_usernote ORDER BY id").fetchall()',
  'events=c.execute("SELECT COUNT(*) FROM atlas_adminauditevent WHERE action LIKE \'privacy.read.%\'").fetchone()[0]',
  'leaks=c.execute("SELECT COUNT(*) FROM atlas_adminauditevent WHERE CAST(diff AS TEXT) LIKE \'%P14-SYNTHETIC%\' OR reason LIKE \'%P14-SYNTHETIC%\'").fetchone()[0]',
  'print(json.dumps({"notes":len(rows),"digest":hashlib.sha256(json.dumps(rows).encode()).hexdigest(),"read_audits":events,"audit_content_leaks":leaks}))','c.close()',
].join('\n')],{env,encoding:'utf8'}));}
function exportHistory(){return JSON.parse(execFileSync(py,['-c',[
  'import os,sqlite3,json,hashlib','from pathlib import Path',
  'c=sqlite3.connect(Path(os.environ["SQLITE_PATH"]).as_uri()+"?mode=ro",uri=True)',
  'rows={t:c.execute("SELECT * FROM "+t+" ORDER BY id").fetchall() for t in ["atlas_quizattempt","atlas_quizattemptanswer","atlas_studyactivity","atlas_userflashcardprogress","atlas_dailychallengeattempt","atlas_cognitivedistortionpracticeattempt","atlas_userprogress","atlas_userconceptprogress"]}',
  'print(json.dumps({"counts":[len(v) for v in rows.values()],"digest":hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),"jobs":c.execute("SELECT COUNT(*) FROM atlas_adminjob WHERE kind=\'privacy_export\'").fetchone()[0],"receipts":c.execute("SELECT COUNT(*) FROM atlas_adminauditevent WHERE action=\'privacy.exported\'").fetchone()[0]}))','c.close()',
].join('\n')],{env,encoding:'utf8'}));}
function runWorker(){const result=execFileSync(py,['manage.py','cms_worker','--once'],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:90000});assert(result.trim().endsWith(' succeeded'),'Native worker did not succeed');}
async function login(page,user){page.setDefaultTimeout(20000);page.on('pageerror',error=>report.errors.push(String(error)));await page.goto(origin+'/admin-console');await page.getByLabel('نام کاربری',{exact:true}).fill(user.username);await page.getByLabel('گذرواژه',{exact:true}).fill(user.password);await page.getByRole('button',{name:'ادامه با گذرواژه',exact:true}).click();await page.getByLabel('روش تأیید').selectOption('recovery');await page.getByLabel('کد تأیید',{exact:true}).fill(user.tokens[0]);await page.getByRole('button',{name:'تأیید و ورود',exact:true}).click();await page.getByRole('button',{name:'خروج',exact:true}).waitFor();}
async function openAccount(page,username){await page.goto(origin+'/admin-console/accounts');await page.getByLabel('نام کاربری یا شناسه',{exact:true}).fill(username);await page.getByRole('button',{name:'جست‌وجو',exact:true}).click();await page.locator('li').filter({has:page.getByText(username,{exact:true})}).getByRole('button',{name:'جزئیات مجاز',exact:true}).click();await page.getByRole('heading',{name:'کنترل دسترسی و نشست حساب',exact:true}).waitFor();await page.getByText('فهرست مجوزهای مستقیم',{exact:true}).click();}
async function confirmAccount(page,token){await page.getByLabel('روش تأیید تغییر حساب').selectOption('recovery');await page.getByLabel('کد MFA تغییر حساب',{exact:true}).fill(token);await page.getByRole('button',{name:'اعمال تغییر تأییدشدهٔ حساب',exact:true}).focus();await page.keyboard.press('Enter');}
(async()=>{try{
  const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
  const privateBefore=privacyState();assert.equal(privateBefore.notes,2);
  const backend=start(py,['manage.py','runserver','127.0.0.1:'+new URL(api).port,'--noreload'],path.join(root,'backend'),'django');await ready(api+'/api/admin/auth/csrf/',backend);
  // The production bundle uses the same-origin API rewrite compiled for port8000.
  const next=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-H','127.0.0.1','-p',new URL(origin).port],path.join(root,'frontend'),'next');await ready(origin+'/admin-console',next);
  browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
  const ownerContext=await browser.newContext({viewport:{width:1280,height:850}}),owner=await ownerContext.newPage();await login(owner,fixture.users.owner);
  const scopedContext=await browser.newContext(),scoped=await scopedContext.newPage();await login(scoped,fixture.users.scoped);
  // Test the scoped help before P14 role/session revocation can log this user out.
  await scoped.goto(origin+'/admin-console/help');
  await scoped.getByRole('heading',{name:'راهنمای کاربردی مدیریت Psychology Atlas'}).waitFor();
  check(await scoped.getByRole('link',{name:'سلامت عملیات'}).count()===0,
    'P19 restricted CMS guide omits owner-only operational link');
  const scopedMe=await request(scoped,'/me/'),target=scopedMe.data.user.id;
  check((await request(scoped,'/users/')).status===403&&(await request(scoped,'/roles/users/'+target+'/')).status===403,'Content curator cannot read account or role metadata');
  await openAccount(owner,fixture.users.scoped.username);
  const initial=await request(owner,'/roles/users/'+target+'/');
  check(Array.isArray(initial.data.direct_permissions)&&initial.data.direct_permissions.includes('cms_brain_view'),
    'Actual role editor receives direct permissions separately from inherited effective grants');
  await owner.getByLabel('جست‌وجوی مجوز مستقیم',{exact:true}).fill('cms_source_view');
  await owner.getByRole('checkbox',{name:'cms_source_view',exact:true}).check();
  await owner.locator('.cms-context').getByText('تغییرات ذخیره نشده',{exact:true}).waitFor();
  await owner.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  check(await owner.getByRole('checkbox',{name:'cms_source_view',exact:true}).isChecked()&&
    await owner.getByRole('button',{name:'بررسی تغییر دسترسی حساب',exact:true}).isEnabled(),
    'Dirty notification preserves the unsaved direct grant and its version snapshot');
  await owner.getByRole('button',{name:'بررسی تغییر دسترسی حساب',exact:true}).click();
  const directSaved=postResponse(owner,'/roles/users/'+target);await confirmAccount(owner,fixture.users.owner.tokens[1]);
  check((await directSaved).status()===200,'Keyboard and fresh MFA save a real direct grant through RolePolicy');
  await owner.goto(origin+'/admin-console/roles');await owner.getByRole('button',{name:'ساخت گروه نقش تازه',exact:true}).click();
  await owner.getByLabel('نام گروه تازه',{exact:true}).fill('P14 synthetic learning viewers');
  await owner.getByLabel('جست‌وجوی مجوز گروه',{exact:true}).fill('cms_learning_view');
  await owner.getByRole('checkbox',{name:'cms_learning_view',exact:true}).check();
  await owner.getByRole('button',{name:'بررسی ذخیرهٔ گروه',exact:true}).click();
  await owner.getByLabel('روش تأیید گروه').selectOption('recovery');await owner.getByLabel('کد MFA گروه',{exact:true}).fill(fixture.users.owner.tokens[2]);
  const created=postResponse(owner,'/roles/groups');await owner.getByRole('button',{name:'اعمال تغییر تأییدشدهٔ گروه',exact:true}).click();check((await created).status()===200,'Real group creation is policy-versioned, MFA-bound and audited');
  const groupList=await request(owner,'/roles/groups/?page=1&page_size=100');
  const pageTarget=groupList.data.results.find(group=>group.name==='P14 pagination fixture 00');assert(pageTarget);
  await owner.locator('li').filter({has:owner.getByText(pageTarget.name,{exact:true})}).getByRole('button',{name:'ویرایش گروه',exact:true}).click();
  await owner.getByLabel('جست‌وجوی مجوز گروه',{exact:true}).fill('cms_source_view');
  await owner.getByRole('checkbox',{name:'cms_source_view',exact:true}).check();
  const concurrent=await request(owner,'/roles/groups/'+pageTarget.id+'/',{permissions:['cms_learning_view','cms_learning_create']},groupList.etag);assert.equal(concurrent.status,200);
  await owner.getByRole('button',{name:'بعد',exact:true}).click();
  await owner.getByRole('dialog').getByRole('button',{name:'ترک بدون ذخیره',exact:true}).click();
  await owner.getByText('صفحهٔ 2',{exact:true}).waitFor();
  check(await owner.getByLabel('جست‌وجوی مجوز گروه',{exact:true}).count()===0,
    'Confirmed pagination discards the old group draft instead of rebinding it to a concurrent fresh policy tag');
  const protectedGroup=await request(owner,'/roles/groups/'+pageTarget.id+'/');
  check(protectedGroup.data.permissions.includes('cms_learning_create')&&!protectedGroup.data.permissions.includes('cms_source_view'),
    'Discarded group editing preserves the real concurrent role update');
  await openAccount(owner,fixture.users.scoped.username);
  if(await owner.getByRole('checkbox',{name:'P14 synthetic learning viewers',exact:true}).count()===0)
    await owner.getByRole('button',{name:'گروه‌های بعد',exact:true}).click();
  await owner.getByRole('checkbox',{name:'P14 synthetic learning viewers',exact:true}).check();
  await owner.getByRole('button',{name:'بررسی تغییر دسترسی حساب',exact:true}).click();
  const assigned=postResponse(owner,'/roles/users/'+target);await confirmAccount(owner,fixture.users.owner.tokens[3]);assert.equal((await assigned).status(),200);
  const membership=await request(owner,'/roles/users/'+target+'/');
  check(membership.data.permissions.includes('cms_learning_view')&&!membership.data.direct_permissions.includes('cms_learning_view')&&membership.data.direct_permissions.includes('cms_source_view'),
    'Group assignment creates inherited access without copying it into direct grants');
  const ownContext=await browser.newContext(),ownPage=await ownContext.newPage();await login(ownPage,fixture.users.reader);
  const ownMe=await request(ownPage,'/me/');let unexpectedProofs=0;
  ownPage.on('request',request=>{if(request.url().includes('/api/admin/auth/step-up'))unexpectedProofs++;});
  await ownPage.getByRole('navigation',{name:'بخش‌های مدیریت'}).getByRole('link',{name:'امنیت حساب من',exact:true}).click();
  await ownPage.getByRole('button',{name:'بررسی لغو این نشست',exact:true}).first().click();
  check(await ownPage.getByLabel('کد MFA تغییر حساب',{exact:true}).count()===0,
    'Own-session confirmation follows the self contract without a cross-user revoke capability');
  const ownRevoked=postResponse(ownPage,'/sessions/'+ownMe.data.session.id+'/revoke');
  await ownPage.getByRole('button',{name:'اعمال تغییر تأییدشدهٔ حساب',exact:true}).click();assert.equal((await ownRevoked).status(),200);
  await ownPage.getByLabel('نام کاربری',{exact:true}).waitFor();
  check(unexpectedProofs===0&&(await request(owner,'/me/')).status===200,'Least-privilege staff revoke only their own session and the owner remains signed in');
  await ownContext.close();
  await owner.getByRole('button',{name:'بازخوانی نشست‌های حساب',exact:true}).click();
  await owner.getByRole('button',{name:'بررسی لغو این نشست',exact:true}).first().click();
  const revoked=postResponse(owner,'/sessions/'+scopedMe.data.session.id+'/revoke');await confirmAccount(owner,fixture.users.owner.tokens[4]);assert.equal((await revoked).status(),200);
  check((await request(scoped,'/me/')).status===403,'Revoking a selected session immediately fences the actual second browser');
  await openAccount(owner,fixture.users.owner.username);await owner.getByLabel('جست‌وجوی مجوز مستقیم',{exact:true}).fill('cms_owner');
  await owner.getByRole('checkbox',{name:'cms_owner',exact:true}).uncheck();await owner.getByRole('button',{name:'بررسی تغییر دسترسی حساب',exact:true}).click();
  const lastOwner=postResponse(owner,'/roles/users/'+(await request(owner,'/me/')).data.user.id);await confirmAccount(owner,fixture.users.owner.tokens[5]);
  const refused=await lastOwner;check(refused.status()===409&&(await refused.json()).code==='LAST_OWNER'&&(await request(owner,'/me/')).status===200,
    'Last Owner removal rolls back and the real owner session remains valid');
  await openAccount(owner,fixture.users.scoped.username);
  await owner.getByRole('checkbox',{name:'حساب فعال است',exact:true}).uncheck();await owner.getByRole('button',{name:'بررسی تغییر دسترسی حساب',exact:true}).click();
  const disabled=postResponse(owner,'/roles/users/'+target);await confirmAccount(owner,fixture.users.owner.tokens[6]);check((await disabled).status()===200&&(await request(owner,'/users/'+target+'/')).data.is_active===false,'Sensitive account deactivation uses existing security-generation revocation');
  await owner.setViewportSize({width:320,height:790});
  const permissionSummary=owner.getByText('فهرست مجوزهای مستقیم',{exact:true});
  if(await permissionSummary.locator('..').getAttribute('open')!==null)await permissionSummary.click();
  await owner.getByRole('heading',{name:'کنترل دسترسی و نشست حساب',exact:true}).scrollIntoViewIfNeeded();
  check(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&getComputedStyle(document.querySelector('[dir="rtl"]')).direction==='rtl'),'Account controls fit a 320px RTL viewport');
  await owner.screenshot({path:path.join(out,'account-controls-mobile.png'),fullPage:true});report.screenshots.push('account-controls-mobile.png');
  const privacyContext=await browser.newContext({viewport:{width:320,height:790}}),privacy=await privacyContext.newPage();
  await login(privacy,fixture.users.privacy_operator);
  await privacy.getByRole('navigation',{name:'بخش‌های مدیریت'}).getByRole('link',{name:'حساب‌ها',exact:true}).click();
  await privacy.getByLabel('نام کاربری یا شناسه',{exact:true}).fill(fixture.p14.subject_username);
  await privacy.getByRole('button',{name:'جست‌وجو',exact:true}).click();
  await privacy.locator('li').filter({has:privacy.getByText(fixture.p14.subject_username,{exact:true})}).getByRole('button',{name:'جزئیات مجاز',exact:true}).click();
  await privacy.getByRole('link',{name:'دسترسی هدفمند به اطلاعات شخصی این کاربر',exact:true}).click();
  await privacy.getByRole('heading',{name:'دسترسی هدفمند به اطلاعات شخصی',exact:true}).waitFor();
  check(await privacy.getByText('P14-SYNTHETIC-PRIVATE-NOTE <b>literal text</b>',{exact:true}).count()===0,
    'No personal content is fetched or rendered before an explicit purpose-bound MFA read');
  const reference=crypto.randomUUID();await privacy.getByLabel('شناسهٔ UUID درخواست پشتیبانی',{exact:true}).fill(reference);
  await privacy.getByRole('checkbox').check();await privacy.getByLabel('روش تأیید مشاهده').selectOption('recovery');
  await privacy.getByLabel('کد MFA مشاهدهٔ خصوصی',{exact:true}).fill(fixture.users.privacy_operator.tokens[1]);
  const read=postResponse(privacy,'/users/'+fixture.p14.subject_id+'/privacy/read');
  await privacy.getByRole('button',{name:'مشاهدهٔ هدفمند با تأیید دومرحله‌ای',exact:true}).focus();await privacy.keyboard.press('Enter');
  const readResponse=await read;assert.equal(readResponse.status(),200);
  const personal=(await readResponse.json());
  check(personal.subject_id===fixture.p14.subject_id&&personal.results.length===1&&
    personal.results[0].body==='P14-SYNTHETIC-PRIVATE-NOTE <b>literal text</b>'&&
    await privacy.getByText('P14-OTHER-SUBJECT-NOTE',{exact:true}).count()===0,
    'Actual purpose/MFA form reads only the selected subject and excludes another user');
  await privacy.getByText('P14-SYNTHETIC-PRIVATE-NOTE <b>literal text</b>',{exact:true}).waitFor();
  check(await privacy.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),
    'Private text renders as escaped content in the 320px Persian layout');
  await privacy.screenshot({path:path.join(out,'synthetic-private-read-mobile.png'),fullPage:true});report.screenshots.push('synthetic-private-read-mobile.png');
  report.limits.push('Headless visibility tests emulate document.hidden/visibilitychange; native tab occlusion is unverified');
  await visibility(privacy,true);await visibility(privacy,false);
  check(await privacy.getByRole('region',{name:'نتیجهٔ خصوصی پشتیبانی',exact:true}).count()===0,
    'A controlled headless visibility event clears private results before return');
  const privatePath='/api/admin/users/'+fixture.p14.subject_id+'/privacy/read/';
  let releaseReply,committed;
  const replyGate=new Promise(resolve=>{releaseReply=resolve;}),serverCommitted=new Promise(resolve=>{committed=resolve;});
  const privatePattern='**'+privatePath;
  await privacy.route(privatePattern,async routed=>{
    const response=await routed.fetch();assert.equal(response.status(),200);committed();await replyGate;
    try{await routed.fulfill({response});}catch(error){
      const failed=routed.request().failure();if(!failed)throw error;
    }
  });
  const settled=Promise.race([
    privacy.waitForResponse(response=>response.url().endsWith(privatePath)&&response.request().method()==='POST').then(async response=>{await response.finished();return 'response';}),
    privacy.waitForEvent('requestfailed',{predicate:request=>request.url().endsWith(privatePath)&&request.method()==='POST'}).then(()=>'aborted'),
  ]);
  await privacy.getByLabel('کد MFA مشاهدهٔ خصوصی',{exact:true}).fill(fixture.users.privacy_operator.tokens[2]);
  await privacy.getByRole('button',{name:'مشاهدهٔ هدفمند با تأیید دومرحله‌ای',exact:true}).click();
  await serverCommitted;await visibility(privacy,true);releaseReply();await settled;await privacy.unroute(privatePattern);
  await visibility(privacy,false);
  await privacy.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  check(await privacy.getByRole('region',{name:'نتیجهٔ خصوصی پشتیبانی',exact:true}).count()===0,
    'A delayed real private-read response cannot repopulate results after hiding the page');
  await privacy.getByLabel('کد MFA مشاهدهٔ خصوصی',{exact:true}).fill(fixture.users.privacy_operator.tokens[3]);
  const reread=postResponse(privacy,'/users/'+fixture.p14.subject_id+'/privacy/read');
  await privacy.getByRole('button',{name:'مشاهدهٔ هدفمند با تأیید دومرحله‌ای',exact:true}).click();assert.equal((await reread).status(),200);
  const policySnapshot=await request(owner,'/roles/users/'+fixture.p14.operator_id+'/');
  assert.equal((await request(owner,'/roles/users/'+fixture.p14.operator_id+'/',{permissions:['cms_enter','cms_user_view']},policySnapshot.etag)).status,200);
  await privacy.getByLabel('کد MFA مشاهدهٔ خصوصی',{exact:true}).fill(fixture.users.privacy_operator.tokens[4]);
  const revokedRead=postResponse(privacy,'/auth/step-up');
  await privacy.getByRole('button',{name:'مشاهدهٔ هدفمند با تأیید دومرحله‌ای',exact:true}).click();
  check((await revokedRead).status()===403&&await privacy.getByText('P14-SYNTHETIC-PRIVATE-NOTE <b>literal text</b>',{exact:true}).count()===0,
    'Real permission revocation prevents new private reads and stale private results are cleared');
  const privateAfter=privacyState();
  check(privateAfter.digest===privateBefore.digest&&privateAfter.read_audits===3&&privateAfter.audit_content_leaks===0,
    'Purpose reads preserve both private notes and append safe access audits without note content');
  await privacyContext.close();
  const historyBefore=exportHistory();assert(historyBefore.counts.every(value=>value>0));
  const exportContext=await browser.newContext({viewport:{width:1280,height:850}}),exporter=await exportContext.newPage();
  await login(exporter,fixture.users.privacy_exporter);
  check(await exporter.getByRole('link',{name:'کارهای پردازش',exact:true}).count()===1,'Export-only account has real job navigation without private-read or upload');
  await exporter.goto(origin+'/admin-console/accounts');
  await exporter.getByLabel('نام کاربری یا شناسه',{exact:true}).fill(fixture.p14.subject_username);
  await exporter.getByRole('button',{name:'جست‌وجو',exact:true}).click();
  await exporter.locator('li').filter({has:exporter.getByText(fixture.p14.subject_username,{exact:true})}).getByRole('button',{name:'جزئیات مجاز',exact:true}).click();
  await exporter.getByRole('link',{name:'دسترسی هدفمند به اطلاعات شخصی این کاربر',exact:true}).click();
  const exportForm=exporter.getByRole('region',{name:'خروجی خصوصی اطلاعات شخصی',exact:true});
  await exportForm.waitFor();check(await exporter.getByRole('heading',{name:'درخواست مشاهدهٔ محدود',exact:true}).count()===0,'Export-only scope does not fetch or display the private-read form');
  await exportForm.getByLabel('شناسهٔ UUID درخواست صاحب داده',{exact:true}).fill('38f68974-f055-4756-9f8e-bad9d387e346');
  await exportForm.getByRole('checkbox').check();await exportForm.getByLabel('روش تأیید خروجی خصوصی').selectOption('recovery');
  await exportForm.getByLabel('کد MFA خروجی خصوصی',{exact:true}).fill('invalid-synthetic-proof');
  const invalidExportProof=postResponse(exporter,'/auth/step-up');
  await exportForm.getByRole('button',{name:'ایجاد کار خروجی خصوصی با تأیید دومرحله‌ای',exact:true}).click();
  check((await invalidExportProof).status()===403&&exportHistory().jobs===0,'Invalid export MFA creates no job and keeps the request recoverable');
  // django-otp throttles the recovery device for one second after a failed code.
  await new Promise(resolve=>setTimeout(resolve,1100));
  await exportForm.getByLabel('شناسهٔ UUID درخواست صاحب داده',{exact:true}).waitFor({state:'visible'});
  await exporter.waitForFunction(()=>!document.querySelector('input[value="38f68974-f055-4756-9f8e-bad9d387e346"]')?.disabled);
  await exportForm.getByLabel('کد MFA خروجی خصوصی',{exact:true}).fill(fixture.users.privacy_exporter.tokens[1]);
  let lostJob,firstPayload;
  const exportRoute='**/api/admin/users/'+fixture.p14.subject_id+'/privacy/export/';
  await exporter.route(exportRoute,async route=>{firstPayload=route.request().postDataJSON();const response=await route.fetch();assert.equal(response.status(),202);lostJob=(await response.json()).job;runWorker();await route.abort('failed');});
  const validExportProof=postResponse(exporter,'/auth/step-up');
  await exportForm.getByRole('button',{name:'ایجاد کار خروجی خصوصی با تأیید دومرحله‌ای',exact:true}).focus();await exporter.keyboard.press('Enter');
  assert.equal((await validExportProof).status(),200,'Fresh export MFA must pass before the lost-reply test');
  await exportForm.getByRole('button',{name:'تطبیق همان درخواست خروجی خصوصی',exact:true}).waitFor();await exporter.unroute(exportRoute);
  const reconciledResponse=postResponse(exporter,'/users/'+fixture.p14.subject_id+'/privacy/export');
  await exportForm.getByRole('button',{name:'تطبیق همان درخواست خروجی خصوصی',exact:true}).click();const reconciled=await reconciledResponse;
  check(reconciled.status()===202&&(await reconciled.json()).job.id===lostJob.id&&reconciled.request().postDataJSON().request_key===firstPayload.request_key,
    'Actual MFA export survives a lost reply after worker commit and UI retries the same key without a second proof');
  await exporter.getByRole('link',{name:'پیگیری خروجی اطلاعات شخصی',exact:true}).click();
  await exporter.getByRole('heading',{name:'خروجی اطلاعات شخصی',exact:true}).waitFor();
  const output=exporter.locator('section.stack').filter({has:exporter.getByRole('heading',{name:'خروجی اطلاعات شخصی',exact:true})}).last();
  check(await exporter.getByRole('button',{name:'اعتبارسنجی جداگانهٔ فایل',exact:true}).count()===0,'Generated personal files expose no upload validation or content import controls');
  const downloadPromise=exporter.waitForEvent('download');await output.getByRole('link',{name:'دریافت خصوصی با مجوز جاری',exact:true}).click();
  const downloaded=await downloadPromise;assert.equal(await downloaded.failure(),null);
  const privateDocument=JSON.parse(fs.readFileSync(await downloaded.path(),'utf8'));
  check(privateDocument.schema_version==='psychology-atlas-personal-export-v1'&&privateDocument.identity.id===fixture.p14.subject_id&&
    privateDocument.data.disorder_notes[0].body==='P14-SYNTHETIC-PRIVATE-NOTE <b>literal text</b>'&&
    !JSON.stringify(privateDocument).includes('P14-OTHER-SUBJECT-NOTE')&&!JSON.stringify(privateDocument).includes('Synthetic canonical question'),
    'Native worker output downloads through UI and contains only the requested subject with no canonical answer graph');
  await exporter.setViewportSize({width:320,height:820});
  check(await exporter.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Personal export job and download controls fit 320px RTL');
  const exportImage=path.join(out,'personal-export-mobile.png');await exporter.screenshot({path:exportImage,fullPage:true,mask:[exporter.locator('code'),exporter.locator('input[type="password"]')]});report.screenshots.push(exportImage);
  const historyAfter=exportHistory();check(historyAfter.digest===historyBefore.digest&&historyAfter.jobs===1&&historyAfter.receipts===1,
    'Export preserves all eight nonempty Attempt Answer Activity SRS Progress tables and creates one job and one final receipt');
  await exportContext.close();
  const studyBefore=exportHistory();
  const studyContext=await browser.newContext({viewport:{width:320,height:820}}),study=await studyContext.newPage();
  await login(study,fixture.users.study_operator);
  await study.goto(origin+'/admin-console/accounts/'+fixture.p14.subject_id+'/privacy');
  const readForm=study.locator('form').filter({has:study.getByRole('heading',{name:'درخواست مشاهدهٔ محدود',exact:true})});
  await readForm.getByLabel('شناسهٔ UUID درخواست پشتیبانی',{exact:true}).fill('79a98623-6590-480c-a11f-a4be8a165e26');
  await readForm.getByRole('checkbox').check();await readForm.getByLabel('روش تأیید مشاهده').selectOption('recovery');
  let studyToken=1;
  for(const [kind,id,action] of [['plan',fixture.p15.plan_id,'pause'],['plan',fixture.p15.plan_id,'resume'],
      ['block',fixture.p15.block_id,'reschedule'],['block',fixture.p15.block_id,'unlock'],['block',fixture.p15.block_id,'skip'],
      ['session',fixture.p15.session_id,'abandon']]){
    await readForm.getByLabel('نوع اطلاعات شخصی').selectOption({plan:'study_plans',block:'study_blocks',session:'study_sessions'}[kind]);
    await readForm.getByLabel('کد MFA مشاهدهٔ خصوصی',{exact:true}).fill(fixture.users.study_operator.tokens[studyToken++]);
    const read=postResponse(study,'/users/'+fixture.p14.subject_id+'/privacy/read');
    await readForm.getByRole('button',{name:'مشاهدهٔ هدفمند با تأیید دومرحله‌ای',exact:true}).click();
    assert.equal((await read).status(),200);
    const controls=study.getByRole('region',{name:'اقدام پشتیبانی مطالعه '+id,exact:true});await controls.waitFor();
    await controls.getByLabel('عملیات پشتیبانی مطالعه').selectOption(action);
    if(action==='reschedule')await controls.getByLabel('روز جدید بلوک').fill(new Date(Date.now()+86400000).toISOString().slice(0,10));
    await controls.getByRole('checkbox').check();await controls.getByLabel('روش تأیید اقدام مطالعه').selectOption('recovery');
    if(action==='pause'){
      await controls.getByLabel('کد MFA اقدام مطالعه',{exact:true}).fill('invalid-synthetic-proof');
      const invalid=postResponse(study,'/auth/step-up');
      await controls.getByRole('button',{name:'اعمال اقدام مطالعه با تأیید دومرحله‌ای',exact:true}).click();
      assert.equal((await invalid).status(),403);await new Promise(resolve=>setTimeout(resolve,1100));
    }
    await controls.getByLabel('کد MFA اقدام مطالعه',{exact:true}).fill(fixture.users.study_operator.tokens[studyToken++]);
    const operateRoute='**/api/admin/users/'+fixture.p14.subject_id+'/study/operate/';let originalBody,originalReceipt;
    if(action==='pause')await study.route(operateRoute,async route=>{
      originalBody=route.request().postDataJSON();const response=await route.fetch();assert.equal(response.status(),200);
      originalReceipt=(await response.json()).receipt_id;await route.abort('failed');
    });
    const valid=postResponse(study,'/auth/step-up');
    await controls.getByRole('button',{name:'اعمال اقدام مطالعه با تأیید دومرحله‌ای',exact:true}).focus();await study.keyboard.press('Enter');
    assert.equal((await valid).status(),200);
    if(action==='pause'){
      await controls.getByRole('button',{name:'تطبیق همان اقدام مطالعه',exact:true}).waitFor();await study.unroute(operateRoute);
      const reconciled=postResponse(study,'/users/'+fixture.p14.subject_id+'/study/operate');
      await controls.getByRole('button',{name:'تطبیق همان اقدام مطالعه',exact:true}).click();const response=await reconciled;
      assert.equal(response.status(),200);assert.equal((await response.json()).receipt_id,originalReceipt);
      assert.deepEqual(response.request().postDataJSON(),originalBody);
      check(true,'Study action rejects invalid MFA and safely reconciles the committed lost reply with the original key');
    }
    await controls.getByRole('status').filter({hasText:'اقدام ثبت شد'}).waitFor();
    check(true,'Real purpose read and fresh MFA execute canonical study action: '+action);
    if(action==='abandon'){
      check(await study.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Study support actions fit 320px RTL');
      await study.screenshot({path:path.join(out,'study-support-mobile.png'),fullPage:true,mask:[study.locator('input[type="password"]')]});report.screenshots.push('study-support-mobile.png');
    }
    await study.getByRole('button',{name:'پاک‌کردن نتیجه از نما',exact:true}).click();
  }
  const counts=JSON.parse(execFileSync(py,['-c','import os,sqlite3,json;c=sqlite3.connect(os.environ["SQLITE_PATH"]);print(json.dumps([c.execute("SELECT COUNT(*) FROM atlas_studyoperationreceipt").fetchone()[0],c.execute("SELECT COUNT(*) FROM atlas_adminauditevent WHERE action=\'study.operated\'").fetchone()[0],c.execute("SELECT status,completed_at FROM atlas_studysession").fetchone()]));c.close()'],{env,encoding:'utf8'}));
  check(exportHistory().digest===studyBefore.digest&&counts[0]===6&&counts[1]===6&&counts[2][0]==='abandoned'&&counts[2][1]===null,
    'Six study support receipts preserve eight nonempty history tables and never complete the learner session');
  // P15 additional diagnostics use exactly the current learner recommendation service,
  // requiring a new independently bound support read, not the prior study action proof.
  for(const scope of ['recommendations','study_availability']){
    await readForm.getByLabel('نوع اطلاعات شخصی').selectOption(scope);
    await readForm.getByLabel('کد MFA مشاهدهٔ خصوصی',{exact:true}).fill(fixture.users.study_operator.tokens[studyToken++]);
    const response=postResponse(study,'/users/'+fixture.p14.subject_id+'/privacy/read');
    await readForm.getByRole('button',{name:'مشاهدهٔ هدفمند با تأیید دومرحله‌ای',exact:true}).click();
    const body=await (await response).json();
    check(body.scope===scope&&body.subject_id===fixture.p14.subject_id&&
      (scope==='recommendations'?body.results.length===1&&body.results[0].version==='v2':
        body.count>=body.results.length&&body.results.every(row=>row.plan_id===fixture.p15.plan_id&&
          typeof row.available_minutes==='number'&&typeof row.weekday==='number')),
      'P15 owner-scoped support diagnostics return the actual '+scope+' through fresh MFA');
    await study.getByRole('region',{name:'نتیجهٔ خصوصی پشتیبانی',exact:true}).waitFor();
    check(await study.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
      'P15 '+scope+' diagnostics remain within the 320px Persian RTL viewport');
    await study.getByRole('button',{name:'پاک‌کردن نتیجه از نما',exact:true}).click();
  }
  await studyContext.close();
  // P16 preflight fingerprint is read-only and deliberately not a publishing route.
  const draft=await request(owner,'/learning/quizzes/',{slug:'p16-private-browser-quiz',title:'Synthetic private publication preflight',description:'',disorder_id:null});
  assert.equal(draft.status,201);
  const quizId=draft.data.quiz_id;
  const inventory=await request(owner,'/publication/preflight/?domain=learning&page=1&page_size=30');
  assert.equal(inventory.status,200);
  const item=inventory.data.results.find(row=>row.kind==='quiz'&&row.resource_id===quizId);
  check(!!item&&item.content_digest?.length===64&&item.content_issues.includes('TARGET_REQUIRED')&&
    !item.eligible&&!inventory.data.publication_available,
    'P16 private Learning draft fingerprint detects a missing dependency without granting publication');
  await owner.goto(origin+'/admin-console/publication-preflight');
  await owner.getByLabel('حوزهٔ مجاز').selectOption('learning');
  await owner.getByText(item.content_digest,{exact:true}).waitFor();
  check(await owner.getByText('اثر انگشت محتوای همین لحظه',{exact:false}).count()===1&&
    await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
    'P16 Learning preflight displays the version digest without overflow on 320px RTL');
  const original=await request(owner,'/learning/quizzes/'+quizId+'/');
  const edited=await request(owner,'/learning/quizzes/'+quizId+'/metadata/',{title:'Edited synthetic private preflight',description:'',disorder_id:null},original.etag);
  assert.equal(edited.status,200);
  const updated=await request(owner,'/publication/preflight/?domain=learning&page=1&page_size=30');
  const changed=updated.data.results.find(row=>row.kind==='quiz'&&row.resource_id===quizId);
  check(changed?.content_digest?.length===64&&changed.content_digest!==item.content_digest&&
    changed.eligible===false,
    'P16 exact preflight fingerprints change on draft edits and never expose an Apply authorization');
  await owner.goto(origin+'/admin-console/publication-preflight');
  await owner.getByLabel('حوزهٔ مجاز').selectOption('learning');
  await owner.getByText(changed.content_digest,{exact:true}).waitFor();
  await owner.getByLabel('انتخاب برای بستهٔ بازبینی: quiz #'+quizId).check();
  const learningSelection=postResponse(owner,'/publication/selections');
  await owner.getByRole('button',{name:'ثبت بستهٔ بازبینی بدون انتشار'}).click();
  const learningSelectionResult=await (await learningSelection).json();
  check(learningSelectionResult.item_count===1&&learningSelectionResult.selection_digest?.length===64&&
    learningSelectionResult.status==='review_selection_only'&&!learningSelectionResult.publication_available,
    'P16 Learning selection records only a durable review batch, with no publish authority');
  check(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)&&
    await owner.getByText('بستهٔ بازبینی ثبت شد',{exact:false}).count()===1,
    'P16 sealed Learning review selection receipt is visible at 320px RTL');
  const recheckPath=response=>response.url().replace(/\/$/,'').endsWith('/publication/selections/'+learningSelectionResult.id+'/verify')&&response.request().method()==='GET'&&!(response.status()>=300&&response.status()<400);
  const initialRecheck=owner.waitForResponse(recheckPath);
  await owner.getByRole('button',{name:'بررسی وضعیت فعلی بسته'}).click();
  const initialResult=await (await initialRecheck).json();
  check(initialResult.all_snapshots_current&&initialResult.policy_matches&&
    initialResult.items[0].snapshot_state==='matching'&&!initialResult.publication_available&&
    initialResult.review_blockers.includes('SOURCE_SCIENCE_RIGHTS_UNVERIFIED'),
    'P16 Learning recheck matches immutable selection digest but never reports scientific clearance');
  check(await owner.getByRole('region',{name:'اعتبارسنجی مجدد بسته'}).count()===1&&
    await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
    'P16 Persian Learning verification fits a 320px RTL viewport');
  const beforeSecondEdit=await request(owner,'/learning/quizzes/'+quizId+'/');
  const secondEdit=await request(owner,'/learning/quizzes/'+quizId+'/metadata/',
    {title:'New private study title after selection',description:'',disorder_id:null},beforeSecondEdit.etag);
  assert.equal(secondEdit.status,200);
  const changedRecheck=owner.waitForResponse(recheckPath);
  await owner.getByRole('button',{name:'بررسی وضعیت فعلی بسته'}).click();
  const staleReport=await (await changedRecheck).json();
  check(!staleReport.all_snapshots_current&&staleReport.items[0].snapshot_state==='stale'&&
    !JSON.stringify(staleReport).includes('New private study title'),
    'P16 changed Learning draft safely invalidates old selection without exposing private text');
  let releaseOldVerification,verificationArrived;
  const delayedVerification=new Promise(resolve=>{verificationArrived=resolve;});
  const verificationGate=new Promise(resolve=>{releaseOldVerification=resolve;});
  const oldVerificationRoute='**/api/admin/publication/selections/'+learningSelectionResult.id+'/verify/';
  await owner.route(oldVerificationRoute,async route=>{
    const response=await route.fetch();verificationArrived();await verificationGate;await route.fulfill({response});
  });
  const oldVerificationResponse=owner.waitForResponse(recheckPath);
  await owner.getByRole('button',{name:'بررسی وضعیت فعلی بسته'}).click();await delayedVerification;
  for(const domain of ['brain','assessment']){
    const answer=await request(owner,'/publication/preflight/?domain='+domain+'&page=1&page_size=30');
    assert.equal(answer.status,200);
    const candidate=answer.data.results.find(row=>row.resource_id===fixture.p16[domain]);
    check(!!candidate&&candidate.proposal_digest?.length===64&&!candidate.eligible&&
      candidate.blockers.includes('SOURCE_DEPENDENCIES_NOT_REVALIDATED')&&
      !answer.data.publication_available&&!JSON.stringify(answer.data).includes('P16 PRIVATE SYNTHETIC SECRET'),
      'P16 '+domain+' immutable proposal inventory excludes private draft text and denies publication');
    if(domain==='assessment')await owner.goto(origin+'/admin-console/publication-preflight');
    await owner.getByLabel('حوزهٔ مجاز').selectOption(domain);
    await owner.getByText(candidate.proposal_digest,{exact:true}).waitFor();
    check(await owner.getByText('اثر انگشت نسخهٔ ثبت‌شدهٔ پیشنهاد',{exact:false}).count()===1&&
      await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
      'P16 '+domain+' proposal digest renders at 320px RTL without overflow or Apply');
    await owner.getByLabel('انتخاب برای بستهٔ بازبینی: '+candidate.kind+' #'+candidate.resource_id).check();
    const selectionResponse=postResponse(owner,'/publication/selections');
    await owner.getByRole('button',{name:'ثبت بستهٔ بازبینی بدون انتشار'}).click();
    const selectionData=await (await selectionResponse).json();
    check(selectionData.domain===domain&&selectionData.item_count===1&&
      selectionData.selection_digest?.length===64&&!selectionData.approved&&!selectionData.publication_available,
      'P16 '+domain+' server-owned selection retains a private review batch without public effects');
    if(domain==='brain'){
      releaseOldVerification();await oldVerificationResponse;await owner.unroute(oldVerificationRoute);
      await owner.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      check(await owner.getByRole('region',{name:'اعتبارسنجی مجدد بسته'}).count()===0,
        'P16 delayed verification from another domain never appears under the new selection');
    }
    const verifyResponse=owner.waitForResponse(response=>response.url().replace(/\/$/,'')
      .endsWith('/publication/selections/'+selectionData.id+'/verify')&&response.request().method()==='GET'&&
      !(response.status()>=300&&response.status()<400));
    await owner.getByRole('button',{name:'بررسی وضعیت فعلی بسته'}).click();
    const verifyBody=await (await verifyResponse).json();
    check(verifyBody.all_snapshots_current&&verifyBody.policy_matches&&
      verifyBody.items[0].snapshot_state==='matching'&&
      verifyBody.items[0].dependency_state==='matching'&&
      verifyBody.review_blockers.includes('LIVE_SOURCE_RIGHTS_REVALIDATION_REQUIRED')&&
      !verifyBody.publication_available&&!JSON.stringify(verifyBody).includes('SYNTHETIC SECRET'),
      'P16 '+domain+' recheck preserves explicit live source/rights blockers without exposing draft');
    const review=verifyBody.items[0].editorial_review;
    check(review?.status==='blocked'&&review.blockers.includes('REVIEW_REQUIRED')&&
      review.blockers.includes('APPROVAL_REQUIRED')&&!verifyBody.approved&&
      !JSON.stringify(verifyBody).includes('P16 PRIVATE SYNTHETIC SECRET'),
      'P16 '+domain+' reports genuine CMS editorial review blockers, not synthetic approval');
    check(await owner.locator('[aria-label="وضعیت بازبینی علمی موجود"]').count()===1&&
      await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
      'P16 '+domain+' editorial review status fits 320px RTL with no publication controls');
    const rightsEvidence=verifyBody.items[0].source_rights_evidence;
    check(rightsEvidence?.scope==='source_metadata_public_display_only'&&
      rightsEvidence.source_count>=1&&rightsEvidence.permitted_count===0&&
      rightsEvidence.status==='not_established'&&!rightsEvidence.publication_rights_cleared&&
      !verifyBody.publication_available,
      'P16 '+domain+' unapproved source-metadata rights cannot become publication clearance');
    check(await owner.locator('[aria-label="شواهد حقوق فراداده منابع"]').count()===1&&
      await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
      'P16 '+domain+' source-metadata rights report is visible in 320px RTL');
    const sourcePreview=await request(owner,'/sources/preview/',{operation:'update',source_id:fixture.p16_source_id,
      changes:{citation:'P16 synthetic private citation edited for '+domain}});
    assert.equal(sourcePreview.status,201);assert.equal(sourcePreview.data.preview.can_apply,true);
    const sourceApplied=await request(owner,'/sources/plans/'+sourcePreview.data.id+'/apply/',{},sourcePreview.etag);
    assert.equal(sourceApplied.status,200);assert.equal(sourceApplied.data.status,'applied');
    const sourceRecheck=owner.waitForResponse(response=>response.url().replace(/\/$/,'')
      .endsWith('/publication/selections/'+selectionData.id+'/verify')&&response.request().method()==='GET'&&
      !(response.status()>=300&&response.status()<400));
    await owner.getByRole('button',{name:'بررسی وضعیت فعلی بسته'}).click();
    const sourceChanged=await (await sourceRecheck).json();
    check(!sourceChanged.all_snapshots_current&&sourceChanged.items[0].snapshot_state==='matching'&&
      sourceChanged.items[0].dependency_state==='stale'&&!sourceChanged.publication_available&&
      !JSON.stringify(sourceChanged).includes('private citation'),
      'P16 '+domain+' canonical source edit invalidates live dependency binding while proposal digest stays unchanged');
  }
  await owner.screenshot({path:path.join(out,'p16-editorial-proposals-mobile.png'),fullPage:true,
    mask:[owner.locator('input[type="password"]')]});
  report.screenshots.push('p16-editorial-proposals-mobile.png');

  // P17 private search must never inspect raw research payload or audit actors.
  await owner.goto(origin+'/admin-console/search');
  const searchInput=owner.getByLabel('شناسه یا کلید لاتین (برای Audit شمارهٔ دقیق)');
  await owner.getByLabel('حوزه').selectOption('research');
  await searchInput.fill('p17-browser');
  const directResearch=await request(owner,'/search/?q=p17-browser&domain=research');
  check(directResearch.status===200&&directResearch.data.count===2,
    'P17 browser direct API serves authorized research results before UI search');
  check(await searchInput.inputValue()==='p17-browser'&&
    await owner.getByLabel('حوزه').inputValue()==='research'&&
    await owner.getByRole('button',{name:'جست‌وجو',exact:true}).isEnabled(),
    'P17 controlled search form has a valid term and selected domain');
  const researchSearch=owner.waitForResponse(response=>response.url().includes('/api/admin/search')&&
    response.url().includes('domain=research')&&response.request().method()==='GET'&&
    !(response.status()>=300&&response.status()<400));
  await owner.getByRole('button',{name:'جست‌وجو',exact:true}).click();
  const researchResponse=await researchSearch;
  assert.equal(researchResponse.status(),200,(await researchResponse.text()).slice(0,400));
  const researchResult=await researchResponse.json();
  check(researchResult.count===2&&researchResult.results.some(r=>r.kind==='research_dataset'&&
    r.resource_id===fixture.p17.dataset_id)&&
    researchResult.results.some(r=>r.kind==='research_record'&&r.resource_id===fixture.p17.record_id)&&
    !JSON.stringify(researchResult).includes('P17 SECRET'),
    'P17 private search discovers only authorized research staging keys without raw content');
  check(await owner.getByText('مجموعه‌دادهٔ پژوهشی داخلی',{exact:true}).count()===1&&
    await owner.getByText('رکورد پژوهشی داخلی',{exact:true}).count()===1,
    'P17 Persian search renders typed research results only');
  await owner.getByLabel('حوزه').selectOption('audit');
  await searchInput.fill(String(fixture.p17.audit_id));
  const auditSearch=owner.waitForResponse(response=>response.url().includes('/api/admin/search')&&
    response.url().includes('domain=audit')&&response.request().method()==='GET'&&
    !(response.status()>=300&&response.status()<400));
  await owner.getByRole('button',{name:'جست‌وجو',exact:true}).click();
  const auditResponse=await auditSearch;
  assert.equal(auditResponse.status(),200,(await auditResponse.text()).slice(0,400));
  const auditResult=await auditResponse.json();
  check(auditResult.count===1&&auditResult.results[0].kind==='audit_event'&&
    auditResult.results[0].resource_id===fixture.p17.audit_id&&
    !JSON.stringify(auditResult).includes('actor_ref')&&!JSON.stringify(auditResult).includes('request_id'),
    'P17 audit discovery is exact-ID only with no actor, event or request metadata');
  check(await owner.getByText('رویداد Audit',{exact:true}).count()===1&&
    await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
    'P17 audit discovery fits the 320px Persian RTL viewport');

  let releaseOldSearch,oldSearchArrived;
  const oldSearchGate=new Promise(resolve=>{releaseOldSearch=resolve;});
  const oldSearchArrival=new Promise(resolve=>{oldSearchArrived=resolve;});
  const oldSearchRoute='**/api/admin/search/?*';
  await owner.route(oldSearchRoute,async route=>{
    if(!route.request().url().includes('q=p17-browser')||
       !route.request().url().includes('domain=research'))return route.continue();
    const response=await route.fetch();oldSearchArrived();await oldSearchGate;
    await route.fulfill({response});
  });
  await owner.getByLabel('حوزه').selectOption('research');
  await searchInput.fill('p17-browser');
  const oldSearchResponse=owner.waitForResponse(response=>response.url().includes('/api/admin/search/')&&
    response.url().includes('q=p17-browser')&&response.status()===200);
  await owner.getByRole('button',{name:'جست‌وجو',exact:true}).click();
  await oldSearchArrival;
  await owner.getByLabel('حوزه').selectOption('audit');
  releaseOldSearch();await oldSearchResponse;await owner.unroute(oldSearchRoute);
  await owner.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  check(await owner.getByRole('heading',{name:/نتایج:/}).count()===0,
    'P17 delayed research search response never repopulates results under another domain');

  const health=await request(owner,'/operations/health/');
  check(health.status===200&&
    health.data.publication_receipts?.scope==='case_revision_structural_receipts_only'&&
    Number.isInteger(health.data.publication_receipts.total_observed_mismatches)&&
    health.data.publication_receipts.full_publication_integrity_proven===false&&
    health.data.publication_receipts.repair_available===false&&
    health.data.backup.state==='unavailable',
    'P18 owner-only case receipt drift is reported as structural metadata, never publication or backup clearance');
  check((await request(scoped,'/operations/health/')).status===403,
    'P18 ordinary content curator cannot read owner receipt health');
  await owner.goto(origin+'/admin-console/operations');
  await owner.getByRole('heading',{name:'رسیدهای انتشار CaseRevision، فقط بررسی ساختاری'}).waitFor();
  check(await owner.locator('[aria-label="بازبینی ساختاری رسیدهای انتشار"]').count()===1&&
    await owner.getByText('مغایرت‌های مشاهده‌شده:',{exact:false}).count()===1&&
    await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
    'P18 receipt drift and explicit non-clearance are visible in Persian 320px RTL');

  await owner.goto(origin+'/admin-console/help');
  await owner.getByRole('heading',{name:'راهنمای کاربردی مدیریت Psychology Atlas'}).waitFor();
  check(await owner.getByRole('link',{name:'حقوق و استفاده'}).getAttribute('href')==='/admin-console/rights'&&
    await owner.getByRole('link',{name:'فهرست و بازبینی محدود P16'}).count()===1&&
    await owner.getByRole('link',{name:'جست‌وجوی داخلی'}).count()===1,
    'P19 owner guide connects live rights, P16 review, P17 search and operations without nonexistent caps');
  check(await owner.getByText('در P16، تأیید فرادادهٔ یک منبع',{exact:false}).count()===1&&
    await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),
    'P19 Persian guide explains non-clearance and fits 320px RTL');
  await openAccount(owner,fixture.users.owner.username);
  await owner.getByRole('button',{name:'بررسی ساخت کدهای بازیابی خودم',exact:true}).click();await confirmAccount(owner,fixture.users.owner.tokens[7]);
  await owner.waitForURL(url=>url.pathname.replace(/\/$/,'')==='/account/two_factor/backup/tokens');
  const recoveryGenerated=owner.waitForResponse(response=>response.url().includes('/account/two_factor/backup/tokens')&&response.request().method()==='POST');
  await owner.locator('form[method="post"] button[type="submit"]').click();assert.equal((await recoveryGenerated).status(),200);
  const freshCodes=await owner.locator('li code').allTextContents();assert.equal(freshCodes.length,10);
  await owner.reload();check(await owner.locator('li code').count()===0,'Maintained MFA flow generates ten replacement recovery codes once and never redisplays them');
  await openAccount(owner,fixture.users.owner.username);await owner.getByRole('button',{name:'بررسی لغو MFA خودم',exact:true}).click();
  const mfaRevoked=postResponse(owner,'/auth/mfa/revoke');await confirmAccount(owner,freshCodes[0]);assert.equal((await mfaRevoked).status(),200);
  await owner.getByLabel('نام کاربری',{exact:true}).waitFor();check(true,'New one-time recovery proof revokes own MFA and logs out the actual session');
  check(report.errors.length===0,'No uncaught browser errors');report.status='PASS';await scopedContext.close();await ownerContext.close();
}catch(error){report.status='FAIL';report.failure=String(error.stack||error).slice(0,1900);process.exitCode=1;
  const page=browser?.contexts()[0]?.pages()[0];if(page){report.failure_alerts=await page.getByRole('alert').allTextContents().catch(()=>[]);await page.screenshot({path:path.join(out,'failure.png'),fullPage:true,mask:[page.locator('code'),page.locator('input[type="password"]')]}).catch(()=>{});}
}finally{report.completed_at=new Date().toISOString();fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));if(browser)await browser.close().catch(()=>{});for(const proc of processes.reverse())if(proc.exitCode===null)proc.kill();if(path.basename(tmp).startsWith('atlas-p14-browser-')&&path.dirname(tmp)===os.tmpdir())fs.rmSync(tmp,{recursive:true,force:true});console.log(JSON.stringify({status:report.status,checks:report.checks.length,errors:report.errors.length,failure:report.failure||null}));}})().catch(error=>{console.error(error);process.exitCode=1;});
