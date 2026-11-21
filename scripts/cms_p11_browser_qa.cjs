// P11 metadata-only browser journey against disposable synthetic fixtures only.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
let chromium;try{({chromium}=require('playwright'));}catch(e){if(e.code!=='MODULE_NOT_FOUND')throw e;({chromium}=require(path.join(os.tmpdir(),'atlas-p07-browser-tools/node_modules/playwright')));}
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-p11-browser-'));
const out=process.env.CMS_QA_OUTPUT||path.join(root,'qa/p11-browser');fs.mkdirSync(out,{recursive:true});
const py=process.env.CMS_QA_PYTHON||(process.platform==='win32'?path.join(root,'backend/.venv/Scripts/python.exe'):'python');
const origin=process.env.CMS_QA_ORIGIN||'http://127.0.0.1:3000',api=process.env.CMS_QA_API_ORIGIN||'http://127.0.0.1:8000';
const env={...process.env,CMS_QA_PHASE:'p11',SQLITE_PATH:path.join(tmp,'cms-journey.sqlite3'),
 NEXT_PUBLIC_API_URL:api+'/api',CSRF_TRUSTED_ORIGINS:origin,DEBUG:'1'};
const report={stage:'P11',status:'RUNNING',checks:[],screenshots:[],errors:[],
 limits:['No real Owner login','Only isolated synthetic identities','No licensed test items or scoring','No P16 publication']};
const processes=[];let browser;
function check(ok,description){assert(ok,description);report.checks.push(description);}
function start(exe,args,cwd,name){const file=fs.openSync(path.join(tmp,name+'.log'),'a');const p=spawn(exe,args,{cwd,env,windowsHide:true,stdio:['ignore',file,file]});fs.closeSync(file);processes.push(p);return p;}
async function ready(url,proc){for(let i=0;i<100;i++){assert(proc.exitCode===null,'Owned test server stopped');try{if((await fetch(url,{signal:AbortSignal.timeout(1400)})).status<500)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error('P11 server not ready');}
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
async function query(page,route){return page.evaluate(async r=>{
 const response=await fetch('/api/admin'+r);return {status:response.status,data:await response.json()};
},route);}
async function shot(page,name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});report.screenshots.push(name+'.png');}
(async()=>{try{
 const f=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{
 cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
 check(!!f.p11&&!!f.users.owner&&!!f.users.assessment_reader,'P11 guarded synthetic fixture including scoped MFA reader');
 const django=start(py,['manage.py','runserver','127.0.0.1:'+new URL(api).port,'--noreload'],path.join(root,'backend'),'django');
 await ready(api+'/api/admin/auth/csrf/',django);
 const next=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-p',new URL(origin).port,'-H','127.0.0.1'],path.join(root,'frontend'),'next');
 await ready(origin+'/admin-console',next);
 browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
 const owner=await browser.newContext({viewport:{width:1280,height:850}}),page=await owner.newPage();
 page.on('pageerror',err=>report.errors.push(String(err)));
 await login(page,f.users.owner);
 check(true,'Real disposable owner MFA and CSRF');
 const schemas=await query(page,'/content/schema/');
 const items=schemas.data.kinds.filter(x=>x.domain==='assessment');
 check(schemas.status===200&&items.length===9,'All nine typed Assessment models available');
 const forbidden=new Set(['items','test_items','questionnaire_text','item_bank','scoring_key',
   'scoring_rules','manual_text','official_translation_text','translation_text']);
 check(items.every(s=>s.fields.every(field=>!forbidden.has(field.name))),'No item, manual or scoring fields in editor');
 const family=await query(page,'/content/assessment-instrument/');
 check(family.status===200&&family.data.count===1,'Synthetic instrument metadata in private editor');
 const version=await query(page,'/content/assessment-version/');
 check(version.status===200&&version.data.count===1,'Unresolved edition remains distinct');
 const forms=await query(page,'/content/assessment-language-form/');
 check(forms.status===200&&forms.data.count===1,'Synthetic form remains separate identity');
 const access=await query(page,'/content/assessment-access/');
 check(access.status===200&&access.data.count===1,'Scoped rights metadata exists without granted rights');
 const form=await query(page,'/content/assessment-language-form/'+f.p11.form_state+'/');
 check(form.status===200&&form.data.field_values?.authorization_status==='unknown','Translation authorization remains UNKNOWN');
 const rights=await query(page,'/content/assessment-access/'+f.p11.access_state+'/');
 check(rights.status===200&&rights.data.field_values?.license_status==='unknown','Rights remain UNKNOWN, not free or licensed');
 await page.goto(origin+'/admin-console/content/assessments');
 await page.getByRole('heading',{name:'مدیریت متادیتای ابزار، منبع و مجوز'}).waitFor();
 await shot(page,'p11-assessments-desktop');
 check(await page.getByRole('link',{name:/نسخه و ویرایش/}).count()>=1,'Version editor linked by visible UI');
 await page.setViewportSize({width:320,height:780});await page.reload();
 await page.getByRole('heading',{name:'مدیریت متادیتای ابزار، منبع و مجوز'}).waitFor();
 check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'320px Assessment page has no overflow');
 await shot(page,'p11-assessments-mobile');
 await page.goto(origin+'/admin-console/content/assessment-instrument/'+f.p11.family_state);
 await page.getByRole('heading').first().waitFor();
 await shot(page,'p11-unreviewed-instrument');
 const scope=await browser.newContext({viewport:{width:390,height:790}}),viewer=await scope.newPage();
 await login(viewer,f.users.assessment_reader);
 const viewerSchema=await query(viewer,'/content/schema/');
 check(viewerSchema.status===200&&viewerSchema.data.kinds.length===9,'Assessment-only reader sees exactly nine schemas');
 check((await query(viewer,'/content/assessment-instrument/')).status===200,'Assessment-only reader can read instrument');
 check((await query(viewer,'/content/brain/tree/')).status===403,'Assessment reader cannot inspect Brain');
 const creation=await viewer.evaluate(async()=>{
 const r=await fetch('/api/admin/content/assessment-instrument/',{
  method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({payload:{}})});
 return r.status;
 });
 check(creation===403,'Assessment-only reader cannot mutate');
 check(report.errors.length===0,'No unhandled browser runtime errors');
 report.status='PASS';await scope.close();await owner.close();
}catch(e){report.status='FAIL';report.failure=String(e?.stack||e?.message||e).slice(0,1600);process.exitCode=1;}
finally{
 report.completed_at=new Date().toISOString();
 fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
 if(browser)await browser.close().catch(()=>{});
 for(const p of processes.reverse())if(p.exitCode===null)p.kill();
 if(path.basename(tmp).startsWith('atlas-p11-browser-')&&path.dirname(tmp)===os.tmpdir())fs.rmSync(tmp,{recursive:true,force:true});
 console.log(JSON.stringify({status:report.status,checks:report.checks.length,screenshots:report.screenshots.length,
  errors:report.errors.length,failure:report.failure||null}));
}})().catch(err=>{console.error(err);process.exitCode=1;});
