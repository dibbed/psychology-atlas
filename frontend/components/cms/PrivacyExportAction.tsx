"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {CmsError} from "@/lib/cms";
import {type AdminJob,mutationBlocked} from "@/lib/cmsJobs";
import {CmsState} from "./CmsShell";
import {usePrivateCms} from "./CmsJobsShared";

type Intent={purpose:"DATA_SUBJECT_REQUEST";case_ref:string;request_key:string};
export default function PrivacyExportAction({userId,onDirty}:{userId:number;onDirty:(value:boolean)=>void}){
  const {can,request,current}=usePrivateCms();
  const [reference,setReference]=useState(""),[method,setMethod]=useState("totp"),[token,setToken]=useState(""),[ack,setAck]=useState(false);
  const [intent,setIntent]=useState<Intent>(),[job,setJob]=useState<AdminJob>(),[error,setError]=useState<unknown>(),[busy,setBusy]=useState(false);
  const [uncertain,setUncertain]=useState(false);
  const lock=useRef(false),allowed=can("cms_user_view")&&can("cms_privacy_export");
  const replay=uncertain&&error instanceof CmsError&&error.code==="UNKNOWN_OUTCOME"&&!!intent;
  const blocked=mutationBlocked(error);
  useEffect(()=>{onDirty(busy||!!token||!!intent&&!job);return()=>onDirty(false);},[busy,token,intent,job,onDirty]);
  useEffect(()=>{const hide=()=>{if(document.hidden)setToken("");};document.addEventListener("visibilitychange",hide);return()=>document.removeEventListener("visibilitychange",hide);},[]);
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!allowed||busy||lock.current||job||blocked&&!replay||!ack||!replay&&!token.trim())return;
    const body=intent??{purpose:"DATA_SUBJECT_REQUEST" as const,case_ref:reference.trim(),request_key:crypto.randomUUID()};
    lock.current=true;setBusy(true);setError(undefined);setIntent(body);let submitted=false;
    try{
      if(!replay)await request("/auth/step-up/",{method:"POST",body:JSON.stringify({action:"privacy_export",target_id:userId,payload:body,method,token:token.trim()})});
      if(!current())return;setToken("");
      submitted=true;
      const response=await request<{job:AdminJob}>(`/users/${userId}/privacy/export/`,{method:"POST",body:JSON.stringify(body)});
      if(current()){setJob(response.data.job);setUncertain(false);}
    }catch(failure){if(current()){setError(failure);setToken("");setUncertain(submitted&&failure instanceof CmsError&&failure.code==="UNKNOWN_OUTCOME");if(!submitted)setIntent(undefined);}}
    finally{lock.current=false;if(current())setBusy(false);}
  }
  if(!allowed)return null;
  return <section className="card stack" aria-label="خروجی خصوصی اطلاعات شخصی"><h2>خروجی درخواست صاحب داده</h2>
    <p>فقط برای درخواست واقعی همین صاحب داده اقدام کنید. فایل شامل اطلاعات هویتی و سوابق شخصی مجاز اوست؛ گذرواژه، نشست، MFA، دادهٔ دیگران و محتوای مرجع در آن قرار نمی‌گیرد. تاریخچهٔ یادگیری تغییر نمی‌کند.</p>
    <p className="muted">دسترسی فایل پس از ۲۴ ساعت پایان می‌یابد. این زمان، سیاست حذف سوابق اصلی نیست. دریافت به مجوز مستقل فایل و مجوز جاری حریم خصوصی نیاز دارد.</p>
    {error!=null&&<CmsState error={error}/>}
    {replay&&<p role="alert">نتیجه نامعلوم است؛ همان درخواست با همان کلید تطبیق می‌شود. فهرست کارها نیز قابل بررسی است.</p>}
    {!job&&<form className="stack" onSubmit={submit}><fieldset className="cms-fieldset stack" disabled={busy||blocked&&!replay}>
      <label>شناسهٔ UUID درخواست صاحب داده<input dir="ltr" required autoComplete="off" maxLength={36} disabled={!!intent} value={reference}
        pattern="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" onChange={event=>setReference(event.target.value)}/></label>
      <label><input type="checkbox" checked={ack} onChange={event=>setAck(event.target.checked)}/>درخواست واقعی و اختیار تهیهٔ خروجی همین کاربر را بررسی کرده‌ام.</label>
      {!replay&&<><label>روش تأیید خروجی خصوصی<select value={method} onChange={event=>setMethod(event.target.value)}><option value="totp">TOTP</option><option value="recovery">کد بازیابی یک‌بارمصرف</option></select></label>
        <label>کد MFA خروجی خصوصی<input type="password" autoComplete="one-time-code" maxLength={32} value={token} onChange={event=>setToken(event.target.value)}/></label></>}
      <button className="button primary" disabled={!ack||!reference||!replay&&!token.trim()}>{replay?"تطبیق همان درخواست خروجی خصوصی":"ایجاد کار خروجی خصوصی با تأیید دومرحله‌ای"}</button>
    </fieldset></form>}
    {intent&&<p className="cms-id">کلید پیگیری: <bdi>{intent.request_key}</bdi></p>}
    {job&&<p role="status">درخواست در سرور ثبت شده است؛ آماده‌شدن فایل را در کار پردازش بررسی کنید. <a className="cms-link" href={"/admin-console/jobs/"+job.id}>پیگیری خروجی اطلاعات شخصی</a></p>}
  </section>;
}
