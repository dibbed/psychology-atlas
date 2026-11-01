// P09 isolated Chromium journey with synthetic history and real MFA/CSRF.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
let chromium;try{({chromium}=require('playwright'));}catch(e){if(e.code!=='MODULE_NOT_FOUND')throw e;({chromium}=require(path.join(os.tmpdir(),'atlas-p07-browser-tools/node_modules/playwright')));}
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-p09-browser-'));
const out=process.env.CMS_QA_OUTPUT||path.join(root,'qa/p09-browser');fs.mkdirSync(out,{recursive:true});
const py=process.env.CMS_QA_PYTHON||(process.platform==='win32'?path.join(root,'backend/.venv/Scripts/python.exe'):'python');
const origin=process.env.CMS_QA_ORIGIN||'http://127.0.0.1:3000',backend=process.env.CMS_QA_API_ORIGIN||'http://127.0.0.1:8000';
const env={...process.env,CMS_QA_PHASE:'p09',SQLITE_PATH:path.join(tmp,'cms-journey.sqlite3'),NEXT_PUBLIC_API_URL:backend+'/api',CSRF_TRUSTED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P09',status:'RUNNING',checks:[],screenshots:[],errors:[],limits:['Synthetic MFA, not local real Owner','No P16 publication','Synthetic citations only','Local HTTP']};const procs=[];let browser;
function check(v,label){assert(v,label);report.checks.push(label);}
function start(cmd,args,cwd,name){const f=fs.openSync(path.join(tmp,name+'.log'),'a');const p=spawn(cmd,args,{cwd,env,windowsHide:true,stdio:['ignore',f,f]});fs.closeSync(f);procs.push(p);return p;}
async function ready(url,p){for(let i=0;i<100;i++){assert(p.exitCode===null,'Owned service died');try{if((await fetch(url,{signal:AbortSignal.timeout(1400)})).status<500)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error('Service readiness timeout');}
async function login(page,user){await page.goto(origin+'/admin-console');await page.getByLabel('نام کاربری',{exact:true}).fill(user.username);await page.getByLabel('گذرواژه',{exact:true}).fill(user.password);await page.getByRole('button',{name:'ادامه با گذرواژه'}).click();await page.getByLabel('روش تأیید').selectOption('recovery');await page.getByLabel('کد تأیید',{exact:true}).fill(user.tokens[0]);await page.getByRole('button',{name:'تأیید و ورود'}).click();await page.getByRole('button',{name:'خروج',exact:true}).waitFor();}
async function query(page,url){return page.evaluate(async u=>{const r=await fetch('/api/admin'+u);return{status:r.status,data:await r.json()};},url);}
async function shot(page,n){await page.screenshot({path:path.join(out,n+'.png'),fullPage:true});report.screenshots.push(n+'.png');}
(async()=>{try{
const f=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
check(!!f.p09&&!!f.users.owner,'Guarded NON-SCIENTIFIC history fixture');
const dj=start(py,['manage.py','runserver','127.0.0.1:'+new URL(backend).port,'--noreload'],path.join(root,'backend'),'django');await ready(backend+'/api/admin/auth/csrf/',dj);
const nx=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-p',new URL(origin).port,'-H','127.0.0.1'],path.join(root,'frontend'),'next');await ready(origin+'/admin-console',nx);
browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
const ctx=await browser.newContext({viewport:{width:1280,height:860}}),page=await ctx.newPage();page.on('pageerror',e=>report.errors.push(e.name));await login(page,f.users.owner);
check(true,'Real session plus synthetic MFA');
const kinds=await query(page,'/content/schema/');check(kinds.status===200&&kinds.data.kinds.length>=68,'P07–P09 kinds remain scoped to Owner');check(kinds.data.kinds.filter(x=>x.domain==='history').length===34,'All 34 P09 kinds mapped');
const timeline=await query(page,'/content/history/chronology/');check(timeline.status===200&&timeline.data.count===2,'Real chronology reader with 2 rows');
const undated=timeline.data.results.find(x=>x.id===f.p09.unknown);check(undated.date_precision==='unknown'&&undated.exact_date===null&&undated.citation_debt,'Unknown date and missing source not invented');
const debt=await query(page,'/content/history/citation-debt/?kind=timeline-event');check(debt.status===200&&debt.data.count===1&&debt.data.results.every(x=>!x.auto_approval),'Legacy source debt stays unreviewed');
await page.goto(origin+'/admin-console/content/chronology');await page.getByRole('heading',{name:'زمان‌بندی و ارجاعات تاریخ روان‌شناسی'}).waitFor();await shot(page,'p09-chronology-desktop');
await page.setViewportSize({width:320,height:760});await page.reload();await page.getByRole('heading',{name:'زمان‌بندی و ارجاعات تاریخ روان‌شناسی'}).waitFor();check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'320px chronology has no document overflow');await shot(page,'p09-chronology-mobile');
await page.goto(origin+'/admin-console/content/psychologist/new');await page.locator('input[name=slug]').fill('p09-browser-draft-non-scientific');await page.locator('input[name=name_en]').fill('P09 NON-SCIENTIFIC candidate person');await page.getByRole('button',{name:'ذخیرهٔ پیشنهاد'}).click();await page.waitForURL(/\/admin-console\/content\/psychologist\/[0-9a-f-]+/);
const id=page.url().split('/').pop(),record=await query(page,'/content/psychologist/'+id+'/');check(record.status===200&&record.data.canonical_pk===null&&record.data.revision_status==='draft','Psychologist edit journey creates private draft only');await shot(page,'p09-person-draft');
const limited=await browser.newContext({viewport:{width:390,height:760}}),scoped=await limited.newPage();await login(scoped,f.users.scoped);
check((await query(scoped,'/content/history/chronology/')).status===403,'No History reader capability blocks chronology');check((await query(scoped,'/content/history/citation-debt/?kind=psychologist')).status===403,'Citation debt is scoped');check((await query(scoped,'/content/schema/')).data.kinds.every(x=>x.domain!=='history'),'History schema hidden');
check(report.errors.length===0,'No browser runtime error');await limited.close();await ctx.close();report.status='PASS';
}catch(e){report.status='FAIL';report.failure=String(e?.message||e).slice(0,700);process.exitCode=1;}
finally{report.completed_at=new Date().toISOString();fs.writeFileSync(path.join(root,'docs/v1.0-p09-browser-report.json'),JSON.stringify(report,null,2)+'\n');fs.writeFileSync(path.join(out,'p09-browser-report.json'),JSON.stringify(report,null,2)+'\n');for(const p of procs){try{p.kill()}catch{}}if(browser)await browser.close().catch(()=>{});try{fs.rmSync(tmp,{recursive:true,force:true});}catch{}console.log(JSON.stringify({status:report.status,checks:report.checks.length,screenshots:report.screenshots.length,errors:report.errors.length,failure:report.failure||null}));}
})();