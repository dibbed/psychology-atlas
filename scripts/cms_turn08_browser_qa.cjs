// Turn 08 isolated Next production build + real Chromium, exact private preview.
// Only owned loopback servers, disposable SQLite, and an isolated frontend copy.
"use strict";
const fs=require("node:fs"),os=require("node:os"),path=require("node:path"),assert=require("node:assert/strict");
const {spawn,execFileSync,spawnSync}=require("node:child_process");
const net=require("node:net");
let chromium;
try { ({chromium}=require("playwright")); }
catch(e) { if(e.code!=="MODULE_NOT_FOUND")throw e; ({chromium}=require(path.join(os.tmpdir(),"atlas-p07-browser-tools/node_modules/playwright"))); }
const root=path.resolve(__dirname,".."),realFront=path.join(root,"frontend");
const temp=fs.mkdtempSync(path.join(os.tmpdir(),"atlas-p14-browser-turn08-"));
const out=process.env.CMS_QA_OUTPUT||path.join(temp,"evidence");
fs.mkdirSync(out,{recursive:true});
const py=path.join(root,"backend",".venv","Scripts","python.exe");
const isolatedFront=path.join(temp,"frontend");
let origin,api,env,browser,children=[];
const report={kind:"TURN08_CHROMIUM_ISOLATED",status:"INCOMPLETE",checks:[],screenshots:[],errors:[],
  backend:"real Django on guarded disposable SQLite",build:"isolated Next webpack production",
  public_apply:false,scientific_rights_approved:false,canonical_db_opened:false};
function check(actual,label){assert(actual,label);report.checks.push(label);}
function exec(executable,args,cwd,timeout=240000) {
  const p=spawnSync(executable,args,{cwd,env,encoding:"utf8",windowsHide:true,timeout,maxBuffer:4*1024*1024});
  if(p.status!==0)throw new Error(executable+" exit="+p.status+"\n"+(p.stderr||"").slice(-2000)+"\n"+(p.stdout||"").slice(-2000));
  return p.stdout||"";
}
function run(exe,args,cwd,name){
  const stream=fs.openSync(path.join(out,name+".log"),"a");
  const proc=spawn(exe,args,{cwd,env,windowsHide:true,stdio:["ignore",stream,stream]});
  fs.closeSync(stream);children.push(proc);return proc;
}
async function freePort(){
  const server=net.createServer();
  await new Promise((resolve,reject)=>{server.once("error",reject);server.listen(0,"127.0.0.1",resolve);});
  const port=server.address().port;await new Promise(done=>server.close(done));return port;
}
async function ready(url,child) {
  for(let i=0;i<140;i++){
    assert(child.exitCode===null,"Owned server exited before readiness");
    try { const r=await fetch(url,{signal:AbortSignal.timeout(1300)});if(r.status<500)return; }catch{}
    await new Promise(done=>setTimeout(done,350));
  }
  throw Error("Loopback service readiness timeout "+url);
}
async function login(page,user) {
  await page.goto(origin+"/admin-console");
  await page.getByLabel("نام کاربری",{exact:true}).fill(user.username);
  await page.getByLabel("گذرواژه",{exact:true}).fill(user.password);
  await page.getByRole("button",{name:"ادامه با گذرواژه"}).click();
  await page.getByLabel("روش تأیید").selectOption("recovery");
  await page.getByLabel("کد تأیید",{exact:true}).fill(user.tokens[0]);
  await page.getByRole("button",{name:"تأیید و ورود",exact:true}).click();
  await page.getByRole("button",{name:"خروج",exact:true}).waitFor();
}
async function getPreview(page,dossierId){
  return page.evaluate(async id=>{
    const r=await fetch("/api/admin/publication/preparations/"+id+"/candidate-preview/",{cache:"no-store"});
    return {status:r.status,body:await r.json(),cache:r.headers.get("Cache-Control")};
  },dossierId);
}
(async()=>{
  try {
    const [apiPort,frontPort]=await Promise.all([freePort(),freePort()]);
    api="http://127.0.0.1:"+apiPort; origin="http://127.0.0.1:"+frontPort;
    env={...process.env,DB_ENGINE:"sqlite",DEBUG:"1",
      SQLITE_PATH:path.join(temp,"cms-journey.sqlite3"),
      SQLITE_TEST_PATH:path.join(temp,"tests.sqlite3"),CMS_ARTIFACT_ROOT:path.join(temp,"private"),
      CMS_QA_PHASE:"p14",NEXT_PUBLIC_API_URL:api+"/api",CSRF_TRUSTED_ORIGINS:origin,
      CORS_ALLOWED_ORIGINS:origin,NEXT_TELEMETRY_DISABLED:"1"};
    check(!fs.existsSync(env.SQLITE_PATH),"Fresh guarded synthetic DB only");
    const excluded=new Set(["node_modules",".next",".git",".turbo","tsconfig.tsbuildinfo"]);
    fs.cpSync(realFront,isolatedFront,{recursive:true,filter:(src)=>{
      const relative=path.relative(realFront,src).split(path.sep);
      return !relative.some(segment=>excluded.has(segment));
    }});
    fs.symlinkSync(path.join(realFront,"node_modules"),path.join(isolatedFront,"node_modules"),"junction");
    const next=path.join(isolatedFront,"node_modules","next","dist","bin","next");
    exec(process.execPath,[next,"build","--webpack"],isolatedFront,540000);
    check(fs.existsSync(path.join(isolatedFront,".next","BUILD_ID")),
      "Isolated production Webpack build succeeded without touching original next-env.d.ts");
    const fixture=JSON.parse(exec(py,[path.join(root,"scripts","cms_browser_fixture.py")],path.join(root,"backend"),180000));
    const django=run(py,["manage.py","runserver","127.0.0.1:"+apiPort,"--noreload"],path.join(root,"backend"),"django");
    await ready(api+"/api/admin/auth/csrf/",django);
    const site=run(process.execPath,[next,"start","-H","127.0.0.1","-p",String(frontPort)],isolatedFront,"next");
    await ready(origin+"/admin-console",site);
    browser=await chromium.launch({headless:true,...(process.platform==="win32"?{channel:"chrome"}:{})});
    const ctx=await browser.newContext({viewport:{width:1280,height:860}});
    const page=await ctx.newPage();page.setDefaultTimeout(20000);
    page.on("pageerror",err=>report.errors.push(err.message));
    await login(page,fixture.users.owner);
    check(true,"Real owner MFA login through same-origin proxy");
    await page.goto(origin+"/admin-console/publication-preflight");
    await page.getByRole("heading",{name:"صف انتشار، فقط بررسی مقدماتی"}).waitFor();
    await page.getByLabel("حوزهٔ مجاز").selectOption("brain");
    const entry=page.locator("li.card.stack").filter({hasText:"brain-anatomical-alias"}).first();
    await entry.getByRole("checkbox").check();
    await page.getByRole("button",{name:"ثبت بستهٔ بازبینی بدون انتشار"}).click();
    await page.getByRole("button",{name:"بررسی وضعیت فعلی بسته"}).click();
    await page.getByRole("button",{name:"ثبت پروندهٔ آماده‌سازی بدون انتشار"}).click();
    await page.getByRole("button",{name:"پیش‌نمایش خصوصی دقیق همین کاندیدا"}).click();
    const region=page.getByRole("region",{name:"پیش‌نمایش خصوصی کاندیدای منتخب"});
    await region.waitFor();
    check(await region.getByText("صرفاً خصوصی",{exact:false}).count()>0,
      "Private candidate preview rendered in Persian UI");
    check(!((await region.innerText()).includes("P16 PRIVATE SYNTHETIC SECRET")),
      "Private alias text not leaked through limited candidate projection");
    const listing=await page.evaluate(async()=>{
      const r=await fetch("/api/admin/publication/preparations/?domain=brain");
      return await r.json();
    });
    check(listing.count>0,"Dossier receipt appears under authorized actor");
    const id=listing.results[0].id;
    const exact=await getPreview(page,id);
    check(exact.status===200&&exact.body.snapshot_current===true,"Exact version-bound preview GET 200");
    check(exact.body.items.length===1&&exact.body.items[0].kind==="brain-anatomical-alias",
      "Chosen candidate kind/identity preserved");
    check(exact.body.public_projection.payload===null&&exact.body.public_projection.available===false,
      "Public projection remains unavailable without science and rights");
    check(exact.cache==="no-store","Private candidate API has no-store response");
    fs.mkdirSync(out,{recursive:true});
    await page.screenshot({path:path.join(out,"turn08-candidate-1280.png"),fullPage:true});
    report.screenshots.push("turn08-candidate-1280.png");
    await page.setViewportSize({width:320,height:820});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),
      "320px RTL candidate preview has no horizontal overflow");
    check(await region.isVisible(),"Candidate preview persists on mobile viewport");
    await page.getByRole("button",{name:"پیش‌نمایش خصوصی دقیق همین کاندیدا"}).focus();
    check(await page.getByRole("button",{name:"پیش‌نمایش خصوصی دقیق همین کاندیدا"}).evaluate(el=>el===document.activeElement),
      "Candidate preview control is keyboard focusable");
    await page.screenshot({path:path.join(out,"turn08-candidate-320.png"),fullPage:true});
    report.screenshots.push("turn08-candidate-320.png");
    check(report.errors.length===0,"Zero Chromium JS runtime errors");
    report.status="PASS";
  } catch(e) {
    report.status="FAIL";report.failure=String(e.stack||e);
    process.exitCode=1;
  } finally {
    if(browser)await browser.close().catch(()=>{});
    for(const child of children.reverse())if(child.exitCode===null)child.kill();
    const file=path.join(out,"report.json");
    fs.writeFileSync(file,JSON.stringify(report,null,2)+"\n");
    console.log(JSON.stringify({status:report.status,checks:report.checks.length,
      screenshots:report.screenshots.length,errors:report.errors.length,
      failure:report.failure||null,report:file,canonical_db_opened:false}));
    if(report.status!=="PASS")console.error(report.failure);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
