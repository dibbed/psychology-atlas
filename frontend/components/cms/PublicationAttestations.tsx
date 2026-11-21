"use client";

import {useEffect,useRef,useState} from "react";
import {useSearchParams} from "next/navigation";
import {cms,CmsError} from "@/lib/cms";
import {useCms} from "@/components/cms/CmsShell";

type Domain="learning"|"brain"|"assessment";
type Kind="source"|"scientific"|"rights";
type Summary={
  schema:"cms-private-manifest-attestation-status-v1";
  plan_id:string;manifest_digest:string;
  status:"attestations_recorded_not_publication_clearance";
  states:Record<Kind,"absent"|"attested"|"revoked">;
  attestations_current:boolean;snapshot_current:boolean;
  approved:false;publication_available:false;public_projection:null;
};
type Result={id:number;plan_id:string;manifest_digest:string;
  kind:Kind;outcome:"attested"|"revoked";recovered:boolean;
  approved:false;publication_available:false;notice:string};

const domains:Domain[]=["learning","brain","assessment"];
const labels:Record<Kind,string>={source:"منبع",scientific:"بررسی علمی",rights:"حقوق استفاده"};

export default function PublicationAttestations(){
  const params=useSearchParams();
  const {can}=useCms();
  const [domain,setDomain]=useState<Domain>("brain");
  const [planId,setPlanId]=useState("");
  const [manifestDigest,setManifestDigest]=useState("");
  const [kind,setKind]=useState<Kind>("source");
  const [outcome,setOutcome]=useState<"attested"|"revoked">("attested");
  const [sourceIds,setSourceIds]=useState("");
  const [evidenceReference,setEvidenceReference]=useState("");
  const [reviewed,setReviewed]=useState(false);
  const [data,setData]=useState<Summary>();
  const [result,setResult]=useState<Result>();
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const retryKey=useRef("");
  const allowed=can("cms_publication_approve_"+domain)&&
    can("cms_"+domain+"_view");
  const verifyAllowed=can("cms_publication_verify_"+domain)&&
    can("cms_"+domain+"_view");
  const canKind=allowed&&can("cms_review_decide_"+domain+"_"+kind);
  const [revision,setRevision]=useState(0);

  useEffect(()=>{
    const id=params.get("plan_id")??"";
    const d=params.get("domain")??"";
    if(id)setPlanId(id);
    if(domains.includes(d as Domain))setDomain(d as Domain);
  },[params]);

  useEffect(()=>{
    setData(undefined);setResult(undefined);setError("");
    retryKey.current="";setReviewed(false);setRevision(x=>x+1);
  },[domain,planId,kind,outcome]);

  async function load(){
    if(!verifyAllowed||busy||!planId.trim())return;
    const stamp=revision;
    setBusy(true);setData(undefined);setResult(undefined);setError("");
    try{
      const response=await cms<Summary>(
        "/publication/plans/"+encodeURIComponent(planId.trim())+"/attestations/");
      if(stamp!==revision)return;
      if(response.data.plan_id!==planId.trim().toLowerCase()||
          response.data.public_projection!==null||
          response.data.publication_available||
          response.data.approved)throw Error("UNTRUSTED_ATTESTATION_RESULT");
      setData(response.data);setManifestDigest(response.data.manifest_digest);
    }catch(e){
      if(stamp===revision)setError(e instanceof CmsError?e.message:"وضعیت این مانیفست قابل بازخوانی نیست.");
    }finally{if(stamp===revision)setBusy(false);}
  }

  async function submit(){
    if(!canKind||!data||busy||!reviewed||!planId.trim())return;
    const ids=sourceIds.split(",").map(s=>s.trim()).filter(Boolean);
    if(outcome==="attested"&&
      (!ids.length||ids.some(s=>!/^[0-9]+$/.test(s)||!Number.isSafeInteger(Number(s))||
         Number(s)<=0)||!evidenceReference.trim())){
      setError("شناسهٔ منبع معتبر و ارجاع مستقل به شاهد بازبینی لازم است.");
      return;
    }
    const sourceList=ids.map(Number).sort((a,b)=>a-b);
    if(sourceList.length!==new Set(sourceList).size){setError("شناسه‌های منبع تکراری‌اند.");return;}
    if(!retryKey.current)retryKey.current=crypto.randomUUID();
    setBusy(true);setError("");
    try{
      const response=await cms<Result>(
        "/publication/plans/"+encodeURIComponent(planId.trim())+"/attestations/",{
          method:"POST",body:JSON.stringify({
            kind,outcome,manifest_digest:manifestDigest,
            request_key:retryKey.current,
            evidence_source_ids:outcome==="revoked"?[]:sourceList,
            rights_scope:outcome==="attested"&&kind==="rights"?
              ["metadata","text","translation"]:[],
            evidence_reference:outcome==="revoked"?"":evidenceReference,
            self_review_ack:true,
          }),
        });
      if(response.data.plan_id!==planId.trim().toLowerCase()||
          response.data.publication_available||response.data.approved)
        throw Error("ATTESTATION_RESULT_MISMATCH");
      setResult(response.data);retryKey.current="";
      setData(undefined);setReviewed(false);
    }catch(e){
      setError(e instanceof CmsError?e.message:
        "ثبت تصمیم انجام نشد؛ تا تغییر اطلاعات، همان شناسهٔ Idempotency برای تلاش مجدد حفظ می‌شود.");
    }finally{setBusy(false);}
  }

  return <main className="shell page stack">
    <div>
      <div className="meta">W16-03 · فقط ثبت تصمیم بازبین</div>
      <h1 className="section-title">سوابق مستقل بازبینی مانیفست</h1>
      <p className="section-copy">این بخش صرفاً تصمیم مستقل بازبین برای منبع، ارزیابی علمی و بررسی حقوق را ثبت و ابطال می‌کند.
        هیچ تصمیمی از این صفحه مجوز عمومی انتشار، گواهی قانونی یا Apply نیست.</p>
    </div>
    <section className="card stack" aria-label="بازخوانی مانیفست خصوصی برای بازبین">
      <label>حوزهٔ بررسی
        <select value={domain} onChange={e=>setDomain(e.target.value as Domain)}>
          {domains.map(d=><option value={d} key={d}>{d}</option>)}
        </select>
      </label>
      <label>شناسهٔ مانیفست نسخه‌مند
        <input value={planId} dir="ltr" spellCheck={false} autoComplete="off"
          onChange={e=>setPlanId(e.target.value)} placeholder="UUID"/>
      </label>
      <button type="button" className="button secondary" onClick={()=>void load()}
        disabled={!verifyAllowed||busy||!planId.trim()}>
        {busy?"در حال بررسی…":"بازخوانی وضعیت فعلی"}
      </button>
      {!verifyAllowed&&<p className="muted">برای خواندن وضعیت، مجوز مستقل مشاهدهٔ انتشار همین حوزه لازم است.</p>}
      {data&&<section className="stack" aria-label="وضعیت خصوصی بازبینی">
        <p>اثر انگشت مانیفست: <code dir="ltr" style={{overflowWrap:"anywhere"}}>{data.manifest_digest}</code></p>
        <p role="status">{data.snapshot_current?"نسخه و وابستگی‌ها هنگام این بازخوانی مطابق‌اند.":"نسخه یا یکی از وابستگی‌ها دیگر مطابق نیست."}</p>
        <ul>{(["source","scientific","rights"] as const).map(k=>
          <li key={k}>{labels[k]}: {data.states[k]==="attested"?"ادعای بازبینی ثبت شده":
              data.states[k]==="revoked"?"تصمیم لغو شده":"بازبینی ثبت نشده"}</li>
        )}</ul>
        <p className="muted">وضعیت سوابق: {data.attestations_current?"سه ادعای نسخه‌مند فعلی ثبت شده‌اند، اما هنوز هیچ مجوزی صادر نشده است.":"مدارک ناکامل یا قدیمی‌اند."}</p>
      </section>}
    </section>
    {allowed&&<section className="card stack" aria-label="ثبت تصمیم بازبین مستقل">
      <h2>ثبت یا لغو تصمیم</h2>
      <label>نوع تصمیم
        <select value={kind} onChange={e=>setKind(e.target.value as Kind)}>
          <option value="source">منبع</option>
          <option value="scientific">علمی</option>
          <option value="rights">حقوق</option>
        </select>
      </label>
      <label>عملیات
        <select value={outcome} onChange={e=>setOutcome(e.target.value as "attested"|"revoked")}>
          <option value="attested">ثبت اظهارنظر مستقل</option>
          <option value="revoked">لغو اظهارنظر قبلی</option>
        </select>
      </label>
      {outcome==="attested"&&<>
        <label>شناسه‌های منابع دقیق، با کاما جداشده
          <input value={sourceIds} onChange={e=>{setSourceIds(e.target.value);retryKey.current="";}}
            dir="ltr" placeholder="1, 2" autoComplete="off"/>
        </label>
        <label>ارجاع کوتاه به شواهد مستقل بازبینی (خصوصی)
          <textarea value={evidenceReference} rows={3}
            onChange={e=>{setEvidenceReference(e.target.value);retryKey.current="";}}
            maxLength={400} placeholder="شناسه/ارجاع سندی که خودتان واقعاً بررسی کرده‌اید"/>
        </label>
        {kind==="rights"&&<p className="muted">دامنهٔ ثبت: metadata، text، translation.
          درج این دامنه‌ها به معنی تأیید قانونی حق استفادهٔ عمومی نیست.</p>}
      </>}
      <label>
        <input type="checkbox" checked={reviewed}
          onChange={e=>setReviewed(e.target.checked)}/>
        هویت، منابع و شواهد را مستقلاً بررسی کرده‌ام و می‌دانم این تصمیم هیچ محتوایی منتشر نمی‌کند.
      </label>
      <button type="button" className="button secondary"
        onClick={()=>void submit()} disabled={!canKind||!data||busy||!reviewed}>
        {busy?"در حال ثبت…":"ثبت تصمیمِ فقط‌خصوصی"}
      </button>
      {!canKind&&<p className="muted">مجوز مستقل ثبت این نوع بازبینی وجود ندارد.</p>}
      {result&&<p role="status">رسید تصمیم #{result.id} ثبت شد. هیچ مجوز انتشار یا Apply ایجاد نشده است.</p>}
    </section>}
    {error&&<p role="alert">{error}</p>}
  </main>;
}
