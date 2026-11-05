"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {CmsError} from "@/lib/cms";
import {mutationBlocked} from "@/lib/cmsJobs";
import {CmsState} from "./CmsShell";
import {usePrivateCms} from "./CmsJobsShared";

export type StudyOperation={kind:"plan"|"block"|"session";etag:string;actions:string[]};
type Intent={kind:StudyOperation["kind"];target_id:number;action:string;etag:string;purpose:"SUPPORT_REQUEST";
  case_ref:string;reason:"STUDY_SUPPORT";request_key:string;scheduled_date?:string};
const labels:Record<string,string>={pause:"توقف برنامه",resume:"ادامهٔ برنامهٔ متوقف",reschedule:"جابه‌جایی بلوک",skip:"ردکردن بلوک",unlock:"آزادکردن زمان بلوک",abandon:"رهاکردن نشست"};

export default function StudyOperationAction({userId,targetId,operation,caseRef,onDirty}:{userId:number;targetId:number;
  operation:StudyOperation;caseRef:string;onDirty:(id:string,value:boolean)=>void}){
  const {can,request,current}=usePrivateCms();
  const [action,setAction]=useState(operation.actions[0]??""),[date,setDate]=useState("");
  const [method,setMethod]=useState("totp"),[token,setToken]=useState(""),[ack,setAck]=useState(false);
  const [intent,setIntent]=useState<Intent>(),[receipt,setReceipt]=useState<number>(),[error,setError]=useState<unknown>(),[busy,setBusy]=useState(false);
  const lock=useRef(false),id=operation.kind+"-"+targetId;
  const allowed=can("cms_user_view")&&can("cms_study_view")&&can("cms_study_correct");
  const replay=!!intent&&error instanceof CmsError&&error.code==="UNKNOWN_OUTCOME";
  const blocked=mutationBlocked(error)&&!replay;
  useEffect(()=>{onDirty(id,busy||!!token||!!intent&&!receipt);return()=>onDirty(id,false);},[id,busy,token,intent,receipt,onDirty]);
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!allowed||busy||lock.current||receipt||blocked||!ack||!action||!replay&&!token.trim())return;
    const body=intent??{kind:operation.kind,target_id:targetId,action,etag:operation.etag,purpose:"SUPPORT_REQUEST" as const,
      case_ref:caseRef,reason:"STUDY_SUPPORT" as const,request_key:crypto.randomUUID(),...(action==="reschedule"?{scheduled_date:date}:{})};
    lock.current=true;setBusy(true);setError(undefined);setIntent(body);let submitted=false;
    try{
      if(!replay)await request("/auth/step-up/",{method:"POST",body:JSON.stringify({action:"study_correct",target_id:userId,payload:body,method,token:token.trim()})});
      if(!current())return;setToken("");submitted=true;
      const response=await request<{receipt_id:number}>(`/users/${userId}/study/operate/`,{method:"POST",headers:{"If-Match":body.etag},body:JSON.stringify(body)});
      if(current())setReceipt(response.data.receipt_id);
    }catch(failure){if(current()){setError(failure);setToken("");if(!submitted)setIntent(undefined);}}
    finally{lock.current=false;if(current())setBusy(false);}
  }
  if(!allowed||!operation.actions.length)return null;
  return <section className="stack" aria-label={"اقدام پشتیبانی مطالعه "+targetId}><h3>اقدام کنترل‌شدهٔ مطالعه</h3>
    <p className="muted">فقط طبق درخواست ثبت‌شدهٔ همین کاربر اقدام کنید. این عمل امتیاز، تسلط یا تکمیل آموزشی ایجاد نمی‌کند. وضعیت نمایش‌داده‌شده متعلق به زمان خواندن است؛ بررسی نتیجه به خواندن تازه نیاز دارد.</p>
    {error!=null&&<CmsState error={error}/>}
    {blocked&&<p role="alert">پیش از اقدام تازه، نتیجه را پاک کرده و وضعیت جاری را با تأیید تازه بخوانید.</p>}
    {receipt?<p role="status">اقدام ثبت شد؛ رسید {receipt.toLocaleString("fa-IR")}. برای عمل بعدی وضعیت جاری را دوباره بخوانید.</p>:
      <form className="stack" onSubmit={submit}><fieldset className="cms-fieldset stack" disabled={busy||blocked}>
        <label>عملیات پشتیبانی مطالعه<select value={action} disabled={!!intent} onChange={event=>setAction(event.target.value)}>
          {operation.actions.map(value=><option key={value} value={value}>{labels[value]??value}</option>)}
        </select></label>
        {action==="reschedule"&&<label>روز جدید بلوک<input type="date" required value={date} disabled={!!intent} onChange={event=>setDate(event.target.value)}/></label>}
        <label><input type="checkbox" checked={ack} onChange={event=>setAck(event.target.checked)}/>درخواست پشتیبانی و اثر همین عمل را بررسی کرده‌ام.</label>
        {!replay&&<><label>روش تأیید اقدام مطالعه<select value={method} onChange={event=>setMethod(event.target.value)}><option value="totp">TOTP</option><option value="recovery">کد بازیابی یک‌بارمصرف</option></select></label>
          <label>کد MFA اقدام مطالعه<input type="password" autoComplete="one-time-code" maxLength={32} value={token} onChange={event=>setToken(event.target.value)}/></label></>}
        <button className="button primary" disabled={!ack||!replay&&!token.trim()}>{replay?"تطبیق همان اقدام مطالعه":"اعمال اقدام مطالعه با تأیید دومرحله‌ای"}</button>
      </fieldset></form>}
  </section>;
}
