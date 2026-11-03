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
const report={stage:'P14',status:'RUNNING',checks:[],screenshots:[],errors:[],limits:['Synthetic accounts only','Privacy export/erase and approved retention remain separate gates','No offline owner identity approval or production recovery']};
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
async function login(page,user){page.setDefaultTimeout(20000);page.on('pageerror',error=>report.errors.push(String(error)));await page.goto(origin+'/admin-console');await page.getByLabel('نام کاربری',{exact:true}).fill(user.username);await page.getByLabel('گذرواژه',{exact:true}).fill(user.password);await page.getByRole('button',{name:'ادامه با گذرواژه',exact:true}).click();await page.getByLabel('روش تأیید').selectOption('recovery');await page.getByLabel('کد تأیید',{exact:true}).fill(user.tokens[0]);await page.getByRole('button',{name:'تأیید و ورود',exact:true}).click();await page.getByRole('button',{name:'خروج',exact:true}).waitFor();}
async function openAccount(page,username){await page.goto(origin+'/admin-console/accounts');await page.getByLabel('نام کاربری یا شناسه',{exact:true}).fill(username);await page.getByRole('button',{name:'جست‌وجو',exact:true}).click();await page.locator('li').filter({has:page.getByText(username,{exact:true})}).getByRole('button',{name:'جزئیات مجاز',exact:true}).click();await page.getByRole('heading',{name:'کنترل دسترسی و نشست حساب',exact:true}).waitFor();await page.getByText('فهرست مجوزهای مستقیم',{exact:true}).click();}
async function confirmAccount(page,token){await page.getByLabel('روش تأیید تغییر حساب').selectOption('recovery');await page.getByLabel('کد MFA تغییر حساب',{exact:true}).fill(token);await page.getByRole('button',{name:'اعمال تغییر تأییدشدهٔ حساب',exact:true}).focus();await page.keyboard.press('Enter');}
(async()=>{try{
  const fixture=JSON.parse(execFileSync(py,[path.join(root,'scripts/cms_browser_fixture.py')],{cwd:path.join(root,'backend'),env,encoding:'utf8',timeout:180000}));
  const backend=start(py,['manage.py','runserver','127.0.0.1:'+new URL(api).port,'--noreload'],path.join(root,'backend'),'django');await ready(api+'/api/admin/auth/csrf/',backend);
  // The production bundle uses the same-origin API rewrite compiled for port8000.
  const next=start(process.execPath,[path.join(root,'frontend/node_modules/next/dist/bin/next'),'start','-H','127.0.0.1','-p',new URL(origin).port],path.join(root,'frontend'),'next');await ready(origin+'/admin-console',next);
  browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
  const ownerContext=await browser.newContext({viewport:{width:1280,height:850}}),owner=await ownerContext.newPage();await login(owner,fixture.users.owner);
  const scopedContext=await browser.newContext(),scoped=await scopedContext.newPage();await login(scoped,fixture.users.scoped);
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
