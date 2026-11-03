"use client";
import {useCallback,useEffect,useRef,useState,type FormEvent} from "react";
import {cmsDate} from "@/lib/cms";
import {faNumber} from "@/lib/fa";
import {StructuredValue} from "@/components/DSMRecordView";
import {CmsState} from "./CmsShell";
import {usePrivateCms} from "./CmsJobsShared";

type Schema={scopes:{key:string;label:string}[];page_size:number;max_page:number};
type Result={subject_id:number;scope:string;purpose:string;page:number;page_size:number;count:number;
  results:Record<string,unknown>[];as_of:string};
const labels:Record<string,string>={id:"شناسه",body:"متن خصوصی",status:"وضعیت",state:"وضعیت مرور",created_at:"زمان ایجاد",updated_at:"آخرین تغییر",
  completed_at:"زمان تکمیل",score:"امتیاز ثبت‌شده",max_score:"حداکثر امتیاز",correct_count:"تعداد پاسخ درست",total_questions:"تعداد سؤال",answered_at:"زمان پاسخ",
  is_correct:"پاسخ درست بوده",activity_date:"روز فعالیت",activity_type:"نوع فعالیت",occurred_at:"زمان فعالیت",progress_percent:"درصد پیشرفت ثبت‌شده",
  last_viewed_at:"آخرین مشاهده",last_reviewed_at:"آخرین مرور",due_at:"موعد مرور",interval_days:"فاصلهٔ روزها",ease_factor:"ضریب سهولت",
  repetitions:"تعداد مرور",lapses:"تعداد فراموشی",last_rating:"آخرین ارزیابی",name:"نام برنامه",plan_kind:"نوع برنامه",start_date:"روز شروع",target_date:"روز هدف",
  notes:"یادداشت برنامه",generation_version:"نسخهٔ برنامه‌ریزی",priority:"اولویت",include_practice:"تمرین دارد",block_kind:"نوع بلوک",scheduled_date:"روز برنامه‌ریزی‌شده",
  estimated_minutes:"زمان برآوردشده",locked_by_user:"قفل کاربر",started_at:"زمان شروع",skipped_at:"زمان ردکردن",planned_minutes:"زمان برنامه‌ریزی‌شده",
  actual_seconds:"ثانیهٔ ثبت‌شده",abandoned_at:"زمان رهاکردن",state_version:"نسخهٔ وضعیت",event_type:"نوع رویداد",awarded_score:"امتیاز رویداد",
  recommendation_type:"نوع پیشنهاد",target_type:"نوع هدف",target_id:"شناسهٔ هدف",value:"بازخورد",suppressed_until:"پایان تعویق",
  study_timezone:"منطقهٔ زمانی مطالعه",default_daily_minutes:"دقیقهٔ روزانه",default_session_minutes:"دقیقهٔ نشست",week_starts_on:"شروع هفته"};
const targets:Record<string,string>={disorder:"اختلال",concept:"مفهوم",therapy:"رویکرد درمانی",quiz:"آزمون",attempt:"تلاش",question:"سؤال",selected_choice:"گزینهٔ انتخاب‌شده",
  case:"پرونده",revision:"نسخه",current_step:"گام جاری",step:"گام",challenge:"چالش",item:"تمرین",plan:"برنامه",scope:"حوزهٔ برنامه",primary_block:"بلوک اصلی",
  theory:"نظریه",psychologist:"شخص",timeline_event:"رویداد",clinical_case:"پروندهٔ آموزشی"};
function label(key:string){return labels[key]||(key.endsWith("_id")?"شناسهٔ "+(targets[key.slice(0,-3)]||key):key.replaceAll("_"," "));}

export default function PrivacyConsole({userId}:{userId:number}){
  const {can,request,current,setDirty}=usePrivateCms();
  const allowed=can("cms_user_view")&&can("cms_privacy_sensitive_read");
  const [subject,setSubject]=useState<{id:number;username:string}>(),[schema,setSchema]=useState<Schema>();
  const [scope,setScope]=useState("disorder_notes"),[page,setPage]=useState(1),[caseRef,setCaseRef]=useState("");
  const [method,setMethod]=useState("totp"),[token,setToken]=useState(""),[ack,setAck]=useState(false);
  const [data,setData]=useState<Result>(),[error,setError]=useState<unknown>(),[readError,setReadError]=useState<unknown>();
  const [busy,setBusy]=useState(false),[reload,setReload]=useState(0);const lock=useRef(false);
  const generation=useRef(0),pending=useRef<AbortController|null>(null);
  const clearPrivate=useCallback(()=>{generation.current++;pending.current?.abort();setData(undefined);setToken("");},[]);
  useEffect(()=>{setDirty(busy||!!token);return()=>setDirty(false);},[busy,token,setDirty]);
  useEffect(()=>{
    if(!allowed)return;let active=true;const abort=new AbortController();setSubject(undefined);setSchema(undefined);setReadError(undefined);setData(undefined);
    const signal=AbortSignal.any([abort.signal,AbortSignal.timeout(15000)]);
    void Promise.all([request<{id:number;username:string}>(`/users/${userId}/`,{signal}),request<Schema>("/users/privacy/schema/",{signal})])
      .then(([user,metadata])=>{if(active&&current()){setSubject(user.data);setSchema(metadata.data);}})
      .catch(failure=>{if(active&&current())setReadError(failure);});
    return()=>{active=false;abort.abort();};
  },[allowed,userId,request,current,reload]);
  useEffect(()=>{
    const visibility=()=>{if(document.hidden)clearPrivate();};
    document.addEventListener("visibilitychange",visibility);window.addEventListener("pagehide",clearPrivate);
    if(document.hidden)clearPrivate();
    return()=>{generation.current++;pending.current?.abort();document.removeEventListener("visibilitychange",visibility);window.removeEventListener("pagehide",clearPrivate);};
  },[clearPrivate]);
  useEffect(()=>{
    if(!data)return;const timer=window.setTimeout(clearPrivate,300000);return()=>clearTimeout(timer);
  },[data,clearPrivate]);
  async function read(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!allowed||!subject||!schema||busy||lock.current||!ack||!token.trim()||document.hidden)return;
    const body={purpose:"SUPPORT_REQUEST",case_ref:caseRef.trim(),scope,page};
    const stamp=++generation.current,abort=new AbortController();pending.current=abort;
    const signal=AbortSignal.any([abort.signal,AbortSignal.timeout(15000)]);
    lock.current=true;setBusy(true);setError(undefined);setData(undefined);
    try{
      await request("/auth/step-up/",{method:"POST",signal,body:JSON.stringify({action:"privacy_read",target_id:userId,payload:body,method,token:token.trim()})});
      if(!current()||generation.current!==stamp||document.hidden)return;setToken("");
      const result=await request<Result>(`/users/${userId}/privacy/read/`,{method:"POST",signal,body:JSON.stringify(body)});
      if(current()&&generation.current===stamp&&!document.hidden)setData(result.data);
    }catch(failure){if(current()&&generation.current===stamp&&!document.hidden){setError(failure);setToken("");}}
    finally{if(pending.current===abort)pending.current=null;lock.current=false;if(current())setBusy(false);}
  }
  function clearInput(){clearPrivate();setError(undefined);}
  if(!allowed)return <CmsState empty="خواندن اطلاعات شخصی به مجوز مستقل کاربر و حریم خصوصی نیاز دارد."/>;
  if(readError)return <CmsState error={readError} retry={()=>setReload(value=>value+1)}/>;
  if(!subject||!schema)return <CmsState loading/>;
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/accounts">بازگشت به حساب‌ها</a>
    <h1>دسترسی هدفمند به اطلاعات شخصی</h1><p>کاربر: <bdi>{subject.username}</bdi> · شناسهٔ {faNumber(subject.id)}</p>
    <p className="cms-notice">فقط برای درخواست پشتیبانی ثبت‌شده و همین کاربر بخوانید. هر خواندن با مجوز جاری، MFA تازه و ثبت دسترسی بررسی می‌شود؛ هیچ یادداشت، پاسخ یا پیشرفتی در این صفحه تغییر نمی‌کند.</p>
    {error!=null&&<CmsState error={error}/>}
    <form className="card stack" onSubmit={read}><h2>درخواست مشاهدهٔ محدود</h2>
      <fieldset className="cms-fieldset stack" disabled={busy}>
        <p>هدف: پشتیبانی با درخواست ثبت‌شده</p>
        <label>شناسهٔ UUID درخواست پشتیبانی<input dir="ltr" maxLength={36} required autoComplete="off" value={caseRef}
          pattern="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" onChange={event=>{setCaseRef(event.target.value);clearInput();}}/></label>
        <label>نوع اطلاعات شخصی<select value={scope} onChange={event=>{setScope(event.target.value);setPage(1);clearInput();}}>
          {schema.scopes.map(row=><option key={row.key} value={row.key}>{row.label}</option>)}
        </select></label>
        <p>صفحهٔ درخواستی: {faNumber(page)}؛ حداکثر {faNumber(schema.page_size)} ردیف. تغییر صفحه به تأیید تازه نیاز دارد.</p>
        <label><input type="checkbox" checked={ack} onChange={event=>setAck(event.target.checked)}/>درخواست واقعی پشتیبانی و مجوز بررسی همین کاربر را دارم.</label>
        <label>روش تأیید مشاهده<select value={method} onChange={event=>setMethod(event.target.value)}><option value="totp">TOTP</option><option value="recovery">کد بازیابی یک‌بارمصرف</option></select></label>
        <label>کد MFA مشاهدهٔ خصوصی<input type="password" autoComplete="one-time-code" maxLength={32} value={token} onChange={event=>setToken(event.target.value)}/></label>
        <button className="button primary" type="submit" disabled={!ack||!caseRef||!token.trim()}>مشاهدهٔ هدفمند با تأیید دومرحله‌ای</button>
      </fieldset>
    </form>
    {data&&<section className="card stack" aria-label="نتیجهٔ خصوصی پشتیبانی"><h2>نتیجهٔ محدود همین درخواست</h2>
      <p>زمان خواندن: {cmsDate(data.as_of)}؛ تعداد کل این نوع: {faNumber(data.count)}؛ صفحهٔ {faNumber(data.page)}</p>
      <p className="muted">این نما با پنهان‌شدن صفحه یا پس از پنج دقیقه پاک می‌شود. متن اطلاعات شخصی در تاریخچهٔ عملیات کپی نمی‌شود.</p>
      {!data.results.length?<CmsState empty="برای این کاربر و نوع اطلاعات، ردیفی ثبت نشده است."/>:data.results.map((row,index)=><article className="card stack" key={String(row.id??index)}>
        <StructuredValue value={Object.fromEntries(Object.entries(row).map(([key,value])=>[label(key),value]))}/>
      </article>)}
      <div className="cms-actions"><button className="button secondary" type="button" disabled={busy||page<=1} onClick={()=>{setPage(value=>value-1);clearInput();}}>صفحهٔ قبل</button>
        <button className="button secondary" type="button" disabled={busy||page*data.page_size>=data.count||page>=schema.max_page} onClick={()=>{setPage(value=>value+1);clearInput();}}>صفحهٔ بعد</button>
        <button className="button secondary" type="button" onClick={clearPrivate}>پاک‌کردن نتیجه از نما</button>
      </div>
    </section>}
  </div>;
}
