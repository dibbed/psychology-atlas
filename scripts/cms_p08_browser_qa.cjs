// P08 disposable production-browser test. No persistent DB or real credentials.
const assert=require('node:assert/strict'), fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,execFileSync}=require('node:child_process');
let chromium;try{({chromium}=require('playwright'));}catch(e){if(e.code!=='MODULE_NOT_FOUND')throw e;({chromium}=require(path.join(os.tmpdir(),'atlas-p07-browser-tools/node_modules/playwright')));}
const root=path.resolve(__dirname,'..'), temp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-p08-browser-'));
const out=process.env.CMS_QA_OUTPUT||path.join(root,'qa/p08-browser');
fs.mkdirSync(out,{recursive:true});
const py=process.env.CMS_QA_PYTHON||(process.platform==='win32'?path.join(root,'backend/.venv/Scripts/python.exe'):'python');
const origin=process.env.CMS_QA_ORIGIN||'http://127.0.0.1:3000';
const builtRewrites=JSON.parse(fs.readFileSync(path.join(root,'frontend/.next/routes-manifest.json'),'utf8')).rewrites.afterFiles;
const bakedApi=builtRewrites.find(rule=>rule.source==='/api/admin/:path*');
assert(bakedApi,'Production Next build has no CMS API rewrite');
const expectedApiOrigin=new URL(bakedApi.destination).origin;
const apiOrigin=process.env.CMS_QA_API_ORIGIN||expectedApiOrigin;
assert(apiOrigin===expectedApiOrigin&&new URL(apiOrigin).hostname==='127.0.0.1',
  'Backend origin must match production build loopback API rewrite');
const env={...process.env,CMS_QA_PHASE:'p08',SQLITE_PATH:path.join(temp,'cms-journey.sqlite3'),NEXT_PUBLIC_API_URL:apiOrigin+'/api',CSRF_TRUSTED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P08',status:'RUNNING',checks:[],screenshots:[],errors:[],limits:['Synthetic MFA fixture, not enrolled local owner','No P16 canonical publication','Local HTTP, no production release']};
const procs=[];let browser;
function check(ok,label){assert(ok,label);report.checks.push(label);}
function start(command,args,cwd,label){const log=fs.openSync(path.join(temp,label+'.log'),'a');const p=spawn(command,args,{cwd,env,windowsHide:true,stdio:['ignore',log,log]});fs.closeSync(log);procs.push(p);return p;}
async function ready(url,p){for(let i=0;i<100;i++){assert(p.exitCode===null,'Owned service exited');try{if((await fetch(url,{signal:AbortSignal.timeout(1400)})).status<500)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error('Service readiness timeout: '+url);}
async function login(page,user){await page.goto(origin+'/admin-console');await page.getByLabel('نام کاربری',{exact:true}).fill(user.username);await page.getByLabel('گذرواژه',{exact:true}).fill(user.password);await page.getByRole('button',{name:'ادامه با گذرواژه'}).click();await page.getByLabel('روش تأیید').selectOption('recovery');await page.getByLabel('کد تأیید',{exact:true}).fill(user.tokens[0]);await page.getByRole('button',{name:'تأیید و ورود'}).click();await page.getByRole('button',{name:'خروج',exact:true}).waitFor();}
async function get(page,route){return page.evaluate(async route=>{const r=await fetch('/api/admin'+route);return{status:r.status,data:await r.json()}},route);}
async function post(page,route,data){return page.evaluate(async({route,data})=>{const csrf=await fetch('/api/admin/auth/csrf/').then(r=>r.json());const r=await fetch('/api/admin'+route,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf.csrf_token},body:JSON.stringify(data)});return{status:r.status,data:await r.json()};},{route,data});}
async function shot(page,name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});report.screenshots.push(name+'.png');}
(async()=>{try{
const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:150000}));
check(!!fixture.p08&&!!fixture.users.owner,'Guarded isolated P08 fixture seeded');
const django=start(py,['manage.py','runserver','127.0.0.1:'+new URL(apiOrigin).port,'--noreload'],path.join(root,'backend'),'backend');
await ready(apiOrigin+'/api/admin/auth/csrf/',django);
const next=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-p',new URL(origin).port,'-H','127.0.0.1'],path.join(root,'frontend'),'frontend');
await ready(origin+'/admin-console',next);
browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});const context=await browser.newContext({viewport:{width:1280,height:900}});const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.name));
await login(page,fixture.users.owner);check(true,'Owner session with real MFA and CSRF');
const schema=await get(page,'/content/schema/');check(schema.status===200&&schema.data.kinds.filter(k=>['core','dsm','therapy'].includes(k.domain)).length===34,'All 34 P07/P08 typed kinds available to Owner');check(schema.data.kinds.filter(x=>x.domain==='therapy').length===17,'All 17 P08 kinds are visible');
await page.goto(origin+'/admin-console/content/technique/new');
await page.locator('input[name=slug]').fill('p08-browser-non-scientific');
await page.locator('input[name=name_en]').fill('P08 NON-SCIENTIFIC technique');
await page.getByRole('button',{name:'ذخیرهٔ پیشنهاد'}).click();await page.waitForURL(/\/admin-console\/content\/technique\/[0-9a-f-]+/);
const id=page.url().split('/').pop(),draft=await get(page,'/content/technique/'+id+'/');
check(draft.status===200&&draft.data.canonical_pk===null&&draft.data.revision_status==='draft','Technique editor creates private proposal');
await page.getByRole('button',{name:'پیش‌نمایش و اختلاف'}).click();await page.getByRole('button',{name:'اعتبارسنجی پیشنهاد در سرور'}).click();await page.getByText('انتشار canonical در این مرحله در دسترس نیست',{exact:false}).first().waitFor();
check((await get(page,'/content/technique/'+id+'/')).data.canonical_pk===null,'Preview never promotes technique');
await shot(page,'p08-technique-desktop');
const link=await post(page,'/content/therapy-technique-source/',{reason:'DRAFT_CREATION',payload:{relationship:fixture.p08.link,source:fixture.p08.source,note:'Synthetic reference, no efficacy claim'}});
check(link.status===201&&link.data.canonical_pk===null,'Source-linked relation remains unpublished');
const compare=await get(page,'/content/therapy/public-compare-preview/?left='+fixture.p08.therapy+'&right='+fixture.p08.other);
check(compare.status===200&&compare.data.publication_available===false,'Existing public Therapy comparison is available, read-only');
await page.goto(origin+'/admin-console/content/therapy-compare');await page.getByRole('heading',{name:'مقایسهٔ واقعی درمان‌های منتشرشده'}).waitFor();await shot(page,'p08-compare-desktop');
await page.setViewportSize({width:320,height:760});await page.reload();await page.getByRole('heading',{name:'مقایسهٔ واقعی درمان‌های منتشرشده'}).waitFor();check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'320px therapy compare has no overflow');await shot(page,'p08-compare-mobile');
const limited=await browser.newContext({viewport:{width:390,height:760}}),scoped=await limited.newPage();await login(scoped,fixture.users.scoped);
check((await get(scoped,'/content/therapy/')).status===403,'Scoped non-therapy staff cannot read content');check((await get(scoped,'/content/therapy/public-compare-preview/?left='+fixture.p08.therapy+'&right='+fixture.p08.other)).status===403,'Private comparison rejects scoped staff');check((await get(scoped,'/content/schema/')).data.kinds.filter(x=>x.domain==='therapy').length===0,'Schema denies 17 therapy kinds');
check(report.errors.length===0,'No uncaught page errors');report.status='PASS';await limited.close();await context.close();
}catch(e){report.status='FAIL';report.failure=String(e?.message||e).slice(0,750);process.exitCode=1;}
finally{fs.writeFileSync(path.join(root,'docs/v1.0-p08-browser-report.json'),JSON.stringify(report,null,2)+'\n');fs.writeFileSync(path.join(out,'p08-browser-report.json'),JSON.stringify(report,null,2)+'\n');for(const p of procs){try{p.kill()}catch{}}if(browser)await browser.close().catch(()=>{});try{fs.rmSync(temp,{recursive:true,force:true});}catch{}console.log(JSON.stringify({status:report.status,checks:report.checks.length,screenshots:report.screenshots.length,errors:report.errors.length,failure:report.failure||null}));}
})();
