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
  DB_ENGINE:'sqlite',NEXT_PUBLIC_API_URL:api+'/api',CSRF_TRUSTED_ORIGINS:origin,CORS_ALLOWED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P12',status:'RUNNING',checks:[],screenshots:[],errors:[],
  limits:['Synthetic, fresh isolated SQLite only','Fictional review evidence confers no real scientific or legal approval','No existing user data or canonical database touched']};
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
  page.setDefaultTimeout(20000);
  page.setDefaultNavigationTimeout(20000);
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
async function post(page,route,body,etag){
  return page.evaluate(async({route,body,etag})=>{
    const csrf=await (await fetch('/api/admin/auth/csrf/',{cache:'no-store'})).json();
    const response=await fetch('/api/admin'+route,{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRFToken':csrf.csrf_token,...(etag?{'If-Match':etag}:{})},
      body:JSON.stringify(body)});
    return {status:response.status,data:await response.json()};
  },{route,body,etag});
}
async function publicRequest(page,route,token,body){
  return page.evaluate(async({url,token,body})=>{
    const response=await fetch(url,{cache:'no-store',
      method:body===undefined?'GET':'POST',
      headers:{...(token?{Authorization:'Bearer '+token}:{}),'Content-Type':'application/json'},
      ...(body===undefined?{}:{body:JSON.stringify(body)})});
    return {status:response.status,data:await response.json()};
  },{url:api+'/api'+route,token,body});
}
function historySnapshot(){
  return JSON.parse(execFileSync(py,['-c',[
    'import os,sqlite3,json,hashlib',
    'from pathlib import Path',
    'c=sqlite3.connect(Path(os.environ["SQLITE_PATH"]).as_uri()+"?mode=ro",uri=True)',
    'tables=["atlas_caseattempt","atlas_caseattemptevent","atlas_caseattemptanswer","atlas_studyactivity","atlas_quizattempt","atlas_quizattemptanswer","atlas_userflashcardprogress"]',
    'rows={t:c.execute("SELECT * FROM "+t+" ORDER BY id").fetchall() for t in tables}',
    'print(json.dumps({"counts":{t:len(r) for t,r in rows.items()},"digest":hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}))',
    'c.close()',
  ].join('\n')],{env,encoding:'utf8'}));
}
(async()=>{try{
  const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{
    cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
  check(!!fixture.p12&&!!fixture.users.owner&&!!fixture.users.case_reader,
    'Synthetic published case and scoped MFA-only reader in disposable SQLite');
  const historyBefore=historySnapshot();
  check(historyBefore.counts.atlas_caseattempt===1&&historyBefore.counts.atlas_caseattemptevent===2&&
    Object.values(historyBefore.counts).every(count=>count>0),
    'Nonempty scored case answers, quiz answers, activity and SRS exist before publication');
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
  const learnerLogin=await publicRequest(owner,'/auth/login/',null,{
    username:fixture.users.owner.username,password:fixture.users.owner.password});
  check(learnerLogin.status===200&&!!learnerLogin.data.access,'Synthetic learner uses actual JWT authentication');
  const learnerToken=learnerLogin.data.access;
  const historicalState=await publicRequest(owner,'/case-attempts/'+fixture.p12.attempt+'/',learnerToken);
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
  const graphWrite=owner.waitForResponse(r=>r.url().replace(/\/$/,'').endsWith(prefix+draft.revision_id+'/graph/edit')&&r.request().method()==='POST'&&!(r.status()>=300&&r.status()<400));
  await editor.getByRole('button',{name:'ذخیرهٔ ساختار Draft'}).click();
  const graphResponse=await graphWrite;
  const graphResult=await graphResponse.json();
  check(graphResponse.status()===200,'Graph save response commits before verification '+
    JSON.stringify({status:graphResponse.status(),code:graphResult.code}));
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
  await owner.getByLabel('انتخاب مسیر این گام').selectOption({label:'Synthetic scored choice'});
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
  const metadataWrite=owner.waitForResponse(r=>r.url().replace(/\/$/,'').endsWith(prefix+draft.revision_id+'/metadata')&&r.request().method()==='POST'&&!(r.status()>=300&&r.status()<400));
  await metadata.getByRole('button',{name:'ذخیرهٔ اطلاعات پیش‌نویس'}).click();
  check((await metadataWrite).status()===200,'Metadata save response commits before verification');
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
  // Scoped reviewers are separate from the author/publisher under two-person policy.
  const reviewerContext=await browser.newContext({viewport:{width:1280,height:850}});
  const reviewer=await reviewerContext.newPage();
  reviewer.on('pageerror',e=>report.errors.push(String(e)));
  await login(reviewer,fixture.users.case_reviewer);
  await reviewer.goto(origin+'/admin-console/content/cases');
  await reviewer.getByRole('button',{name:'باز کردن Draft'}).first().click();
  const reviewPanel=reviewer.getByRole('heading',{name:'مرکز انتشار نسخهٔ کیس (P16)'}).locator('..');
  await owner.setViewportSize({width:1280,height:850});
  await owner.goto(origin+'/admin-console/content/cases');
  await owner.getByRole('button',{name:'باز کردن Draft'}).first().click();
  const panel=owner.getByRole('heading',{name:'مرکز انتشار نسخهٔ کیس (P16)'}).locator('..');
  await panel.getByText('SOURCE_REVIEW_REQUIRED').first().waitFor();
  check(true,'P16 UI presents the missing revision-scoped source review');
  await reviewPanel.getByLabel('شناسهٔ SourceReference تأییدشده').fill(String(fixture.p12.source));
  await reviewPanel.getByLabel('محل دقیق مدرک برای همین ادعا').fill('Synthetic section 1, isolated QA');
  await reviewPanel.getByRole('checkbox').first().check();
  await reviewPanel.getByRole('button',{name:'ثبت تصمیم نسخه‌مند'}).click();
  await reviewPanel.getByText('تأیید‌شده برای این نسخه').first().waitFor();
  check(true,'P16 source review form records an exact-version decision');
  const approverContext=await browser.newContext({viewport:{width:1280,height:850}});
  const approver=await approverContext.newPage();
  approver.on('pageerror',e=>report.errors.push(String(e)));
  await login(approver,fixture.users.case_approver);
  await approver.goto(origin+'/admin-console/content/cases');
  await approver.getByRole('button',{name:'باز کردن Draft'}).first().click();
  const approvalPanel=approver.getByRole('heading',{name:'مرکز انتشار نسخهٔ کیس (P16)'}).locator('..');
  await approvalPanel.getByLabel('شناسهٔ SourceReference تأییدشده').fill(String(fixture.p12.source));
  await approvalPanel.getByLabel('محل دقیق مدرک برای همین ادعا').fill('Synthetic independent science review');
  await approvalPanel.getByRole('checkbox').first().check();
  await approvalPanel.getByRole('button',{name:'ثبت تصمیم نسخه‌مند'}).click();
  await approvalPanel.getByText('تأیید‌شده برای این نسخه').nth(1).waitFor();
  check(true,'P16 scientific form records a separate privileged decision');
  await reviewPanel.getByLabel('نوع بررسی').selectOption('rights');
  await reviewPanel.getByLabel('دارندهٔ حق',{exact:true}).fill('Synthetic original fixture owner');
  await reviewPanel.getByLabel('مبنای شناسایی دارندهٔ حق').fill('Explicit fictional test declaration');
  await reviewPanel.getByLabel('شرح دقیق اجازهٔ نمایش عمومی متن دیجیتال').fill('Isolated fictional rights claim for disposable QA only');
  await reviewPanel.getByLabel('قلمرو مجوز').fill('Synthetic QA territory');
  const future=days=>new Date(Date.now()+days*86400000).toISOString().slice(0,10);
  await reviewPanel.getByLabel('تاریخ بازبینی بعدی').fill(future(120));
  await reviewPanel.getByLabel('انقضای مجوز، در صورت وجود').fill(future(180));
  await reviewPanel.getByRole('checkbox').first().check();
  await reviewPanel.getByRole('button',{name:'ثبت تصمیم نسخه‌مند'}).click();
  await reviewPanel.getByText('تأیید‌شده برای این نسخه').nth(2).waitFor();
  check(true,'P16 rights form requires explicit scope, holder and dated review');
  await panel.getByRole('button',{name:'تازه‌سازی وضعیت بررسی‌ها'}).click();
  await panel.getByRole('button',{name:'ساخت مانیفست ثابت سروری'}).click();
  await panel.getByText('وضعیت مانیفست:').waitFor();
  const p16Plan=await panel.getByPlaceholder('UUID مانیفست').inputValue();
  check(/^[0-9a-f-]{36}$/.test(p16Plan),'P16 server freezes a version-bound manifest');
  const planFrozen=await query(owner,'/publication/cases/plans/'+p16Plan+'/');
  const planRoute='/publication/cases/plans/'+p16Plan+'/';
  const applyBody={manifest_digest:planFrozen.data.manifest_digest,idempotency_key:crypto.randomUUID()};
  check((await post(owner,planRoute+'apply/',applyBody)).status===409,
    'Frozen manifest without independent approval cannot be applied');
  await approvalPanel.getByPlaceholder('UUID مانیفست').fill(p16Plan);
  await approvalPanel.getByRole('button',{name:'دریافت وضعیت و رسید'}).click();
  await approvalPanel.getByText('frozen',{exact:true}).first().waitFor();
  await approvalPanel.getByRole('checkbox').last().check();
  await approvalPanel.getByRole('button',{name:'تأیید مانیفست'}).click();
  await approvalPanel.getByText('approved',{exact:true}).first().waitFor();
  await panel.getByRole('button',{name:'دریافت وضعیت و رسید'}).click();
  await panel.getByText('approved',{exact:true}).first().waitFor();
  check(true,'A separate scoped MFA reviewer approves the frozen manifest');
  const planBeforeApply=await query(owner,'/publication/cases/plans/'+p16Plan+'/');
  const graphBeforeApply=await query(owner,prefix+draft.revision_id+'/graph/');
  check(planBeforeApply.status===200&&planBeforeApply.data.status==='approved'&&
    planBeforeApply.data.receipts.length===0&&
    graphBeforeApply.data.revision_status==='draft',
    'P16 browser confirms Freeze and approval cannot silently activate a draft');
  await owner.screenshot({path:path.join(out,'case-publication-before-apply.png'),fullPage:true});
  report.screenshots.push('case-publication-before-apply.png');
  check((await post(reader,planRoute+'apply/',applyBody)).status===403,
    'Read-only MFA user cannot publish through a forged direct request');
  check((await post(owner,planRoute+'apply/',{...applyBody,manifest_digest:'0'.repeat(64)})).status===412,
    'Stale manifest digest fails before any publication');
  check((await post(owner,planRoute+'apply/',applyBody)).status===403,
    'Approved manifest still requires action-bound fresh MFA');
  await panel.getByRole('checkbox').last().check();
  await panel.getByLabel('روش احراز دوباره').selectOption('recovery');
  await panel.getByLabel('کد MFA').fill('invalid-recovery-code');
  await panel.getByRole('button',{name:'تأیید نهایی و انتشار نسخه'}).click();
  await panel.getByRole('alert').waitFor();
  check((await query(owner,planRoute)).data.receipts.length===0,
    'Invalid browser MFA cannot apply or create a receipt');
  // django-otp throttles the recovery device for one second after a failed code.
  await new Promise(resolve=>setTimeout(resolve,1100));
  let firstApplyKey;
  await owner.route('**'+planRoute+'apply/',async route=>{
    firstApplyKey=route.request().postDataJSON().idempotency_key;
    const response=await route.fetch();
    check(response.status()===200,'Real Apply commits before simulated lost response');
    await route.fulfill({status:200,contentType:'application/json',body:'unreadable lost response'});
  },{times:1});
  await panel.getByLabel('کد MFA').fill(fixture.users.owner.tokens[1]);
  const lostApply=owner.waitForResponse(r=>r.url().endsWith(planRoute+'apply/')&&r.request().method()==='POST');
  await panel.getByRole('button',{name:'تأیید نهایی و انتشار نسخه'}).click();
  await lostApply;
  await panel.getByRole('alert').waitFor();
  const appliedOnce=await query(owner,planRoute);
  check(appliedOnce.data.status==='applied'&&appliedOnce.data.receipts.length===1,
    'Unknown browser outcome has exactly one server publication receipt');
  const retriedRequest=owner.waitForRequest(r=>r.url().endsWith(planRoute+'apply/')&&r.method()==='POST');
  await panel.getByLabel('کد MFA').fill(fixture.users.owner.tokens[2]);
  await panel.getByRole('button',{name:'تأیید نهایی و انتشار نسخه'}).click();
  check((await retriedRequest).postDataJSON().idempotency_key===firstApplyKey,
    'Retry after an unknown Apply outcome reuses the original idempotency key');
  await panel.getByText('applied',{exact:true}).first().waitFor();
  const applied=await query(owner,planRoute);
  const current=await query(owner,prefix+draft.revision_id+'/graph/');
  const old=await query(owner,prefix+fixture.p12.revision+'/graph/');
  check(applied.data.receipts.length===1&&applied.data.receipts[0].id===appliedOnce.data.receipts[0].id,
    'Browser retry returns the original receipt without duplicate publication');
  check(current.data.current_revision_id===draft.revision_id&&current.data.revision_status==='published',
    'Successful browser Apply switches current revision to the reviewed draft');
  check(JSON.stringify(old.data.steps)===JSON.stringify(unchanged.data.steps)&&old.data.revision_status==='published',
    'Previous published revision graph remains unchanged after Apply');
  check(historySnapshot().digest===historyBefore.digest,
    'Apply and retry preserve historical attempts, events, answers, activity and SRS byte-for-byte');
  const publicCase=await publicRequest(owner,'/cases/'+fixture.p12.slug+'/',null);
  const publicList=await publicRequest(owner,'/cases/',null);
  check(publicCase.status===200&&publicCase.data.title===current.data.title&&
    publicList.data.results.some(item=>item.slug===fixture.p12.slug),
    'Actual public case detail and list expose the newly published revision');
  const publicPage=await ownerContext.newPage();
  publicPage.setDefaultTimeout(20000);
  publicPage.on('pageerror',e=>report.errors.push(String(e)));
  await publicPage.goto(origin+'/cases/'+fixture.p12.slug);
  await publicPage.getByRole('heading',{name:current.data.title,exact:true}).waitFor();
  check(true,'Public case page renders the reviewed revision in the browser');
  check(JSON.stringify((await publicRequest(owner,'/case-attempts/'+fixture.p12.attempt+'/',learnerToken)).data)===
    JSON.stringify(historicalState.data),'Historical scored attempt API remains pinned after publication');
  await owner.screenshot({path:path.join(out,'case-publication-receipt.png'),fullPage:true});
  report.screenshots.push('case-publication-receipt.png');
  await panel.getByRole('checkbox').last().check();
  await panel.getByLabel('روش احراز دوباره').selectOption('recovery');
  await panel.getByLabel('کد MFA').fill(fixture.users.owner.tokens[3]);
  await panel.getByRole('button',{name:'لغو نمایش عمومی و ثبت رسید'}).click();
  await panel.getByText('withdrawn',{exact:true}).first().waitFor();
  check((await query(owner,planRoute)).data.receipts.length===2&&historySnapshot().digest===historyBefore.digest,
    'Browser MFA withdrawal adds one compensating receipt and preserves all learner history');
  check((await publicRequest(owner,'/cases/'+fixture.p12.slug+'/',null)).status===404&&
    !(await publicRequest(owner,'/cases/',null)).data.results.some(item=>item.slug===fixture.p12.slug),
    'Withdrawal removes the case from actual public detail and list');
  const withdrawnPage=await publicPage.goto(origin+'/cases/'+fixture.p12.slug);
  await publicPage.getByRole('heading',{name:'این صفحه پیدا نشد',exact:true}).waitFor();
  check(await publicPage.getByRole('heading',{name:current.data.title,exact:true}).count()===0,
    'Withdrawn public page renders not-found without case content (HTTP '+withdrawnPage.status()+')');
  check((await publicRequest(owner,'/cases/'+fixture.p12.slug+'/attempts/',learnerToken,{})).status===404,
    'Withdrawal rejects new learner start requests');
  const resumed=await publicRequest(owner,'/cases/'+fixture.p12.slug+'/attempts/current/',learnerToken);
  check(resumed.status===200&&JSON.stringify(resumed.data)===JSON.stringify(historicalState.data),
    'Withdrawn case still resumes the unchanged historical scored attempt');
  const completed=await publicRequest(owner,'/case-attempts/'+fixture.p12.attempt+'/decisions/',learnerToken,{
    step_id:fixture.p12.end,state_version:historicalState.data.state_version,choice_id:null});
  check(completed.status===200&&completed.data.status==='completed'&&completed.data.score===3&&
    completed.data.case.revision_number===1&&completed.data.history.length===3,
    'Historical scored attempt completes on its original revision after browser withdrawal');
  check(report.errors.length===0,'Browser emitted no uncaught runtime errors');
  report.status='PASS';
  await approverContext.close();await reviewerContext.close();await readerContext.close();await ownerContext.close();
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
