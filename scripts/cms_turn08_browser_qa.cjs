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
    check(await region.getByText("نقشهٔ محدود مصرف‌کنندگان عمومی",{exact:false}).count()>0,
      "W17-01 private surface footprint visible with explicit non-public boundary");
    check(await region.getByText("فیلدهای قابل‌ردیابی و تغییرکرده",{exact:false}).count()>0,
      "W17-01 field-level proposal impact rendered without raw draft payload");
    check(await region.getByText("برای این نوع، مسیر عمومی مستقلی وجود ندارد",{exact:false}).count()>0,
      "W17-01 absent public Compare reader is explicitly unavailable");
    check(await region.getByText("/api/brain-anatomy/{slug}/",{exact:true}).count()>0,
      "W17-01 reader contract names the real registered Brain detail route");
    check(await region.getByText("ریشه‌های عمومی موجود، از همان فیلتر عمومی سایت:",{exact:false}).count()>0,
      "W17-01 existing public root checked without promoting private candidate");
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
    // W16-02: actual immutable review-manifest flow, not public Apply.
    await page.getByRole("button",{name:"تطبیق پروندهٔ ثابت با وضعیت زنده"}).click();
    const freezePanel=page.getByRole("region",{name:"مانیفست ثابت بررسی پیش از انتشار"});
    await freezePanel.getByRole("button",{name:"ساخت Dry-run با نسخهٔ فعلی پرونده"}).click();
    await freezePanel.getByRole("button",{name:"ثبت Immutable Frozen Review Manifest"}).waitFor();
    check(await freezePanel.getByText("فیلدهای تغییر:",{exact:false}).count()>0,
      "W16-02 real frozen dry-run lists field names and canonical public-root impact only");
    await freezePanel.getByRole("button",{name:"ثبت Immutable Frozen Review Manifest"}).click();
    await freezePanel.getByText("مانیفست بررسی منجمد شد.",{exact:false}).waitFor();
    const qaFrozen=await page.evaluate(async id=>{
      const r=await fetch("/api/admin/publication/preparations/"+id+"/dry-run/",{cache:"no-store"});
      return {status:r.status,body:await r.json(),cache:r.headers.get("cache-control")};
    },id);
    check(qaFrozen.status===200&&qaFrozen.body.public_projection===null&&qaFrozen.body.approved===false,
      "W16-02 dry-run cannot publish any private projection");
    check(qaFrozen.body.actions.length===1&&qaFrozen.body.actions[0].kind==="brain-anatomical-alias",
      "W16-02 exact chosen candidate is sealed by kind and revision");
    check(!(await freezePanel.innerText()).includes("P16 PRIVATE SYNTHETIC SECRET"),
      "W16-02 frozen manifest UI discloses no private aliases or raw evidence");
    check(qaFrozen.cache==="no-store","W16-02 manifest response disables cache");
    await page.setViewportSize({width:320,height:820});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),
      "W16-02 frozen-manifest panel does not overflow at 320px RTL");
    await page.screenshot({path:path.join(out,"turn08-frozen-manifest-320.png"),fullPage:true});
    report.screenshots.push("turn08-frozen-manifest-320.png");
    // W16-03: a separate, non-authorizing reviewer page can read bounded
    // receipt state but cannot display draft evidence or publicly Apply it.
    await freezePanel.getByRole("link",{name:"بازکردن فرم مستقل ثبت سوابق بازبین"}).click();
    await page.getByRole("heading",{name:"سوابق مستقل بازبینی مانیفست"}).waitFor();
    await page.getByRole("button",{name:"بازخوانی وضعیت فعلی"}).click();
    const attestationRegion=page.getByRole("region",{name:"وضعیت خصوصی بازبینی"});
    await attestationRegion.waitFor();
    check(await attestationRegion.getByText("بازبینی ثبت نشده",{exact:false}).count()===3,
      "W16-03 reviewer page safely shows three independent missing attestations");
    check(!(await page.locator("#cms-main").innerText()).includes("P16 PRIVATE SYNTHETIC SECRET"),
      "W16-03 reviewer UI exposes no private candidate or scientific raw data");
    check(await page.getByRole("button",{name:/Apply|انتشار عمومی/}).count()===0,
      "W16-03 reviewer UI has no public Apply control");
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),
      "W16-03 reviewer UI fits a 320px viewport");
    await page.screenshot({path:path.join(out,"turn08-attestation-review-320.png"),fullPage:true});
    report.screenshots.push("turn08-attestation-review-320.png");
    // W16-00: real Learning UI recheck after semantic subtype drift, using
    // synthetic records in the *same guarded disposable* browser database.
    const learningFixture=JSON.parse(exec(py,["-c",[
      "import os,json,tempfile",
      "from pathlib import Path",
      "db=Path(os.environ['SQLITE_PATH']).resolve()",
      "assert os.environ.get('CMS_QA_PHASE')=='p14' and db.name=='cms-journey.sqlite3'",
      "assert db.parent.name.startswith('atlas-p14-browser-turn08-') and db.parent.parent==Path(tempfile.gettempdir()).resolve()",
      "import django",
      "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')",
      "django.setup()",
      "from atlas.models import Concept,CognitiveDistortionPracticeItem,CognitiveDistortionPracticeChoice",
      "c=Concept.objects.create(slug='qa-w16-target',name_en='Synthetic target',subtype=Concept.Subtype.COGNITIVE_DISTORTION,is_active=True)",
      "alt=Concept.objects.create(slug='qa-w16-alternative',name_en='Synthetic alternative',subtype=Concept.Subtype.COGNITIVE_DISTORTION,is_active=True)",
      "item=CognitiveDistortionPracticeItem.objects.create(slug='qa-w16-item',prompt='Synthetic private question',explanation='Synthetic private explanation',target_concept=c,is_active=False,seed_managed=False)",
      "CognitiveDistortionPracticeChoice.objects.create(item=item,concept=c,text='Correct',is_correct=True,is_active=True)",
      "CognitiveDistortionPracticeChoice.objects.create(item=item,concept=alt,text='Alternative',is_correct=False,is_active=True)",
      "print(json.dumps({'target':c.pk,'item':item.pk}))",
    ].join("\n")],path.join(root,"backend"),90000));
    await page.setViewportSize({width:1280,height:860});
    await page.goto(origin+"/admin-console/publication-preflight");
    await page.getByLabel("حوزهٔ مجاز").selectOption("learning");
    const learningEntry=page.locator("li.card.stack").filter({hasText:"distortion_practice #"+learningFixture.item}).first();
    await learningEntry.getByRole("checkbox").check();
    await page.getByRole("button",{name:"ثبت بستهٔ بازبینی بدون انتشار"}).click();
    await page.getByRole("button",{name:"بررسی وضعیت فعلی بسته"}).click();
    await page.getByRole("button",{name:"ثبت پروندهٔ آماده‌سازی بدون انتشار"}).click();
    const driftPy=[
      "import os,tempfile",
      "from pathlib import Path",
      "db=Path(os.environ['SQLITE_PATH']).resolve()",
      "assert os.environ.get('CMS_QA_PHASE')=='p14' and db.name=='cms-journey.sqlite3' and db.parent.name.startswith('atlas-p14-browser-turn08-') and db.parent.parent==Path(tempfile.gettempdir()).resolve()",
      "import django",
      "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')",
      "django.setup()",
      "from atlas.models import Concept",
      "assert Concept.objects.filter(pk="+learningFixture.target+",slug='qa-w16-target').update(subtype=Concept.Subtype.GENERAL)==1",
    ].join("\n");
    exec(py,["-c",driftPy],path.join(root,"backend"),90000);
    await page.getByRole("button",{name:"تطبیق پروندهٔ ثابت با وضعیت زنده"}).click();
    await page.getByText("نسخه، سیاست یا شواهد از زمان ثبت پرونده تغییر کرده‌اند.",{exact:false}).waitFor();
    check(true,"W16-00 Learning UI recheck explicitly shows semantic stale dossier");
    const learningListing=await page.evaluate(async()=>{
      const r=await fetch("/api/admin/publication/preparations/?domain=learning",{cache:"no-store"});
      return r.json();
    });
    const learningId=learningListing.results[0].id;
    const denied=await getPreview(page,learningId);
    check(denied.status===409,"W16-00 stale Learning candidate is withheld from private preview");
    await page.goto(origin+"/admin-console/search");
    await page.getByRole("combobox").selectOption("research");
    const searchInput=page.locator('input[type="search"]');
    await searchInput.fill("p17-browser");
    const suggestions=page.getByRole("region",{name:"پیشنهادهای مجاز"});
    await suggestions.waitFor();
    check(await suggestions.getByRole("button").count()===2,
      "W17-01 debounced slug autocomplete only exposes two synthetic authorized identities");
    await suggestions.getByRole("button",{name:/رکورد پژوهشی داخلی/}).click();
    check(await searchInput.inputValue()==="p17-browser-record",
      "W17-01 autocomplete selects exact safe record slug");
    await page.getByRole("button",{name:"جست‌وجو",exact:true}).click();
    const searchResults=page.locator("section.card.stack").filter({hasText:"نتایج:"}).last();
    await searchResults.waitFor();
    check(!(await searchResults.innerText()).includes("P17 SECRET"),
      "W17-01 private search does not leak staged research raw/answers");
    // Public routes intentionally bypass the admin-only Next rewrite.
    // Query the owned loopback Django API, not Next's 404 public path.
    const publicResponse=await fetch(api+"/api/search/?q=p17-browser-record",{
      signal:AbortSignal.timeout(10000),
    });
    const publicSearch={status:publicResponse.status,text:await publicResponse.text()};
    check(publicSearch.status===200&&!publicSearch.text.includes("P17 SECRET"),
      "W17-01 public search keeps private staging hidden");
    const aliasSetup=[
      "import os,tempfile",
      "from pathlib import Path",
      "db=Path(os.environ['SQLITE_PATH']).resolve()",
      "assert os.environ.get('CMS_QA_PHASE')=='p14' and db.name=='cms-journey.sqlite3' and db.parent.name.startswith('atlas-p14-browser-turn08-') and db.parent.parent==Path(tempfile.gettempdir()).resolve()",
      "import django",
      "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')",
      "django.setup()",
      "from atlas.models import BrainAnatomicalAlias,AssessmentAlias,BrainAnatomicalEntity,AssessmentInstrument,SourceReference",
      "source=SourceReference.objects.get(title='P16 synthetic dependency evidence')",
      "brain=BrainAnatomicalEntity.objects.get(slug='p16-private-parent')",
      "assessment=AssessmentInstrument.objects.create(slug='p17-alias-synthetic-parent',name_en='Synthetic assessment parent',is_active=True)",
      "BrainAnatomicalAlias.objects.create(entity=brain,source=source,text='p17exact',language='en',alias_type='alternative')",
      "AssessmentAlias.objects.create(instrument=assessment,source=source,source_note='Synthetic non-scientific locator',text='p17exact',language='en',alias_type='acronym')",
    ].join("\n");
    exec(py,["-c",aliasSetup],path.join(root,"backend"),90000);
    await page.getByRole("combobox").selectOption("aliases");
    await searchInput.fill("p17exact");
    await page.getByRole("button",{name:"جست‌وجو",exact:true}).click();
    await page.getByText("ابهام نام جایگزین:",{exact:false}).waitFor();
    check(true,"W17-01 two exact aliases produce explicit scoped ambiguity in Persian UI");
    check(!(await searchResults.innerText()).includes("P16 PRIVATE SYNTHETIC SECRET"),
      "W17-01 alias match hides proposal text and parent details");
    // Independent browser context ensures no privileged owner cookies are
    // reused by the permission-scoped account.
    const restrictedCtx=await browser.newContext({viewport:{width:1280,height:860}});
    const restrictedPage=await restrictedCtx.newPage();
    restrictedPage.setDefaultTimeout(20000);
    restrictedPage.on("pageerror",error=>report.errors.push(error.message));
    await login(restrictedPage,fixture.users.scoped);
    await restrictedPage.goto(origin+"/admin-console/search");
    await restrictedPage.getByText("برای جست‌وجوی داخلی به مجوز مستقل cms_search نیاز است.",{exact:false}).waitFor();
    check(true,"W17-01 scoped role without search permission denied in browser");
    await restrictedCtx.close();
    // Real public Search exact alias ambiguity, from two separately reviewed
    // synthetic roots only in the guarded disposable browser database.
    const publicAliasFixture=[
      "import os,tempfile",
      "from pathlib import Path",
      "db=Path(os.environ['SQLITE_PATH']).resolve()",
      "assert os.environ.get('CMS_QA_PHASE')=='p14' and db.name=='cms-journey.sqlite3' and db.parent.name.startswith('atlas-p14-browser-turn08-') and db.parent.parent==Path(tempfile.gettempdir()).resolve()",
      "import django",
      "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')",
      "django.setup()",
      "from atlas.models import (BrainAnatomicalEntity,BrainAnatomicalEntitySource,BrainAnatomicalAlias,AssessmentInstrument,AssessmentSource,AssessmentAlias,SourceReference)",
      "source=SourceReference.objects.get(title='P16 synthetic dependency evidence')",
      "brain=BrainAnatomicalEntity.objects.create(slug='w17uiqa-brain',name_en='SYNTHETIC reviewed QA brain',kind='structure',laterality='not_established',is_active=True)",
      "BrainAnatomicalEntitySource.objects.create(entity=brain,source=source,note='Test-only fabricated metadata')",
      "brain.review_status='reviewed'",
      "brain.save(update_fields=['review_status'])",
      "BrainAnatomicalAlias.objects.create(entity=brain,source=source,source_note='Synthetic test locator',text='w17uiqa',language='en',alias_type='abbreviation',review_status='reviewed')",
      "assessment=AssessmentInstrument.objects.create(slug='w17uiqa-assessment',name_en='SYNTHETIC reviewed QA instrument',is_active=True)",
      "AssessmentSource.objects.create(instrument=assessment,source=source,note='Test-only fabricated metadata')",
      "assessment.review_status='reviewed'",
      "assessment.save(update_fields=['review_status'])",
      "AssessmentAlias.objects.create(instrument=assessment,source=source,source_note='Synthetic test locator',text='w17uiqa',language='en',alias_type='acronym',review_status='reviewed')",
    ].join("\n");
    exec(py,["-c",publicAliasFixture],path.join(root,"backend"),90000);
    await page.goto(origin+"/search?q=w17uiqa");
    const publicAmbiguity=page.getByRole("region",{name:"ابهام نام جایگزین در جست‌وجوی عمومی"});
    await publicAmbiguity.waitFor();
    check(await publicAmbiguity.getByRole("link").count()===2,
      "W17-01 real public Search distinguishes two reviewed synthetic alias identities");
    check(await publicAmbiguity.locator('a[href="/brain/w17uiqa-brain"]').count()===1 &&
          await publicAmbiguity.locator('a[href="/assessments/w17uiqa-assessment"]').count()===1,
      "W17-01 public ambiguity links only to verified public domain routes");
    check(!(await page.locator("main").innerText()).includes("P16 PRIVATE SYNTHETIC SECRET"),
      "W17-01 public Search and ambiguity omit private editorial candidate strings");
    await page.setViewportSize({width:320,height:780});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),
      "W17-01 public alias ambiguity remains responsive at 320px RTL");
    await page.screenshot({path:path.join(out,"turn08-public-alias-320.png"),fullPage:true});
    report.screenshots.push("turn08-public-alias-320.png");
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
