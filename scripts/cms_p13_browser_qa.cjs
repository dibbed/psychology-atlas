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
  CMS_QA_PHASE:'p13',NEXT_PUBLIC_API_URL:api+'/api',CSRF_TRUSTED_ORIGINS:origin,CORS_ALLOWED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P13',status:'RUNNING',checks:[],screenshots:[],errors:[],
  limits:['Synthetic isolated SQLite only','Quiz metadata/authoring slice; P13 publication, archive and import/export remain incomplete']};
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
  'rows={t:c.execute("SELECT * FROM "+t+" ORDER BY id").fetchall() for t in ["atlas_quizattempt","atlas_quizattemptanswer","atlas_studyactivity"]}',
  'print(json.dumps({"counts":[len(v) for v in rows.values()],"digest":hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}))','c.close()',
].join('\n')],{env,encoding:'utf8'}));}
function writeResponse(page,suffix){return page.waitForResponse(r=>r.url().replace(/\/$/,'').endsWith(suffix)&&
  r.request().method()==='POST'&&!(r.status()>=300&&r.status()<400));}
(async()=>{try{
  const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
  const before=history();check(before.counts.every(n=>n>0),'Existing synthetic quiz answers and learning activity are nonempty');
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
    'Historical inactive Quiz stays locked in UI/API and preserves actual answers/activity');
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
