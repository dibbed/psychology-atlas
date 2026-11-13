"use client";
import {useCallback,useEffect,useRef,useState,type FormEvent} from "react";
import {cms,CmsError} from "@/lib/cms";
import {useCms} from "@/components/cms/CmsShell";

type Stage="source"|"scientific"|"rights";
type ReviewStatus={revision_digest:string;review_blockers:string[];
  reviews:Partial<Record<Stage,{id:number;outcome:string;revision_digest:string;created_at:string}>>;
  plans:{id:string;status:string;manifest_digest:string;created_at:string}[]};
type Plan={id:string;status:string;manifest_digest:string;case_id:number;revision_id:number;
  receipts:{id:number;event_type:string}[]};
const kinds:Record<Stage,string>={source:"بررسی منبع",scientific:"تأیید علمی",rights:"مجوز حقوقی"};
const stages:Stage[]=["source","scientific","rights"];

export function CasePublicationWorkflow({caseId,revisionId,etag,digest,status,onPublished}:{
  caseId:number;revisionId:number;etag:string|null;digest:string;
  status:string;onPublished:()=>Promise<void>;
}){
  const {can}=useCms();
  const [state,setState]=useState<ReviewStatus>();
  const [plan,setPlan]=useState<Plan>();
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");
  const [busy,setBusy]=useState(false);
  const [stage,setStage]=useState<Stage>("source");
  const [sourceId,setSourceId]=useState("");
  const [locator,setLocator]=useState("");
  const [rightsholder,setRightsholder]=useState("");
  const [holderBasis,setHolderBasis]=useState("");
  const [permissionStatement,setPermissionStatement]=useState("");
  const [territory,setTerritory]=useState("");
  const [reviewOn,setReviewOn]=useState("");
  const [expiresOn,setExpiresOn]=useState("");
  const [ack,setAck]=useState(false);
  const [planId,setPlanId]=useState("");
  const [token,setToken]=useState("");
  const [mfaMethod,setMfaMethod]=useState<"totp"|"recovery">("totp");
  const [actionAck,setActionAck]=useState(false);
  const requestKeys=useRef<Record<string,string>>({});
  const canReview=(kind:Stage)=>can("cms_review_decide_cases_"+kind)&&
    (kind!=="rights"||can("cms_rights_decide"));
  const selectedStage=canReview(stage)?stage:stages.find(canReview)??"source";
  const canFreeze=can("cms_publication_freeze_cases");
  const canApprove=can("cms_publication_approve_cases");
  const canApply=can("cms_publication_apply_cases");
  const canWithdraw=can("cms_publication_withdraw_cases");
  const canReinstate=can("cms_publication_reinstate_cases");
  const canVerify=can("cms_publication_verify_cases");

  const load=useCallback(async()=>{
    const response=await cms<ReviewStatus>(
      "/publication/cases/"+caseId+"/revisions/"+revisionId+"/reviews/");
    setState(response.data);
  },[caseId,revisionId]);

  useEffect(()=>{let active=true;
    void cms<ReviewStatus>("/publication/cases/"+caseId+"/revisions/"+revisionId+"/reviews/")
      .then(r=>{if(active)setState(r.data);})
      .catch(e=>{if(active)setError(e instanceof CmsError?e.message:"خواندن پیش‌نیازهای انتشار ممکن نشد.");});
    return ()=>{active=false;};
  },[caseId,revisionId]);

  const safely=async(action:()=>Promise<void>)=>{
    if(busy)return;
    setBusy(true);setError("");setSuccess("");
    try{await action();}
    catch(e){setError(e instanceof CmsError?e.message:e instanceof Error?e.message:"عملیات انجام نشد.");}
    finally{setBusy(false);}
  };
  const review=async(event:FormEvent)=>{
    event.preventDefault();
    await safely(async()=>{
      if(!etag||!ack||!/^\d+$/.test(sourceId)||!Number.isSafeInteger(Number(sourceId))||!locator.trim()){
        throw new Error("شناسه منبع، محل استناد و تأیید آگاهانه لازم است.");
      }
      const rights=selectedStage==="rights"?{
        rightsholder,holder_basis:holderBasis,permission_statement:permissionStatement,
        territory,review_on:reviewOn||null,expires_on:expiresOn||null,
        material:"text",intended_use:"public_display",
      }:undefined;
      await cms("/publication/cases/"+caseId+"/revisions/"+revisionId+"/reviews/",{
        method:"POST",headers:{"If-Match":etag},
        body:JSON.stringify({kind:selectedStage,outcome:"approved",self_review_ack:true,
          evidence:[{source_id:Number(sourceId),locator:locator.trim()}],...(rights?{rights}:{})}),
      });
      setSuccess("تصمیم بازبین ثبت شد. برای تطبیق نسخه و مدارک، وضعیت دوباره خوانده شد.");
      setAck(false);
      await load();
    });
  };
  const freeze=async()=>{
    await safely(async()=>{
      if(!etag)throw new Error("شناسه نسخه برای Freeze لازم است.");
      const response=await cms<{plan_id:string;manifest_digest:string;status:string}>(
        "/publication/cases/"+caseId+"/revisions/"+revisionId+"/freeze/",
        {method:"POST",headers:{"If-Match":etag},body:"{}"});
      setPlanId(response.data.plan_id);
      await openPlan(response.data.plan_id);
      setSuccess("مانیفستِ سروری ثابت شد. برای انتشار، تأیید مستقل و MFA لازم است.");
      await load();
    });
  };
  const openPlan=async(id:string)=>{
    const response=await cms<Plan>("/publication/cases/plans/"+id+"/");
    if(response.data.case_id!==caseId||response.data.revision_id!==revisionId)
      throw new Error("این شناسهٔ طرح به کیس یا نسخهٔ انتخابی تعلق ندارد.");
    setPlan(response.data);setPlanId(id);
  };
  const approve=async()=>{
    await safely(async()=>{
      if(!plan||!actionAck)throw new Error("مانیفست و تأیید آگاهانه لازم‌اند.");
      await cms("/publication/cases/plans/"+plan.id+"/approve/",{
        method:"POST",body:JSON.stringify({
          manifest_digest:plan.manifest_digest,self_review_ack:true}),
      });
      await openPlan(plan.id);
      setActionAck(false);
      setSuccess("تأیید مانیفست ثبت شد. هنوز هیچ انتشار عمومی انجام نشده است.");
    });
  };
  const reinstate=async()=>{
    await safely(async()=>{
      if(!plan||!actionAck)throw new Error("مانیفست و تأیید آگاهانه لازم‌اند.");
      const response=await cms<{plan_id:string}>
        ("/publication/cases/plans/"+plan.id+"/reinstate/",{method:"POST",
          body:JSON.stringify({manifest_digest:plan.manifest_digest})});
      await openPlan(response.data.plan_id);
      setActionAck(false);
      setSuccess("طرح بازگردانی ساخته شد. نمایش عمومی هنوز غیرفعال است؛ تأیید تازه و MFA جداگانه لازم است.");
    });
  };
  const execute=async(operation:"apply"|"withdraw")=>{
    await safely(async()=>{
      if(!plan||!token.trim()||!actionAck)
        throw new Error("مانیفست، تأیید نهایی و کد احراز هویت دوباره لازم‌اند.");
      const action=operation==="apply"?"case_publish":"case_withdraw";
      await cms("/auth/step-up/",{
        method:"POST",body:JSON.stringify({
          action,target_id:revisionId,method:mfaMethod,token:token.trim(),
          payload:{manifest_digest:plan.manifest_digest},
        }),
      });
      setToken("");
      const result=await cms<{status:string;newly_applied?:boolean;newly_withdrawn?:boolean}>(
        "/publication/cases/plans/"+plan.id+"/"+operation+"/",{
          method:"POST",body:JSON.stringify({
            manifest_digest:plan.manifest_digest,
            idempotency_key:requestKeys.current[plan.id+"/"+operation]??=crypto.randomUUID(),
          }),
        });
      await openPlan(plan.id);
      setActionAck(false);
      setSuccess(operation==="apply"
        ?"نسخه با رسید سروری منتشر شد. تاریخچهٔ تلاش‌های قبلی دست‌نخورده است."
        :"نمایش عمومی نسخه غیرفعال شد. سوابق قبلی حفظ شده‌اند.");
      await onPublished();
    });
  };
  if(!can("cms_cases_validate"))return null;
  const isDraft=status==="draft";
  return <section className="card stack" dir="rtl" aria-labelledby="case-publication-title">
    <h2 id="case-publication-title">مرکز انتشار نسخهٔ کیس (P16)</h2>
    <p className="muted">سه تصمیم انسانیِ منبع، علمی و حقوقی باید به اثرانگشت همین نسخه متصل شوند. اعتبار گراف به‌تنهایی مجوز انتشار نیست. هیچ انتشار خودکاری انجام نمی‌شود.</p>
    <p>شناسهٔ محتوای نسخه: <code dir="ltr" style={{overflowWrap:"anywhere"}}>{digest}</code></p>
    {error&&<p role="alert">{error}</p>}
    {success&&<p role="status">{success}</p>}
    <button type="button" className="button secondary" disabled={busy} onClick={()=>void safely(load)}>
      تازه‌سازی وضعیت بررسی‌ها
    </button>
    {state&&<div className="stack">
      {state.revision_digest!==digest&&<p role="alert">محتوای نسخه از زمان بارگذاری تغییر کرده است. ابتدا نسخه را دوباره باز کنید.</p>}
      <ul>{stages.map(kind=><li key={kind}>
        {kinds[kind]}: {state.reviews[kind]?.outcome==="approved"&&state.reviews[kind]?.revision_digest===digest?
          "تأیید‌شده برای این نسخه":state.reviews[kind]?.outcome==="revoked"?"لغوشده":"نیازمند تأیید"}
      </li>)}</ul>
      {state.review_blockers.length>0&&<p className="muted">
        موانع: {state.review_blockers.join(" ، ")}
      </p>}
    </div>}
    {isDraft&&stages.some(canReview)&&<form className="stack" onSubmit={review}>
      <h3>ثبت تصمیم بازبینی</h3>
      <label>نوع بررسی
        <select value={selectedStage} onChange={e=>{setStage(e.target.value as Stage);setAck(false);}}>
          {stages.filter(canReview).map(kind=><option key={kind} value={kind}>{kinds[kind]}</option>)}
        </select>
      </label>
      <label>شناسهٔ SourceReference تأییدشده
        <input type="number" min="1" required value={sourceId} onChange={e=>setSourceId(e.target.value)}/>
      </label>
      <label>محل دقیق مدرک برای همین ادعا
        <input required maxLength={1000} value={locator} onChange={e=>setLocator(e.target.value)}
          placeholder="صفحه، بند، بخش یا نشانی مدرک"/>
      </label>
      {selectedStage==="rights"&&<>
        <p className="muted">منبع علمی یا در دسترس بودن آنلاین، به‌تنهایی مجوز بازنشر نیست. فقط پس از بررسی واقعی مدرک حق استفاده ثبت شود.</p>
        <label>دارندهٔ حق<input required maxLength={1000} value={rightsholder} onChange={e=>setRightsholder(e.target.value)}/></label>
        <label>مبنای شناسایی دارندهٔ حق<textarea required maxLength={2000} value={holderBasis} onChange={e=>setHolderBasis(e.target.value)}/></label>
        <label>شرح دقیق اجازهٔ نمایش عمومی متن دیجیتال<textarea required maxLength={4000} value={permissionStatement} onChange={e=>setPermissionStatement(e.target.value)}/></label>
        <label>قلمرو مجوز<input required maxLength={255} value={territory} onChange={e=>setTerritory(e.target.value)}/></label>
        <label>تاریخ بازبینی بعدی<input type="date" required value={reviewOn} onChange={e=>setReviewOn(e.target.value)}/></label>
        <label>انقضای مجوز، در صورت وجود<input type="date" value={expiresOn} onChange={e=>setExpiresOn(e.target.value)}/></label>
      </>}
      <label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>
        من مدارک همین نسخه را شخصاً بررسی کرده‌ام و مسئولیت تصمیم ثبت‌شده را می‌پذیرم.</label>
      <button className="button secondary" disabled={busy||!etag||!ack||state?.revision_digest!==digest}>ثبت تصمیم نسخه‌مند</button>
    </form>}
    {isDraft&&canFreeze&&<div className="stack">
      <h3>Freeze و ساخت Manifest</h3>
      <p>Freeze فقط پس از رفع تمام موانع و ثبت سه تأیید معتبر ممکن است.</p>
      <button className="button secondary" type="button" disabled={busy||!etag||!state||state.review_blockers.length>0}
        onClick={()=>void freeze()}>ساخت مانیفست ثابت سروری</button>
    </div>}
    {canVerify&&<div className="stack">
      <h3>بررسی طرح و رسید انتشار</h3>
      <label>شناسهٔ طرح
        <input dir="ltr" value={planId} onChange={e=>setPlanId(e.target.value.trim())}
          placeholder="UUID مانیفست"/>
      </label>
      <button type="button" className="button secondary" disabled={busy||!planId} onClick={()=>void safely(()=>openPlan(planId))}>
        دریافت وضعیت و رسید
      </button>
      {state?.plans.map(row=><button key={row.id} type="button" className="button secondary"
        disabled={busy} onClick={()=>void safely(()=>openPlan(row.id))}>
        طرح {row.id.slice(0,8)} | {row.status}
      </button>)}
    </div>}
    {plan&&<div className="stack">
      <p>وضعیت مانیفست: <strong>{plan.status}</strong></p>
      <p>اثر انگشت مانیفست (خود متن علمی نیست):</p>
      <code dir="ltr" style={{overflowWrap:"anywhere"}}>{plan.manifest_digest}</code>
      <p>رسیدهای ثبت‌شده: {plan.receipts.map(r=>r.event_type+" #"+r.id).join(" ، ")||"هنوز ندارد"}</p>
      <label><input type="checkbox" checked={actionAck} onChange={e=>setActionAck(e.target.checked)}/>
        محتوای این مانیفست، مسئولیت انتشار و اثر آن بر نمایش عمومی را بررسی کردم.</label>
      {plan.status==="frozen"&&canApprove&&<button className="button secondary" type="button"
        disabled={busy||!actionAck} onClick={()=>void approve()}>تأیید مانیفست</button>}
      {plan.status==="withdrawn"&&canReinstate&&<>
        <p className="muted">بازگردانی، تأیید قبلی را دوباره به کار نمی‌برد: یک طرح تازه ساخته می‌شود و انتشار آن به تأیید مستقل و MFA تازه نیاز دارد. تاریخ انتشار اولیه حفظ می‌شود.</p>
        <button className="button secondary" type="button" disabled={busy||!actionAck}
          onClick={()=>void reinstate()}>ساخت طرح بازگردانی نمایش عمومی</button>
      </>}
      {((plan.status==="approved"&&canApply)||(plan.status==="applied"&&canWithdraw))&&<>
        <label>روش احراز دوباره
          <select value={mfaMethod} onChange={e=>setMfaMethod(e.target.value as "totp"|"recovery")}>
            <option value="totp">کد TOTP</option><option value="recovery">کد بازیابی یک‌بارمصرف</option>
          </select>
        </label>
        <label>کد MFA
          <input type="password" autoComplete="one-time-code" value={token} onChange={e=>setToken(e.target.value)}/>
        </label>
        <button className="button" type="button" disabled={busy||!actionAck||!token.trim()}
          onClick={()=>void execute(plan.status==="approved"?"apply":"withdraw")}>
          {plan.status==="approved"?"تأیید نهایی و انتشار نسخه":"لغو نمایش عمومی و ثبت رسید"}
        </button>
      </>}
    </div>}
  </section>;
}
