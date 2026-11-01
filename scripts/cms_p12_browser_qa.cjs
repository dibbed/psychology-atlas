// Isolated, synthetic-only P12 Case Builder browser integration. Never uses the main DB.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
let chromium;try{({chromium}=require('playwright'));}catch(e){if(e.code!=='MODULE_NOT_FOUND')throw e;({chromium}=require(path.join(os.tmpdir(),'atlas-p07-browser-tools/node_modules/playwright')));}
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-p12-browser-'));
const out=process.env.CMS_QA_OUTPUT||path.join(root,'qa/p12-browser');
fs.mkdirSync(out,{recursive:true});
const py=process.env.CMS_QA_PYTHON||(process.platform==='win32'?path.join(root,'backend/.venv/Scripts/python.exe'):'python');
const origin=process.env.CMS_QA_ORIGIN||'http://127.0.0.1:3000';
const api=process.env.CMS_QA_API_ORIGIN||'http://127.0.0.1:8000';
const env={...process.env,CMS_QA_PHASE:'p12',SQLITE_PATH:path.join(tmp,'cms-journey.sqlite3'),
  NEXT_PUBLIC_API_URL:api+'/api',CSRF_TRUSTED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P12',status:'RUNNING',checks:[],screenshots:[],errors:[],
  limits:['Synthetic, fresh isolated SQLite only','No actual reviewed publication','No existing user data or canonical database touched']};
const processes=[];let browser;
function check(ok,description){assert(ok,description);report.checks.push(description);}
function start(exe,args,cwd,name){
  const handle=fs.openSync(path.join(tmp,name+'.log'),'a');
  const proc=spawn(exe,args,{cwd,env,windowsHide:true,stdio:['ignore',handle,handle]});
  fs.closeSync(handle);processes.push(proc);return proc;
}
async function ready(url,proc){
  for(let i=0;i<100;i++){
    assert(proc.exitCode===null,'Owned test server stopped');
    try{const r=await fetch(url,{signal:AbortSignal.timeout(1500)});if(r.status<500)return;}catch{}
    await new Promise(resolve=>setTimeout(resolve,300));
  }
  throw Error('P12 test server not ready');
}
async function login(page,user){
  await page.goto(origin+'/admin-console');
  await page.getByLabel('نام کاربری',{exact:true}).fill(user.username);
  await page.getByLabel('گذرواژه',{exact:true}).fill(user.password);
  await page.getByRole('button',{name:'ادامه با گذرواژه'}).click();
  await page.getByLabel('روش تأیید').selectOption('recovery');
  await page.getByLabel('کد تأیید',{exact:true}).fill(user.tokens[0]);
  await page.getByRole('button',{name:'تأیید و ورود'}).click();
  await page.getByRole('button',{name:'خروج',exact:true}).waitFor();
}
async function query(page,route){
  return page.evaluate(async r=>{
    const response=await fetch('/api/admin'+r,{cache:'no-store',credentials:'same-origin'});
    return {status:response.status,data:await response.json(),etag:response.headers.get('ETag')};
  },route);
}
(async()=>{try{
  const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{
    cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
  check(!!fixture.p12&&!!fixture.users.owner&&!!fixture.users.case_reader,
    'Synthetic published case and scoped MFA-only reader in disposable SQLite');
  const django=start(py,['manage.py','runserver','127.0.0.1:'+new URL(api).port,'--noreload'],path.join(root,'backend'),'django');
  await ready(api+'/api/admin/auth/csrf/',django);
  const next=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start',
    '-p',new URL(origin).port,'-H','127.0.0.1'],path.join(root,'frontend'),'next');
  await ready(origin+'/admin-console',next);
  browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
  const ownerContext=await browser.newContext({viewport:{width:1280,height:850}});
  const owner=await ownerContext.newPage();
  owner.on('pageerror',e=>report.errors.push(String(e)));
  await login(owner,fixture.users.owner);
  check(true,'Owner session uses real MFA and CSRF against isolated backend');
  await owner.goto(origin+'/admin-console/content/cases');
  await owner.getByRole('heading',{name:'بازرسی گراف کیس آموزشی'}).waitFor();
  await owner.getByText('P12 synthetic published fixture').first().waitFor();
  check(true,'Existing case appears in real private catalog');
  const prefix='/cases/'+fixture.p12.case+'/revisions/';
  const published=await query(owner,prefix+fixture.p12.revision+'/graph/');
  check(published.status===200&&published.data.valid===true,'Published fixture graph is structurally valid');
  const beforeAttempt=await query(owner,prefix+fixture.p12.revision+'/validate/');
  check(beforeAttempt.status===200&&beforeAttempt.data.publication_available===false,
    'Graph validity never permits unreviewed publication');
  await owner.getByRole('button',{name:'نسخهٔ منتشرشده',exact:true}).first().click();
  await owner.getByRole('heading',{name:/Synthetic v1/}).waitFor();
  await owner.getByRole('button',{name:'ساخت پیش‌نویس مستقل از این نسخه'}).click();
  await owner.getByRole('heading',{name:'ویرایش ساختار CaseRevision (فقط Draft)'}).waitFor();
  const revisions=await query(owner,'/cases/'+fixture.p12.case+'/revisions/');
  const draft=revisions.data.results.find(item=>item.status==='draft');
  check(revisions.status===200&&!!draft&&revisions.data.current_revision_id===fixture.p12.revision,
    'Cloning keeps published revision selected and creates separate draft');
  const editor=owner.getByRole('heading',{name:'ویرایش ساختار CaseRevision (فقط Draft)'}).locator('..');
  const firstStep=editor.locator('form fieldset').nth(1).locator('details').first();
  await firstStep.locator('summary').click();
  await firstStep.getByLabel('عنوان',{exact:true}).fill('P12 updated fictional start');
  check(await owner.getByText('تغییر ذخیره‌نشده دارید.').count()>0,
    'Unsaved graph edit is visible before navigation');
  owner.once('dialog',async dialog=>dialog.dismiss());
  await owner.getByRole('button',{name:'بازرسی همین نسخه'}).last().click();
  check(await firstStep.getByLabel('عنوان',{exact:true}).inputValue()==='P12 updated fictional start',
    'Canceling navigation preserves unsaved graph edits');
  await editor.getByRole('button',{name:'ذخیرهٔ ساختار Draft'}).click();
  await owner.waitForFunction(async url=>{
    const response=await fetch('/api/admin'+url,{cache:'no-store',credentials:'same-origin'});
    if(!response.ok)return false;
    const data=await response.json();
    return data.valid&&data.steps.some(s=>s.title==='P12 updated fictional start');
  },prefix+draft.revision_id+'/graph/',{timeout:15000});
  const updated=await query(owner,prefix+draft.revision_id+'/graph/');
  check(updated.status===200&&updated.data.valid&&updated.data.steps.some(s=>s.title==='P12 updated fictional start'),
    'Real form writes valid graph and reloads a new ETag '+JSON.stringify({status:updated.status,valid:updated.data.valid,titles:updated.data.steps.map(s=>s.title)}));
  const unchanged=await query(owner,prefix+fixture.p12.revision+'/graph/');
  check(unchanged.data.steps[0].title==='Fictional start'&&
    unchanged.data.current_revision_id===fixture.p12.revision,
    'Canonical published revision is immutable across graph draft edit');
  await owner.getByRole('button',{name:'بررسی ساختار و موانع انتشار'}).click();
  await owner.getByText('وضعیت انتشار: غیرفعال، تا تأییدهای لازم.').waitFor();
  check(await owner.getByText(/تأیید علمی به همین نسخه/).count()>0,
    'Validation UI surfaces revision-scoped scientific review blocker');
  const validated=await query(owner,prefix+draft.revision_id+'/validate/');
  const displayedDigest=await owner.locator('section[aria-labelledby="case-validation-title"] code[dir="ltr"]').first().textContent();
  check(validated.status===200&&displayedDigest===validated.data.revision_digest,
    'Case validation UI displays exact server-computed content fingerprint');
  await owner.getByRole('button',{name:'اجرای شبیه‌سازی بدون ثبت سابقه'}).focus();
  await owner.keyboard.press('Enter');
  await owner.getByText('شبیه‌سازی تکمیل شد.').waitFor();
  check(true,'Draft route simulation completes with no learner-write API');
  const metadataRequests=[];
  owner.on('request',r=>{
    if(r.method()==='POST'&&r.url().includes('/metadata/')){
      let body={};try{body=JSON.parse(r.postData()||'{}');}catch{}
      metadataRequests.push({expected:body.educational_objective==='Updated synthetic learning objective',
        fieldNames:Object.keys(body)});
    }
  });
  owner.on('response',r=>{
    if(r.request().method()==='POST'&&r.url().includes('/metadata/'))
      metadataRequests.push({responseStatus:r.status()});
  });
  const metadata=owner.getByRole('heading',{name:'ویرایش اطلاعات پیش‌نویس'}).locator('..');
  await metadata.getByLabel('هدف آموزشی').fill('Updated synthetic learning objective');
  await metadata.getByRole('button',{name:'ذخیرهٔ اطلاعات پیش‌نویس'}).click();
  await owner.waitForFunction(async url=>{
    const response=await fetch('/api/admin'+url,{cache:'no-store',credentials:'same-origin'});
    if(!response.ok)return false;
    return (await response.json()).educational_objective==='Updated synthetic learning objective';
  },prefix+draft.revision_id+'/graph/',{timeout:15000});
  await owner.waitForFunction(()=>{
    const button=document.querySelector('section[aria-labelledby="draft-metadata"] button[type="submit"]');
    return button&&!button.disabled;
  },null,{timeout:15000});
  const saved=await query(owner,prefix+draft.revision_id+'/graph/');
  check(saved.status===200&&saved.data.educational_objective==='Updated synthetic learning objective',
    'Draft metadata editor persists independently of graph edits '+JSON.stringify({status:saved.status,objective:saved.data.educational_objective,metadataRequests}));
  await metadata.getByLabel('هدف آموزشی').fill('Uncommitted fictional metadata change');
  let metadataDialogSeen=false;
  owner.once('dialog',async dialog=>{metadataDialogSeen=true;await dialog.dismiss();});
  await owner.getByRole('button',{name:'بازرسی همین نسخه'}).last().click();
  const valueAfterCancel=await metadata.getByLabel('هدف آموزشی').inputValue();
  check(metadataDialogSeen&&valueAfterCancel==='Uncommitted fictional metadata change',
    'Canceling internal navigation preserves unsaved metadata edits '+JSON.stringify({metadataDialogSeen,valueAfterCancel}));
  await metadata.getByLabel('هدف آموزشی').fill('Updated synthetic learning objective');
  await owner.screenshot({path:path.join(out,'case-editor-desktop.png'),fullPage:true});
  report.screenshots.push('case-editor-desktop.png');
  await owner.setViewportSize({width:320,height:790});
  check(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),
    'Live Case Builder forms fit 320px width with no horizontal overflow');
  await owner.screenshot({path:path.join(out,'case-editor-mobile.png'),fullPage:true});
  report.screenshots.push('case-editor-mobile.png');
  await owner.reload();
  await owner.getByRole('heading',{name:'بازرسی گراف کیس آموزشی'}).waitFor();
  check(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),
    'Case list and editor entry fit 320px viewport without horizontal overflow');
  await owner.screenshot({path:path.join(out,'case-catalog-mobile.png'),fullPage:true});
  report.screenshots.push('case-catalog-mobile.png');
  await owner.goto(origin+'/admin-console/publication-preflight');
  await owner.getByRole('heading',{name:'صف انتشار، فقط بررسی مقدماتی'}).waitFor();
  const preflight=await query(owner,'/publication/preflight/?domain=cases');
  const draftCandidate=preflight.data.results.find(x=>x.resource_id===draft.revision_id);
  check(preflight.status===200&&!!draftCandidate&&
    await owner.getByText(draftCandidate.revision_digest,{exact:true}).count()===1&&
    !draftCandidate.eligible&&await owner.getByText('پیش‌نیازهای انتشار ناقص است').count()>0,
    'Publication preflight renders the same server-bound fingerprint and stays closed');
  const readerContext=await browser.newContext({viewport:{width:390,height:790}});
  const reader=await readerContext.newPage();
  reader.on('pageerror',e=>report.errors.push(String(e)));
  await login(reader,fixture.users.case_reader);
  await reader.goto(origin+'/admin-console/content/cases');
  await reader.getByRole('heading',{name:'بازرسی گراف کیس آموزشی'}).waitFor();
  check(await reader.getByRole('button',{name:'ساخت کیس و Draft اولیه'}).count()===0,
    'Read-only role has no case create button');
  const readerData=await query(reader,prefix+draft.revision_id+'/graph/');
  check(readerData.status===200&&readerData.data.revision_status==='draft',
    'Scoped preview user can inspect but cannot edit draft');
  await reader.getByRole('button',{name:'باز کردن Draft'}).first().click();
  check(await reader.getByRole('heading',{name:'ویرایش ساختار CaseRevision (فقط Draft)'}).count()===0,
    'Scoped read-only case role cannot see mutation form');
  // P16 exercises the real review form on disposable fictional content only.
  await owner.setViewportSize({width:1280,height:850});
  await owner.goto(origin+'/admin-console/content/cases');
  await owner.getByRole('button',{name:'باز کردن Draft'}).first().click();
  const panel=owner.getByRole('heading',{name:'مرکز انتشار نسخهٔ کیس (P16)'}).locator('..');
  await panel.getByText('SOURCE_REVIEW_REQUIRED').first().waitFor();
  check(true,'P16 UI presents the missing revision-scoped source review');
  await panel.getByLabel('شناسهٔ SourceReference تأییدشده').fill(String(fixture.p12.source));
  await panel.getByLabel('محل دقیق مدرک برای همین ادعا').fill('Synthetic section 1, isolated QA');
  await panel.getByRole('checkbox').first().check();
  await panel.getByRole('button',{name:'ثبت تصمیم نسخه‌مند'}).click();
  await panel.getByText('تأیید‌شده برای این نسخه').first().waitFor();
  check(true,'P16 source review form records an exact-version decision');
  await panel.getByLabel('نوع بررسی').selectOption('scientific');
  await panel.getByRole('checkbox').first().check();
  await panel.getByRole('button',{name:'ثبت تصمیم نسخه‌مند'}).click();
  await panel.getByText('تأیید‌شده برای این نسخه').nth(1).waitFor();
  check(true,'P16 scientific form records a separate privileged decision');
  await panel.getByLabel('نوع بررسی').selectOption('rights');
  await panel.getByLabel('دارندهٔ حق',{exact:true}).fill('Synthetic original fixture owner');
  await panel.getByLabel('مبنای شناسایی دارندهٔ حق').fill('Explicit fictional test declaration');
  await panel.getByLabel('شرح دقیق اجازهٔ نمایش عمومی متن دیجیتال').fill('Isolated fictional rights claim for disposable QA only');
  await panel.getByLabel('قلمرو مجوز').fill('Synthetic QA territory');
  await panel.getByLabel('تاریخ بازبینی بعدی').fill('2027-01-01');
  await panel.getByLabel('انقضای مجوز، در صورت وجود').fill('2027-02-01');
  await panel.getByRole('checkbox').first().check();
  await panel.getByRole('button',{name:'ثبت تصمیم نسخه‌مند'}).click();
  await panel.getByText('تأیید‌شده برای این نسخه').nth(2).waitFor();
  check(true,'P16 rights form requires explicit scope, holder and dated review');
  await panel.getByRole('button',{name:'ساخت مانیفست ثابت سروری'}).click();
  await panel.getByText('وضعیت مانیفست:').waitFor();
  const p16Plan=await panel.getByPlaceholder('UUID مانیفست').inputValue();
  check(/^[0-9a-f-]{36}$/.test(p16Plan),'P16 server freezes a version-bound manifest');
  await panel.getByRole('checkbox').last().check();
  await panel.getByRole('button',{name:'تأیید مانیفست'}).click();
  await panel.getByText('approved',{exact:true}).first().waitFor();
  check(true,'P16 manifest review is separate from publication activation');
  const planBeforeApply=await query(owner,'/publication/cases/plans/'+p16Plan+'/');
  const graphBeforeApply=await query(owner,prefix+draft.revision_id+'/graph/');
  check(planBeforeApply.status===200&&planBeforeApply.data.status==='approved'&&
    planBeforeApply.data.receipts.length===0&&
    graphBeforeApply.data.revision_status==='draft',
    'P16 browser confirms Freeze and approval cannot silently activate a draft');
  await owner.screenshot({path:path.join(out,'case-publication-before-apply.png'),fullPage:true});
  report.screenshots.push('case-publication-before-apply.png');
  check(report.errors.length===0,'Browser emitted no uncaught runtime errors');
  report.status='PASS';
  await readerContext.close();await ownerContext.close();
}catch(e){report.status='FAIL';report.failure=String(e?.stack||e?.message||e).slice(0,1900);process.exitCode=1;}
finally{
  report.completed_at=new Date().toISOString();
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
  if(browser)await browser.close().catch(()=>{});
  for(const p of processes.reverse())if(p.exitCode===null)p.kill();
  if(path.basename(tmp).startsWith('atlas-p12-browser-')&&path.dirname(tmp)===os.tmpdir())
    fs.rmSync(tmp,{recursive:true,force:true});
  console.log(JSON.stringify({status:report.status,checks:report.checks.length,
    screenshots:report.screenshots.length,errors:report.errors.length,failure:report.failure||null}));
}})().catch(err=>{console.error(err);process.exitCode=1;});
