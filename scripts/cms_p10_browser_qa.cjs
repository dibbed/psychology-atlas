// P10 actual browser/CSRF/MFA journey against explicitly owned disposable data.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
let chromium;try{({chromium}=require('playwright'));}catch(e){if(e.code!=='MODULE_NOT_FOUND')throw e;({chromium}=require(path.join(os.tmpdir(),'atlas-p07-browser-tools/node_modules/playwright')));}
const root=path.resolve(__dirname,'..');
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-p10-browser-'));
const out=process.env.CMS_QA_OUTPUT||path.join(root,'qa/p10-browser');fs.mkdirSync(out,{recursive:true});
const py=process.env.CMS_QA_PYTHON||(process.platform==='win32'?path.join(root,'backend/.venv/Scripts/python.exe'):'python');
const origin=process.env.CMS_QA_ORIGIN||'http://127.0.0.1:3000',api=process.env.CMS_QA_API_ORIGIN||'http://127.0.0.1:8000';
const env={...process.env,CMS_QA_PHASE:'p10',SQLITE_PATH:path.join(tmp,'cms-journey.sqlite3'),
 NEXT_PUBLIC_API_URL:api+'/api',CSRF_TRUSTED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P10',status:'RUNNING',checks:[],screenshots:[],errors:[],
 limits:['No real Owner login','Synthetic scientific content and MFA','Local HTTP only','No P16 publication']};
const processes=[];let browser;
const check=(value,label)=>{assert(value,label);report.checks.push(label);};
function start(exe,args,cwd,name){const file=fs.openSync(path.join(tmp,name+'.log'),'a');const p=spawn(exe,args,{cwd,env,windowsHide:true,stdio:['ignore',file,file]});fs.closeSync(file);processes.push(p);return p;}
async function ready(url,p){for(let i=0;i<100;i++){assert(p.exitCode===null,'Owned server failed');try{if((await fetch(url,{signal:AbortSignal.timeout(1400)})).status<500)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error('P10 owned server readiness timeout');}
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
async function query(page,target){
 return page.evaluate(async route=>{const r=await fetch('/api/admin'+route);return {status:r.status,data:await r.json()};},target);
}
async function shot(page,name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});report.screenshots.push(name+'.png');}
(async()=>{try{
 const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
 check(!!fixture.p10&&!!fixture.users.owner,'Guarded P10 NON-SCIENTIFIC fixture');
 const dj=start(py,['manage.py','runserver','127.0.0.1:'+new URL(api).port,'--noreload'],path.join(root,'backend'),'django');
 await ready(api+'/api/admin/auth/csrf/',dj);
 const nx=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-p',new URL(origin).port,'-H','127.0.0.1'],path.join(root,'frontend'),'next');
 await ready(origin+'/admin-console',nx);
 browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
 const owner=await browser.newContext({viewport:{width:1280,height:860}}),page=await owner.newPage();
 page.on('pageerror',e=>report.errors.push(String(e)));
 await login(page,fixture.users.owner);check(true,'Real isolated MFA session and CSRF');
 const schema=await query(page,'/content/schema/');
 check(schema.status===200&&schema.data.kinds.filter(x=>x.domain==='brain').length===13,'All 13 P10 models available to Owner');
 const tree=await query(page,'/content/brain/tree/');
 check(tree.status===200&&tree.data.count===3&&!tree.data.publication_available,'Private Brain tree has three synthetic nodes');
 const left=tree.data.results.find(x=>x.id===fixture.p10.left);
 check(left.parent_id===fixture.p10.root,'Canonical parent anchored');
 const bad=await query(page,`/content/brain/tree/?child=${fixture.p10.left}&parent=${fixture.p10.right}`);
 check(bad.status===200&&bad.data.after.blockers.includes('LATERALITY_CONFLICT'),'Wrong laterality blocked');
 const cyc=await query(page,`/content/brain/tree/?child=${fixture.p10.root}&parent=${fixture.p10.left}`);
 check(cyc.status===200&&cyc.data.after.blockers.includes('CYCLE'),'Cycle blocked without mutation');
 const after=await query(page,'/content/brain/tree/');
 check(after.data.results.find(x=>x.id===fixture.p10.left).parent_id===fixture.p10.root,'No canonical tree mutation');
 await page.goto(origin+'/admin-console/content/brain');
 await page.getByRole('heading',{name:'درخت آناتومی و پیش‌نمایش جابه‌جایی والد'}).waitFor();
 await page.getByLabel('شناسهٔ ناحیهٔ فرزند').fill(String(fixture.p10.left));
 await page.getByLabel('شناسهٔ والد پیشنهادی').fill(String(fixture.p10.right));
 await page.getByRole('button',{name:'محاسبهٔ اثر بدون ذخیره'}).click();
 await page.getByText('تغییر پیشنهادی نامعتبر است',{exact:false}).waitFor();
 check(true,'Real UI before/after impact check');
 await shot(page,'p10-brain-tree-desktop');
 await page.setViewportSize({width:320,height:760});await page.reload();
 await page.getByRole('heading',{name:'درخت آناتومی و پیش‌نمایش جابه‌جایی والد'}).waitFor();
 check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'320px Brain tree has no document overflow');
 await shot(page,'p10-brain-tree-mobile');
 await page.goto(origin+'/admin-console/content/brain-network-membership/new');
 await page.getByRole('heading').first().waitFor();
 check((await query(page,'/content/options/brain-network-membership/')).status===200,'Empty membership remains navigable');
 await shot(page,'p10-empty-membership-editor');
 const scoped=await browser.newContext({viewport:{width:390,height:760}}),limited=await scoped.newPage();
 await login(limited,fixture.users.scoped);
 check((await query(limited,'/content/brain/tree/')).status===200,'Brain viewer can view canonical tree');
 check((await query(limited,`/content/brain/tree/?child=${fixture.p10.left}&parent=${fixture.p10.root}`)).status===403,'View-only cannot preview proposed parent');
 check(report.errors.length===0,'No unhandled browser errors');
 report.status='PASS';await scoped.close();await owner.close();
}catch(e){report.status='FAIL';report.failure=String(e?.stack||e?.message||e).slice(0,1000);process.exitCode=1;}
finally{
 report.completed_at=new Date().toISOString();
 fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
 if(browser)await browser.close().catch(()=>{});
 for(const proc of processes.reverse()){if(proc.exitCode===null)proc.kill();}
 if(path.basename(tmp).startsWith('atlas-p10-browser-')&&path.dirname(tmp)===os.tmpdir())fs.rmSync(tmp,{recursive:true,force:true});
 console.log(JSON.stringify({status:report.status,checks:report.checks.length,screenshots:report.screenshots.length,errors:report.errors.length,failure:report.failure||null}));
}}
)().catch(e=>{console.error(e);process.exitCode=1;});
