"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {cms,cmsDate,CmsError} from "@/lib/cms";
import {useCms} from "./CmsShell";

type Kind="quiz"|"flashcard"|"daily"|"distortions";
type Receipt={receipt_id:number;archived_at:string;newly_archived:boolean};
export function LearningArchiveAction({kind,itemId,etag,archivedAt,blocked,onBusyChange,onArchived}:{
  kind:Kind;itemId:number;etag:string|null;archivedAt:string|null;blocked:boolean;
  onBusyChange:(busy:boolean)=>void;onArchived:(at:string)=>Promise<void>;
}){
  const {can}=useCms();
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  const [method,setMethod]=useState("totp"),[token,setToken]=useState(""),[ack,setAck]=useState(false);
  const [receipt,setReceipt]=useState<Receipt>();
  const pending=useRef<{scope:string;key:string}|null>(null);
  const live=useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;};},[]);
  const validTag=!!etag&&/^"\d+"$/.test(etag)&&Number.isSafeInteger(Number(etag.slice(1,-1)));
  const archive=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(busy||blocked||!ack||!token.trim()||!validTag||!etag||archivedAt||receipt)return;
    setBusy(true);onBusyChange(true);setError("");
    try{
      const scope=kind+"/"+itemId+"/"+etag;
      if(pending.current?.scope!==scope)pending.current={scope,key:crypto.randomUUID()};
      const idempotency_key=pending.current.key,reason="CONTENT_ARCHIVE";
      const bound={kind,etag:Number(etag.slice(1,-1)),reason,idempotency_key};
      await cms("/auth/step-up/",{method:"POST",body:JSON.stringify({
        action:"learning_archive",target_id:itemId,method,token:token.trim(),payload:bound,
      })});
      if(!live.current)return;
      setToken("");
      const result=await cms<Receipt>("/learning/archive/"+kind+"/"+itemId+"/",{
        method:"POST",headers:{"If-Match":etag},body:JSON.stringify({reason,idempotency_key}),
      });
      if(!live.current)return;
      setReceipt(result.data);setAck(false);
      await onArchived(result.data.archived_at);
    }catch(e){if(live.current)setError(e instanceof CmsError?e.message:"بایگانی انجام نشد؛ وضعیت سرور را بررسی کنید.");}
    finally{if(live.current)setBusy(false);onBusyChange(false);}
  };
  if(!can("cms_learning_view"))return null;
  const date=archivedAt||receipt?.archived_at;
  return <section className="card stack" aria-labelledby={"learning-archive-"+kind+"-"+itemId}>
    <h3 id={"learning-archive-"+kind+"-"+itemId}>بایگانی کنترل‌شدهٔ محتوا</h3>
    {date?<p role="status">محتوا بایگانی شده است. شناسه‌ها و تاریخچه حفظ شده‌اند. زمان ثبت: {cmsDate(date)}</p>:
      <p className="muted">بایگانی دسترسی تازه به محتوا را می‌بندد؛ پاسخ‌ها، فعالیت‌ها و زمان‌بندی مرورهای قبلی حذف نمی‌شوند.</p>}
    {receipt&&<p role="status">رسید بایگانی: <code dir="ltr">#{receipt.receipt_id}</code></p>}
    {error&&<p role="alert">{error}</p>}
    {!date&&can("cms_learning_archive")&&<form className="stack" onSubmit={archive}>
      <fieldset className="stack" disabled={busy||blocked}>
        <legend>تأیید بایگانی</legend>
        <label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>
          می‌دانم که دسترسی تازه بسته می‌شود و تاریخچه حذف نمی‌شود.</label>
        <label>روش تأیید بایگانی<select value={method} onChange={e=>setMethod(e.target.value)}>
          <option value="totp">کد TOTP</option><option value="recovery">کد بازیابی یک‌بارمصرف</option>
        </select></label>
        <label>کد MFA برای بایگانی<input type="password" autoComplete="one-time-code" maxLength={32}
          value={token} onChange={e=>setToken(e.target.value)}/></label>
        <button className="button secondary" type="submit" disabled={!ack||!token.trim()||!validTag}>
          {busy?"در حال بایگانی…":"بایگانی با تأیید دومرحله‌ای"}</button>
      </fieldset>
      {blocked&&!busy&&<p className="muted">بایگانی پس از پایان عملیات جاری و ذخیره یا کنارگذاری ویرایش‌ها فعال می‌شود.</p>}
    </form>}
  </section>;
}
