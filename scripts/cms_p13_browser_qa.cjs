// Real learning-editor UI against a fresh synthetic database, never the canonical DB.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
let chromium;try{({chromium}=require('playwright'));}catch(e){if(e.code!=='MODULE_NOT_FOUND')throw e;({chromium}=require(path.join(os.tmpdir(),'atlas-p07-browser-tools/node_modules/playwright')));}
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-p13-browser-'));
const out=process.env.CMS_QA_OUTPUT||path.join(root,'qa/p13-browser');fs.mkdirSync(out,{recursive:true});
const py=process.env.CMS_QA_PYTHON||(process.platform==='win32'?path.join(root,'backend/.venv/Scripts/python.exe'):'python');
const origin=process.env.CMS_QA_ORIGIN||'http://127.0.0.1:3000',api=process.env.CMS_QA_API_ORIGIN||'http://127.0.0.1:8000';
assert(new URL(origin).hostname==='127.0.0.1'&&new URL(api).hostname==='127.0.0.1');
const env={...process.env,DB_ENGINE:'sqlite',SQLITE_PATH:path.join(tmp,'cms-journey.sqlite3'),
  SQLITE_TEST_PATH:path.join(tmp,'tests.sqlite3'),CMS_ARTIFACT_ROOT:path.join(tmp,'private'),
  CMS_QA_PHASE:'p13',NEXT_PUBLIC_API_URL:api+'/api',CSRF_TRUSTED_ORIGINS:origin,CORS_ALLOWED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P13',status:'RUNNING',checks:[],screenshots:[],errors:[],
  limits:['Synthetic isolated SQLite only','No scientific/rights approval or publication; no production rollout']};
const processes=[];let browser;
function check(ok,message){assert(ok,message);report.checks.push(message);}
function start(exe,args,cwd,name){
  const log=fs.openSync(path.join(tmp,name+'.log'),'a');
  const proc=spawn(exe,args,{cwd,env,windowsHide:true,stdio:['ignore',log,log]});
  fs.closeSync(log);processes.push(proc);return proc;
}
async function ready(url,proc){
  for(let i=0;i<100;i++){
    assert(proc.exitCode===null,'Owned server exited before readiness');
    try{if((await fetch(url,{signal:AbortSignal.timeout(1500)})).status<500)return;}catch{}
    await new Promise(resolve=>setTimeout(resolve,300));
  }
  throw Error('Owned server readiness timeout');
}
async function login(page,user){
  page.setDefaultTimeout(20000);page.on('pageerror',e=>report.errors.push(String(e)));
  await page.goto(origin+'/admin-console');
  await page.getByLabel('نام کاربری',{exact:true}).fill(user.username);
  await page.getByLabel('گذرواژه',{exact:true}).fill(user.password);
  await page.getByRole('button',{name:'ادامه با گذرواژه'}).click();
  await page.getByLabel('روش تأیید').selectOption('recovery');
  await page.getByLabel('کد تأیید',{exact:true}).fill(user.tokens[0]);
  await page.getByRole('button',{name:'تأیید و ورود'}).click();
  await page.getByRole('button',{name:'خروج',exact:true}).waitFor();
  await page.goto(origin+'/admin-console/content/learning-quizzes');
  await page.getByRole('heading',{name:'مدیریت آزمون‌های آموزشی'}).waitFor();
}
async function request(page,route,body,etag){
  return page.evaluate(async({route,body,etag})=>{
    const headers={};if(body!==undefined){
      headers['X-CSRFToken']=(await(await fetch('/api/admin/auth/csrf/',{cache:'no-store'})).json()).csrf_token;
      headers['Content-Type']='application/json';if(etag)headers['If-Match']=etag;
    }
    const response=await fetch('/api/admin'+route,{cache:'no-store',credentials:'same-origin',headers,
      ...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)})});
    return {status:response.status,data:await response.json(),etag:response.headers.get('ETag')};
  },{route,body,etag});
}
function history(){return JSON.parse(execFileSync(py,['-c',[
  'import os,sqlite3,json,hashlib','from pathlib import Path',
  'c=sqlite3.connect(Path(os.environ["SQLITE_PATH"]).as_uri()+"?mode=ro",uri=True)',
  'rows={t:c.execute("SELECT * FROM "+t+" ORDER BY id").fetchall() for t in ["atlas_quizattempt","atlas_quizattemptanswer","atlas_studyactivity","atlas_userflashcardprogress","atlas_dailychallengeattempt","atlas_cognitivedistortionpracticeattempt","atlas_userprogress","atlas_userconceptprogress"]}',
  'print(json.dumps({"counts":[len(v) for v in rows.values()],"digest":hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}))','c.close()',
].join('\n')],{env,encoding:'utf8'}));}
function writeResponse(page,suffix){return page.waitForResponse(r=>r.url().replace(/\/$/,'').endsWith(suffix)&&
  r.request().method()==='POST'&&!(r.status()>=300&&r.status()<400));}
function archiveEvidence(){return JSON.parse(execFileSync(py,['-c',[
  'import os,sqlite3,json','from pathlib import Path',
  'c=sqlite3.connect(Path(os.environ["SQLITE_PATH"]).as_uri()+"?mode=ro",uri=True)',
  'print(json.dumps({"receipts":c.execute("SELECT kind,resource_id,COUNT(*) FROM atlas_learningarchivereceipt GROUP BY kind,resource_id ORDER BY kind").fetchall(),"audit":c.execute("SELECT target_kind,target_id,COUNT(*) FROM atlas_adminauditevent WHERE action=\'learning.archived\' GROUP BY target_kind,target_id ORDER BY target_kind").fetchall()}))','c.close()',
].join('\n')],{env,encoding:'utf8'}));}
function runWorker(){
  const result=execFileSync(py,['manage.py','cms_worker','--once'],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:90000});
  assert(result.trim().endsWith(' succeeded'),'Owned native worker did not finish successfully');
}
function expireRevokedOutput(identifier){
  execFileSync(py,['-c',[
    'import os,sys,tempfile','from pathlib import Path',
    'database=Path(os.environ["SQLITE_PATH"]).resolve()',
    'assert database.parent.parent==Path(tempfile.gettempdir()).resolve() and database.parent.name.startswith("atlas-p13-browser-") and database.name=="cms-journey.sqlite3"',
    'os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")','import django;django.setup()',
    'from atlas.cms_job_models import AdminArtifact','from django.utils import timezone','from datetime import timedelta',
    'rows=AdminArtifact.objects.filter(pk=sys.argv[1],owner__username="qa_owner",kind="learning_export_json",resource_type="learning_export",state="revoked")',
    'assert rows.count()==1','assert rows.update(expires_at=timezone.now()-timedelta(seconds=1))==1',
  ].join('\n'),identifier],{cwd:path.join(root,'backend'),env,encoding:'utf8'});
}
function transferEvidence(){return JSON.parse(execFileSync(py,['-c',[
  'import os,sqlite3,json','from pathlib import Path',
  'c=sqlite3.connect(Path(os.environ["SQLITE_PATH"]).as_uri()+"?mode=ro",uri=True)',
  'tables=["atlas_quiz","atlas_flashcard","atlas_dailychallenge","atlas_cognitivedistortionpracticeitem"]',
  'print(json.dumps({"content_counts":[c.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in tables],"jobs":c.execute("SELECT kind,COUNT(*) FROM atlas_adminjob GROUP BY kind ORDER BY kind").fetchall(),"audit":c.execute("SELECT action,COUNT(*) FROM atlas_adminauditevent WHERE action IN (\'learning.imported\',\'learning.exported\') GROUP BY action ORDER BY action").fetchall(),"artifacts":c.execute("SELECT kind,resource_type,state,COUNT(*) FROM atlas_adminartifact GROUP BY kind,resource_type,state ORDER BY kind,resource_type").fetchall()}))','c.close()',
].join('\n')],{env,encoding:'utf8'}));}
function archiveControl(page){return page.getByRole('heading',{name:'بایگانی کنترل‌شدهٔ محتوا',exact:true}).locator('..');}
async function prepareArchive(page,token){
  const form=archiveControl(page);
  await form.getByRole('checkbox').check();
  await form.getByLabel('روش تأیید بایگانی').selectOption('recovery');
  await form.getByLabel('کد MFA برای بایگانی').fill(token);
  await form.getByRole('button',{name:'بایگانی با تأیید دومرحله‌ای',exact:true}).focus();
}
async function learnerToken(user){
  const response=await fetch(api+'/api/auth/login/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(user)});
  assert.equal(response.status,200);return (await response.json()).access;
}
async function learnerRequest(page,token,route,body){
  return page.evaluate(async({token,route,body,api})=>{
    const response=await fetch(api+'/api'+route,{cache:'no-store',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
      ...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)})});
    return {status:response.status,data:await response.json()};
  },{token,route,body,api});
}
(async()=>{try{
  const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
  const before=history();check(before.counts.every(n=>n>0),'Existing synthetic quiz answers, learning activity and SRS are nonempty');
  const django=start(py,['manage.py','runserver','127.0.0.1:'+new URL(api).port,'--noreload'],path.join(root,'backend'),'django');
  await ready(api+'/api/admin/auth/csrf/',django);
  const next=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-H','127.0.0.1','-p',new URL(origin).port],path.join(root,'frontend'),'next');
  await ready(origin+'/admin-console',next);
  browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
  const ownerContext=await browser.newContext({viewport:{width:1280,height:850}}),owner=await ownerContext.newPage();
  await login(owner,fixture.users.owner);check(true,'Owner opens the real Quiz editor using MFA and CSRF');
  const create=owner.getByRole('heading',{name:'ساخت آزمون غیرفعال و منتشرنشده'}).locator('..');
  await create.getByLabel('شناسهٔ لاتین').fill('p13-browser-draft');
  await create.getByLabel('عنوان',{exact:true}).fill('P13 fictional draft');
  await create.getByLabel('شرح',{exact:true}).fill('Synthetic original description');
  await create.getByRole('button',{name:'ساخت Draft غیرفعال'}).click();
  await owner.getByRole('heading',{name:'P13 fictional draft',exact:true}).waitFor();
  await owner.getByRole('button',{name:'افزودن سؤال',exact:true}).click();
  const question=owner.getByRole('heading',{name:'سؤال‌ها (1)',exact:true}).locator('..').locator('details').first();
  await question.locator('summary').click();
  await question.getByLabel('متن سؤال').fill('Fictional question?');
  await question.getByLabel('گزینه 1',{exact:true}).fill('Synthetic correct choice');
  await question.getByLabel('گزینه 2',{exact:true}).fill('Synthetic distractor');
  const savedQuestions=writeResponse(owner,'/questions/replace');
  await owner.getByRole('button',{name:'ذخیرهٔ سؤال‌ها در Draft'}).click();
  check((await savedQuestions).status()===200,'Real question editor creates a valid private answer key');
  const catalog=await request(owner,'/learning/quizzes/');
  const id=catalog.data.results.find(row=>row.slug==='p13-browser-draft').quiz_id;
  const route='/learning/quizzes/'+id+'/',original=await request(owner,route);
  const metadata=owner.getByRole('group',{name:'اطلاعات آزمون غیرفعال'});
  await metadata.getByLabel('عنوان آزمون',{exact:true}).fill('P13 saved fictional title');
  await metadata.getByLabel('شرح آزمون').fill('Synthetic metadata change only');
  check(await owner.getByRole('button',{name:'ذخیرهٔ سؤال‌ها در Draft'}).isDisabled(),'Unsaved metadata cannot be overwritten by a question save');
  const savedMetadata=writeResponse(owner,'/metadata');
  await metadata.getByRole('button',{name:'ذخیرهٔ اطلاعات آزمون'}).focus();await owner.keyboard.press('Enter');
  check((await savedMetadata).status()===200,'Keyboard submission saves Quiz metadata through the real form');
  await owner.getByRole('heading',{name:'P13 saved fictional title',exact:true}).waitFor();
  const changed=await request(owner,route);
  check(changed.etag!==original.etag&&!changed.data.is_active&&
    JSON.stringify(changed.data.questions)===JSON.stringify(original.data.questions),
    'Metadata changes advance ETag and preserve question IDs, answer key and private visibility');
  check((await request(owner,route+'metadata/',{title:'Stale attempt',description:'',disorder_id:null},original.etag)).status===412,'Stale browser edit is rejected');
  await owner.getByLabel('Synthetic correct choice',{exact:true}).check();
  await owner.getByRole('button',{name:'اجرای پیش‌نمایش بی‌اثر'}).click();
  await owner.getByText(/امتیاز فرضی/).waitFor();
  check(history().digest===before.digest,'Quiz preview and metadata edits preserve all historical quiz rows and activity');
  check((await owner.evaluate(async url=>(await fetch(url)).status,api+'/api/quizzes/p13-browser-draft/'))===404,'Unreviewed Quiz remains absent from the public API');
  await owner.screenshot({path:path.join(out,'quiz-metadata-desktop.png'),fullPage:true});report.screenshots.push('quiz-metadata-desktop.png');
  await owner.setViewportSize({width:320,height:790});
  check(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Quiz editor fits 320px viewport');
  await owner.screenshot({path:path.join(out,'quiz-metadata-mobile.png'),fullPage:true});report.screenshots.push('quiz-metadata-mobile.png');
  const readerContext=await browser.newContext(),reader=await readerContext.newPage();await login(reader,fixture.users.learning_reader);
  await reader.locator('li').filter({hasText:'P13 saved fictional title'}).getByRole('button',{name:'باز کردن',exact:true}).click();
  await reader.getByRole('heading',{name:'P13 saved fictional title',exact:true}).waitFor();
  check(await reader.getByRole('group',{name:'اطلاعات آزمون غیرفعال'}).count()===0&&
    (await request(reader,route+'metadata/',{title:'Forbidden',description:'',disorder_id:null},changed.etag)).status===403,
    'View-only MFA role has no metadata form and cannot forge an edit');
  await owner.locator('li').filter({hasText:'Synthetic historical quiz'}).getByRole('button',{name:'باز کردن',exact:true}).click();
  await owner.getByRole('heading',{name:'Synthetic historical quiz',exact:true}).waitFor();
  const historicalRoute='/learning/quizzes/'+fixture.p13.historical_quiz+'/',historical=await request(owner,historicalRoute);
  check(historical.data.history_protected&&await owner.getByRole('group',{name:'اطلاعات آزمون غیرفعال'}).count()===0&&
    (await request(owner,historicalRoute+'metadata/',{title:'Forbidden historical rewrite',description:'',disorder_id:null},historical.etag)).status===409&&history().digest===before.digest,
    'Historical Quiz stays locked in UI/API and preserves actual answers/activity');
  await owner.setViewportSize({width:1280,height:850});
  await owner.goto(origin+'/admin-console/content/learning-flashcards');
  await owner.getByRole('heading',{name:'کارت‌های آموزشی و حفاظت SRS',exact:true}).waitFor();
  const createCard=owner.getByRole('group',{name:'محتوای کارت',exact:true});
  await createCard.getByLabel('شناسهٔ لاتین').fill('p13-browser-card');
  await createCard.getByLabel('روی کارت').fill('P13 fictional front');
  await createCard.getByLabel('پشت کارت').fill('P13 fictional back');
  await createCard.getByLabel('شناسهٔ مفهوم مرتبط (اختیاری)',{exact:true}).fill(String(fixture.p13.concept));
  await createCard.getByLabel('شناسهٔ اختلال مرتبط (اختیاری)',{exact:true}).fill(String(fixture.p13.disorder));
  await createCard.getByRole('button',{name:'ساخت کارت خصوصی'}).click();
  await owner.getByRole('heading',{name:'کارت: p13-browser-card',exact:true}).waitFor();
  const cardCatalog=await request(owner,'/learning/flashcards/');
  const cardId=cardCatalog.data.results.find(row=>row.slug==='p13-browser-card').flashcard_id;
  const cardRoute='/learning/flashcards/'+cardId+'/',cardBefore=await request(owner,cardRoute);
  check(!cardBefore.data.is_active&&cardBefore.data.concept_id===fixture.p13.concept&&
    cardBefore.data.disorder_id===fixture.p13.disorder,'Flashcard form creates a private card with validated Concept/Disorder relationships');
  const editCard=owner.getByRole('group',{name:'ویرایش کارت خصوصی',exact:true});
  await editCard.getByLabel('روی کارت').fill('P13 updated fictional front');
  await editCard.getByLabel('شناسهٔ مفهوم مرتبط (اختیاری)',{exact:true}).fill('');
  const cardWrite=writeResponse(owner,'/flashcards/'+cardId+'/metadata');
  await editCard.getByRole('button',{name:'ذخیرهٔ Draft کارت'}).click();
  check((await cardWrite).status()===200,'Flashcard relationship update succeeds through the real audited API');
  const cardAfter=await request(owner,cardRoute);
  check(cardAfter.data.front==='P13 updated fictional front'&&cardAfter.data.concept_id===null&&
    cardAfter.data.disorder_id===fixture.p13.disorder&&!cardAfter.data.is_active&&cardAfter.etag!==cardBefore.etag,
    'Clearing one relationship preserves the other, card identity and private visibility');
  await owner.setViewportSize({width:320,height:790});
  check(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Flashcard relationship editor fits 320px viewport');
  await owner.screenshot({path:path.join(out,'flashcard-relationships-mobile.png'),fullPage:true});report.screenshots.push('flashcard-relationships-mobile.png');
  await owner.locator('li').filter({hasText:'p13-historical-card'}).getByRole('button',{name:'باز کردن',exact:true}).click();
  await owner.getByRole('heading',{name:'کارت: p13-historical-card',exact:true}).waitFor();
  const historicalCardRoute='/learning/flashcards/'+fixture.p13.historical_card+'/',historicalCard=await request(owner,historicalCardRoute);
  check(historicalCard.data.history_protected&&await owner.getByRole('group',{name:'ویرایش کارت خصوصی',exact:true}).count()===0&&
    (await request(owner,historicalCardRoute+'metadata/',{concept_id:fixture.p13.concept},historicalCard.etag)).status===409&&history().digest===before.digest,
    'Historical Flashcard relations cannot be changed; real SRS and all learner history stay unchanged');
  const freshToken=await learnerToken(fixture.users.learning_fresh),historicalToken=await learnerToken(fixture.users.owner);
  const historicalDashboard=await learnerRequest(owner,historicalToken,'/dashboard/');
  check((await learnerRequest(owner,freshToken,'/quizzes/p13-historical-fixture/')).status===200&&
    (await learnerRequest(owner,freshToken,'/flashcards/')).data.results.some(r=>r.slug==='p13-historical-card')&&
    (await learnerRequest(owner,freshToken,'/daily-challenge/')).status===200&&
    (await learnerRequest(owner,freshToken,'/cognitive-distortions/practice/')).data.items.some(r=>r.slug==='p13-archive-practice'),
    'All four synthetic archive targets are available before the operation');
  check(await archiveControl(reader).getByRole('button').count()===0&&
    (await request(reader,'/learning/archive/quiz/'+id+'/',{reason:'CONTENT_ARCHIVE',idempotency_key:crypto.randomUUID()},changed.etag)).status===403,
    'Read-only role has no Archive form and a forged Archive request is denied');
  await owner.locator('li').filter({hasText:'p13-browser-card'}).getByRole('button',{name:'باز کردن',exact:true}).click();
  await owner.getByRole('heading',{name:'کارت: p13-browser-card',exact:true}).waitFor();
  const concurrentEdit=await request(owner,cardRoute+'metadata/',{front:'Synthetic concurrent update'},cardAfter.etag);
  assert.equal(concurrentEdit.status,200);
  await prepareArchive(owner,fixture.users.owner.tokens[1]);
  const staleArchive=writeResponse(owner,'/archive/flashcard/'+cardId);
  await owner.keyboard.press('Enter');
  check((await staleArchive).status()===412&&archiveEvidence().receipts.length===0,
    'A concurrent edit makes the actual Archive form fail on stale ETag without a receipt');
  await archiveControl(owner).getByRole('alert').waitFor();
  const specs=[
    {kind:'flashcard',id:fixture.p13.historical_card,page:'learning-flashcards',label:'p13-historical-card'},
    {kind:'quiz',id:fixture.p13.historical_quiz,page:'learning-quizzes',label:'Synthetic historical quiz'},
    {kind:'daily',id:fixture.p13.daily,page:'learning-practice',label:'Synthetic archive daily question'},
    {kind:'distortions',id:fixture.p13.practice,page:'learning-practice',label:'Synthetic archive practice question'},
  ];
  let tokenIndex=2;
  for(const spec of specs){
    await owner.goto(origin+'/admin-console/content/'+spec.page);
    if(spec.kind==='daily')await owner.locator('li').filter({hasText:spec.label}).getByRole('button',{name:'باز کردن',exact:true}).waitFor();
    if(spec.kind==='daily'||spec.kind==='distortions')await owner.getByLabel('نوع تمرین').selectOption(spec.kind);
    if(spec.kind==='daily')check(await owner.locator('li').filter({hasText:spec.label}).count()===1,
      'Reselecting the loaded current practice kind does not leave the catalog stuck loading');
    await owner.locator('li').filter({hasText:spec.label}).getByRole('button',{name:'باز کردن',exact:true}).click();
    await archiveControl(owner).waitFor();
    const suffix='/archive/'+spec.kind+'/'+spec.id;
    if(spec.kind==='flashcard'){
      await prepareArchive(owner,'invalid-synthetic-mfa');
      const denied=writeResponse(owner,'/auth/step-up');await owner.keyboard.press('Enter');
      check((await denied).status()===403&&archiveEvidence().receipts.length===0,
        'Invalid MFA from the actual Archive form cannot archive content');
      // The installed otp_static device throttles the first failed proof for one second.
      await new Promise(resolve=>setTimeout(resolve,1100));
      let committed,originalKey;
      const pattern='**/api/admin/learning/archive/flashcard/'+spec.id+'/';
      await owner.route(pattern,async intercepted=>{
        originalKey=JSON.parse(intercepted.request().postData()).idempotency_key;
        const response=await intercepted.fetch();assert.equal(response.status(),200);committed=await response.json();
        await intercepted.abort('failed');
      });
      await prepareArchive(owner,fixture.users.owner.tokens[tokenIndex++]);
      const lostResponse=owner.waitForEvent('requestfailed',{predicate:r=>r.url().endsWith('/learning/archive/flashcard/'+spec.id+'/')});
      await owner.keyboard.press('Enter');await lostResponse;
      await archiveControl(owner).getByRole('alert').waitFor();
      await owner.unroute(pattern);
      check(committed?.newly_archived===true&&archiveEvidence().receipts.length===1,
        'Response is deliberately lost after the real Archive commit');
      await prepareArchive(owner,fixture.users.owner.tokens[tokenIndex++]);
      const retried=writeResponse(owner,suffix);await owner.keyboard.press('Enter');
      const response=await retried,body=await response.json();
      check(response.status()===200&&!body.newly_archived&&body.receipt_id===committed.receipt_id&&
        response.request().postDataJSON().idempotency_key===originalKey,
        'UI retry keeps the same key and reconciles the single committed receipt');
    }else{
      await prepareArchive(owner,fixture.users.owner.tokens[tokenIndex++]);
      const archived=writeResponse(owner,suffix);await owner.keyboard.press('Enter');
      const response=await archived;
      check(response.status()===200&&(await response.json()).newly_archived===true,
        spec.kind+' archives through the actual keyboard-submitted MFA form');
    }
    await archiveControl(owner).getByText(/محتوا بایگانی شده است/).waitFor();
    check(history().digest===before.digest,spec.kind+' archive preserves all eight history/progress/SRS table digests');
    check(await archiveControl(owner).getByRole('button').count()===0&&
      await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&getComputedStyle(document.querySelector('[dir="rtl"]')).direction==='rtl'),
      spec.kind+' archive receipt is read-only and fits the RTL mobile layout');
    const filename='archive-'+spec.kind+'-mobile.png';
    await owner.screenshot({path:path.join(out,filename),fullPage:true});report.screenshots.push(filename);
  }
  const evidence=archiveEvidence();
  check(evidence.receipts.length===4&&evidence.audit.length===4&&
    evidence.receipts.every(row=>row[2]===1)&&evidence.audit.every(row=>row[2]===1),
    'Exactly one Receipt and one Audit exist per archived kind, including lost-response retry');
  check((await learnerRequest(owner,freshToken,'/quizzes/p13-historical-fixture/')).status===404&&
    !(await learnerRequest(owner,freshToken,'/flashcards/')).data.results.some(r=>r.slug==='p13-historical-card')&&
    (await learnerRequest(owner,freshToken,'/daily-challenge/')).status===404&&
    !(await learnerRequest(owner,freshToken,'/cognitive-distortions/practice/')).data.items.some(r=>r.slug==='p13-archive-practice'),
    'Fresh public reads immediately exclude all four archives');
  for(const [route,body] of [
    ['/quizzes/p13-historical-fixture/submit/',{answers:[{question_id:fixture.p13.quiz_question,choice_id:fixture.p13.quiz_choice}]}],
    ['/flashcards/p13-historical-card/review/',{rating:'good'}],
    ['/daily-challenge/',{choice_id:fixture.p13.daily_choice}],
    ['/cognitive-distortions/practice/p13-archive-practice/submit/',{choice_id:fixture.p13.practice_choice}],
  ])check((await learnerRequest(owner,freshToken,route,body)).status===404,'Fresh learner writes are denied after Archive: '+route);
  const preservedDashboard=await learnerRequest(owner,historicalToken,'/dashboard/');
  const preservedDaily=await learnerRequest(owner,historicalToken,'/daily-challenge/');
  check(preservedDashboard.status===200&&preservedDashboard.data.quizzes_completed===historicalDashboard.data.quizzes_completed&&
    preservedDaily.status===200&&preservedDaily.data.attempt.selected_choice_id===fixture.p13.daily_choice&&history().digest===before.digest,
    'Authorized historical quiz totals and pinned Daily result survive; all eight tables are unchanged');
  await owner.setViewportSize({width:1280,height:850});
  await owner.goto(origin+'/admin-console/content/learning-transfer');
  await owner.getByRole('heading',{name:'انتقال خصوصی محتوای آموزشی',exact:true}).waitFor();
  await reader.goto(origin+'/admin-console/content/learning-transfer');
  check(await reader.getByLabel('فایل بستهٔ آموزشی').count()===0&&
    await reader.getByRole('button',{name:'ثبت کار خروجی خصوصی',exact:true}).count()===0&&
    (await request(reader,'/learning/transfer/import/',{artifact_id:crypto.randomUUID(),request_key:crypto.randomUUID()})).status===403&&
    (await request(reader,'/learning/transfer/selection/?kind=quiz')).status===403,
    'View-only MFA role has no transfer forms and cannot forge import or export selection');
  await owner.getByText('قالب نسخه‌مند و نمونهٔ هر چهار نوع',{exact:true}).click();
  const bundle=JSON.parse(await owner.getByLabel('نمونهٔ قالب بستهٔ خصوصی').inputValue());
  const practiceFields=bundle.items.find(row=>row.kind==='distortions').fields;
  practiceFields.target_concept_slug=practiceFields.choices[0].concept_slug='p13-synthetic-distortion';
  practiceFields.choices[1].concept_slug='p13-synthetic-other-distortion';
  const preTransfer=transferEvidence();
  await owner.getByLabel('فایل بستهٔ آموزشی').setInputFiles({name:'P13-synthetic-authoring.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))});
  const uploaded=writeResponse(owner,'/artifacts');
  await owner.getByRole('button',{name:'بارگذاری بسته در قرنطینه',exact:true}).click();
  const uploadedResponse=await uploaded;assert.equal(uploadedResponse.status(),201);
  const inputId=(await uploadedResponse.json()).artifact.id;
  const inputCard=owner.getByRole('region',{name:'جزئیات فایل خصوصی',exact:true});
  const validated=writeResponse(owner,'/validate');
  await inputCard.getByRole('button',{name:'اعتبارسنجی جداگانهٔ فایل',exact:true}).click();
  check((await validated).status()===200,'Actual uploaded four-kind JSON is validated privately before enqueue');
  let committedImport,importKey;
  const importPattern='**/api/admin/learning/transfer/import/';
  await owner.route(importPattern,async routed=>{
    const response=await routed.fetch();assert.equal(response.status(),202);
    committedImport=(await response.json()).job;importKey=routed.request().postDataJSON().request_key;
    runWorker();await routed.abort('failed');
  });
  await inputCard.getByRole('button',{name:'بررسی ایجاد کار ورود',exact:true}).click();
  await inputCard.getByRole('button',{name:'تأیید ایجاد کار',exact:true}).click();
  await inputCard.getByRole('button',{name:'تطبیق همان کار ورود',exact:true}).waitFor();
  await owner.unroute(importPattern);
  const importRetry=writeResponse(owner,'/learning/transfer/import');
  await inputCard.getByRole('button',{name:'تطبیق همان کار ورود',exact:true}).click();
  await inputCard.getByRole('button',{name:'تأیید ایجاد کار',exact:true}).click();
  const reconciledImport=await importRetry,importJob=(await reconciledImport.json()).job;
  check(reconciledImport.status()===202&&importJob.id===committedImport.id&&importJob.status==='succeeded'&&
    reconciledImport.request().postDataJSON().request_key===importKey&&importJob.result.created.length===4,
    'Lost import response after real worker commit reconciles the same key and one four-item result through UI');
  const afterImport=transferEvidence();
  check(afterImport.content_counts.every((n,index)=>n===preTransfer.content_counts[index]+1)&&
    afterImport.jobs.find(row=>row[0]==='learning_import')[1]===1&&
    afterImport.audit.find(row=>row[0]==='learning.imported')[1]===1&&history().digest===before.digest,
    'Native import creates four new parents once with one job/audit and unchanged eight-table history');
  const created=importJob.result.created;
  for(const item of created){
    const catalog=await request(owner,'/learning/transfer/selection/?kind='+item.kind);
    check(catalog.status===200&&catalog.data.results.some(row=>row.resource_id===item.resource_id),
      item.kind+' imported draft is private, unseeded, unarchived and without learner history');
  }
  check((await learnerRequest(owner,freshToken,'/quizzes/transfer-example-quiz/')).status===404&&
    !(await learnerRequest(owner,freshToken,'/flashcards/')).data.results.some(row=>row.slug==='transfer-example-card')&&
    !(await learnerRequest(owner,freshToken,'/cognitive-distortions/practice/')).data.items.some(row=>row.slug==='transfer-example-practice'),
    'Imported private authoring content does not grant public availability');
  await inputCard.getByRole('link',{name:'پیگیری کار ایجادشده ←',exact:true}).click();
  await owner.getByText('تعداد آیتم‌های آموزشی پردازش‌شده: ۴',{exact:true}).waitFor();
  check(await owner.getByRole('heading',{name:'پایان‌یافته',exact:true}).count()===1,'Import job detail displays final native worker result and fresh IDs');
  await owner.goto(origin+'/admin-console/content/learning-transfer');
  const exportSection=owner.getByRole('heading',{name:'خروجی خصوصی از نسخه‌های انتخاب‌شده',exact:true}).locator('..');
  for(const item of created){
    await exportSection.getByLabel('نوع محتوا برای خروجی').selectOption(item.kind);
    const selection=await request(owner,'/learning/transfer/selection/?kind='+item.kind);
    const row=selection.data.results.find(entry=>entry.resource_id===item.resource_id);
    await exportSection.locator('li').filter({has:owner.getByText(row.label,{exact:true})}).getByRole('checkbox').check();
  }
  let committedExport,exportKey;
  const exportPattern='**/api/admin/learning/transfer/export/';
  await owner.route(exportPattern,async routed=>{
    const response=await routed.fetch();assert.equal(response.status(),202);
    committedExport=(await response.json()).job;exportKey=routed.request().postDataJSON().request_key;
    runWorker();await routed.abort('failed');
  });
  await exportSection.getByRole('button',{name:'ثبت کار خروجی خصوصی',exact:true}).focus();await owner.keyboard.press('Enter');
  await exportSection.getByRole('button',{name:'تطبیق همان درخواست خروجی',exact:true}).waitFor();
  await owner.unroute(exportPattern);
  const exportRetry=writeResponse(owner,'/learning/transfer/export');
  await exportSection.getByRole('button',{name:'تطبیق همان درخواست خروجی',exact:true}).click();
  const reconciledExport=await exportRetry,exportJob=(await reconciledExport.json()).job;
  check(reconciledExport.status()===202&&exportJob.id===committedExport.id&&exportJob.status==='succeeded'&&
    reconciledExport.request().postDataJSON().request_key===exportKey&&exportJob.result.items===4,
    'Keyboard export with lost response after commit reconciles the same manifest/job/key through UI');
  await exportSection.getByRole('link',{name:'پیگیری کار خروجی خصوصی',exact:true}).click();
  const output=owner.getByRole('heading',{name:'بستهٔ خروجی آموزشی',exact:true}).locator('..');
  const downloaded=owner.waitForEvent('download');
  await output.getByRole('link',{name:'دریافت خصوصی با مجوز جاری',exact:true}).click();
  const download=await downloaded;assert.equal(await download.failure(),null);
  const exported=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  for(const item of exported.items)assert.deepEqual(item.fields,bundle.items.find(row=>row.kind===item.kind).fields);
  check(exported.schema_version===bundle.schema_version&&exported.items.length===4&&
    exported.items.every(item=>Object.keys(item).sort().join(',')==='fields,key,kind'),
    'Real private download contains exactly the four closed content graphs and no user/progress metadata');
  check((await request(reader,'/artifacts/'+exportJob.output_artifact_id+'/')).status===403,
    'View-only role cannot read generated output metadata');
  const revokedOutput=writeResponse(owner,'/revoke');
  await output.getByRole('button',{name:'بررسی لغو دسترسی فایل',exact:true}).click();
  await output.getByRole('button',{name:'تأیید لغو دسترسی',exact:true}).click();
  check((await revokedOutput).status()===200,'Actual output-file revocation immediately closes its download control');
  expireRevokedOutput(exportJob.output_artifact_id);
  await output.getByRole('button',{name:'بازخوانی فراداده',exact:true}).click();
  await output.getByText('learning-export.json',{exact:true}).waitFor();
  const expiredOutput=await request(owner,'/artifacts/'+exportJob.output_artifact_id+'/');
  assert.equal(expiredOutput.data.artifact.state,'revoked');
  if(expiredOutput.data.artifact.cleanup_supported!==false){
    check(await output.getByRole('button',{name:'پاکسازی فایل منقضی بدون وابستگی',exact:true}).isEnabled(),
      'Revoked output becomes cleanup-eligible through UI after actual expiry without changing revoked state');
    const cleanupQueued=writeResponse(owner,'/cleanup');
    await output.getByRole('button',{name:'پاکسازی فایل منقضی بدون وابستگی',exact:true}).click();
    await output.getByRole('button',{name:'تأیید ایجاد کار پاکسازی',exact:true}).click();
    assert.equal((await cleanupQueued).status(),202);runWorker();
    await output.getByRole('button',{name:'بازخوانی فراداده',exact:true}).click();
    await output.getByText(/فراداده و تاریخچه حفظ شده‌اند/).first().waitFor();
    const cleanedOutput=await request(owner,'/artifacts/'+exportJob.output_artifact_id+'/');
    check(cleanedOutput.data.artifact.state==='expired'&&!!cleanedOutput.data.artifact.purged_at&&
      (await request(owner,'/artifacts/'+exportJob.output_artifact_id+'/download/?purpose=learning_authoring')).status===409&&
      history().digest===before.digest,'Native cleanup finishes with expired metadata, unavailable bytes and unchanged history');
  }else{
    check(await output.getByRole('button',{name:'پاکسازی فایل منقضی بدون وابستگی',exact:true}).isDisabled(),
      'Unsupported native cleanup stays disabled with truthful platform status');
    report.limits.push('Native generated-file cleanup not executed: platform adapter unavailable');
  }
  const exporterContext=await browser.newContext({viewport:{width:320,height:790}}),exporter=await exporterContext.newPage();
  await login(exporter,fixture.users.learning_exporter);await exporter.goto(origin+'/admin-console/content/learning-transfer');
  await exporter.getByRole('heading',{name:'انتقال خصوصی محتوای آموزشی',exact:true}).waitFor();
  check(await exporter.getByRole('navigation',{name:'بخش‌های مدیریت'}).getByRole('link',{name:'کارهای پردازش',exact:true}).count()===1,
    'Export-only actor can reach the scoped job list through actual CMS navigation');
  check(await exporter.getByLabel('فایل بستهٔ آموزشی').count()===0&&
    (await request(exporter,'/learning/transfer/import/',{artifact_id:inputId,request_key:crypto.randomUUID()})).status===403,
    'Export-only MFA actor has no import/upload/editor form and cannot forge import');
  await exporter.getByRole('checkbox').first().check();
  const exporterQueued=writeResponse(exporter,'/learning/transfer/export');
  await exporter.getByRole('button',{name:'ثبت کار خروجی خصوصی',exact:true}).focus();await exporter.keyboard.press('Enter');
  const exporterResponse=await exporterQueued;assert.equal(exporterResponse.status(),202);runWorker();
  await exporter.getByRole('link',{name:'پیگیری کار خروجی خصوصی',exact:true}).click();
  const exporterOutput=exporter.getByRole('heading',{name:'بستهٔ خروجی آموزشی',exact:true}).locator('..');
  const exporterDownload=exporter.waitForEvent('download');
  await exporterOutput.getByRole('link',{name:'دریافت خصوصی با مجوز جاری',exact:true}).click();
  check(await(await exporterDownload).failure()===null,'Export-only actor completes native worker export and real download without edit/upload');
  check(await exporter.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&getComputedStyle(document.querySelector('[dir="rtl"]')).direction==='rtl'),
    'Actual transfer result fits the 320px RTL layout with keyboard controls');
  await exporter.screenshot({path:path.join(out,'transfer-export-only-mobile.png'),fullPage:true});report.screenshots.push('transfer-export-only-mobile.png');
  await owner.setViewportSize({width:320,height:790});
  await owner.screenshot({path:path.join(out,'transfer-output-mobile.png'),fullPage:true});report.screenshots.push('transfer-output-mobile.png');
  const finalTransfer=transferEvidence();
  check(finalTransfer.jobs.find(row=>row[0]==='learning_import')[1]===1&&finalTransfer.jobs.find(row=>row[0]==='learning_export')[1]===2&&
    finalTransfer.audit.find(row=>row[0]==='learning.imported')[1]===1&&finalTransfer.audit.find(row=>row[0]==='learning.exported')[1]===2&&
    finalTransfer.content_counts.every((n,index)=>n===afterImport.content_counts[index])&&history().digest===before.digest,
    'All transfer operations retain exact job/audit counts and unchanged canonical content/history after exports');
  await exporterContext.close();
  check(report.errors.length===0,'No uncaught browser runtime errors');report.status='PASS';
  await readerContext.close();await ownerContext.close();
}catch(e){
  report.status='FAIL';report.failure=String(e.stack||e).slice(0,1900);process.exitCode=1;
  const page=browser?.contexts()[0]?.pages()[0];
  if(page){
    report.failure_fields=await page.locator('fieldset').evaluateAll(rows=>rows.map(f=>({
      legend:f.querySelector('legend')?.textContent,disabled:f.disabled,
      labels:[...f.querySelectorAll('label')].map(l=>l.textContent),
    }))).catch(()=>[]);
    report.failure_alerts=await page.getByRole('alert').allTextContents().catch(()=>[]);
    await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});
  }
}
finally{
  report.completed_at=new Date().toISOString();fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
  if(browser)await browser.close().catch(()=>{});
  for(const proc of processes.reverse())if(proc.exitCode===null)proc.kill();
  if(path.basename(tmp).startsWith('atlas-p13-browser-')&&path.dirname(tmp)===os.tmpdir())fs.rmSync(tmp,{recursive:true,force:true});
  console.log(JSON.stringify({status:report.status,checks:report.checks.length,screenshots:report.screenshots.length,errors:report.errors.length,failure:report.failure||null}));
}})().catch(e=>{console.error(e);process.exitCode=1;});
