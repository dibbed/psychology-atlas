"use client";
import {useState} from "react";
import {cms, CmsError} from "@/lib/cms";

type Outcome={
  case_id:number;revision_id:number;revision_status:string;
  revision_digest:string;graph_valid:boolean;graph_issues:string[];publication_eligible:boolean;
  publication_available:boolean;publication_blockers:string[];
  counts:{steps:number;questions:number;choices:number;transitions:number;scoring_dimensions:number};
};
const meanings:Record<string,string>={
  SCIENTIFIC_REVIEW_NOT_LINKED:"تأیید علمی به همین نسخه از گراف، پرسش‌ها و امتیازها متصل نیست.",
  SOURCE_RIGHTS_REVIEW_NOT_LINKED:"مدرک منبع و حقوق استفاده برای همین نسخه تأیید و ثبت نشده است.",
  P16_PUBLICATION_WORKFLOW_REQUIRED:"اجرای انتشار باید از گردش‌کار امن و نسخه‌مند مرکز انتشار P16 انجام شود.",
  CASE_GRAPH_INVALID:"گراف کیس خطای ساختاری دارد.",
  REQUIRED_CASE_METADATA_MISSING:"عنوان یا خلاصهٔ کیس ناقص است.",
  NOT_EDITABLE_DRAFT:"نسخه انتخاب‌شده Draft نیست.",
  SEED_MANAGED_REVISION:"این نسخه به داده‌های Seed تعلق دارد و نباید از ویرایشگر منتشر شود."
};
export function CaseValidation({caseId,revisionId}:{caseId:number;revisionId:number}){
  const [value,setValue]=useState<Outcome>();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const check=async()=>{
    setBusy(true);setError("");setValue(undefined);
    try{
      const r=await cms<Outcome>("/cases/"+caseId+"/revisions/"+revisionId+"/validate/");
      setValue(r.data);
    }catch(e){setError(e instanceof CmsError?e.message:"اعتبارسنجی در دسترس نیست.");}
    finally{setBusy(false);}
  };
  return <section className="card stack" aria-labelledby="case-validation-title">
    <h2 id="case-validation-title">اعتبارسنجی و پیش‌نیاز انتشار</h2>
    <p className="muted">معتبر بودن ساختار کیس به معنی تأیید علمی، مجوز استفاده از منبع یا اجازهٔ انتشار نیست.</p>
    <button className="button secondary" type="button" onClick={check} disabled={busy}
      aria-busy={busy}>{busy?"در حال اعتبارسنجی…":"بررسی ساختار و موانع انتشار"}</button>
    {error&&<p role="alert">{error}</p>}
    {value&&<div className="stack" aria-live="polite">
      <p><strong>{value.graph_valid?"ساختار گراف معتبر است.":"ساختار گراف نیاز به اصلاح دارد."}</strong></p>
      <p>اثر انگشت محتوای همین نسخه (SHA-256)، فقط برای تطبیق بازبینی:</p>
      <code dir="ltr" style={{overflowWrap:"anywhere"}}>{value.revision_digest}</code>
      <p>گام: {value.counts.steps} | پرسش: {value.counts.questions} | گزینه: {value.counts.choices} | انتقال: {value.counts.transitions} | بُعد: {value.counts.scoring_dimensions}</p>
      {value.graph_issues.length>0&&<ul>{value.graph_issues.map((issue,i)=>
        <li key={i}><code dir="ltr">{issue}</code></li>)}</ul>}
      <p><strong>{value.publication_eligible?"تمام پیش‌شرط‌های این نسخه برقرار است؛ انتشار فقط با مانیفست، تأیید و MFA انجام می‌شود.":"وضعیت انتشار: غیرفعال، تا تأییدهای لازم."}</strong></p>
      <ul>{value.publication_blockers.map((reason,i)=>
        <li key={i}>{meanings[reason]??reason}</li>)}</ul>
    </div>}
  </section>;
}
