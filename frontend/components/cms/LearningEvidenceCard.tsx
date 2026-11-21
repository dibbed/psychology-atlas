"use client";

import {useEffect,useRef,useState,type FormEvent} from "react";
import {cms, CmsError} from "@/lib/cms";
import {useCms} from "@/components/cms/CmsShell";

export type LearningEvidenceKind="quiz-question"|"flashcard"|"daily"|"distortions";
type Link={source_id:number;source_title:string|null;locator:string|null;
  source_verification_status:string;status:"linked"|"stale"|"restricted";reason:string|null};
type Evidence={kind:LearningEvidenceKind;item_id:number;revision:number;
  status:string;links:Link[];scientific_review:"unreviewed";
  publication_available:false;canonical_write:0;learner_write:0;content_digest:string};
type EditableLink={source_id:number;locator:string};
const label=(s:string)=>({
  linked:"پیوند ثبت‌شده (بدون تأیید مستقل)",stale:"نیازمند بازبینی شواهد",
  restricted:"منبع بایگانی یا محدودشده",
}[s]??s);
const message=(e:unknown)=>e instanceof CmsError?e.message:"بارگذاری یا ذخیرهٔ منبع انجام نشد.";

export function LearningEvidenceCard({kind,itemId,editable,blocked=false,refreshToken=0,onDirtyChange}:{
  kind:LearningEvidenceKind;itemId:number;editable:boolean;blocked?:boolean;
  refreshToken?:number;onDirtyChange?:(dirty:boolean)=>void;
}){
  const {can}=useCms();
  const authorized=can("cms_learning_view")&&can("cms_source_view");
  const canEdit=authorized&&can("cms_learning_edit")&&editable;
  const [evidence,setEvidence]=useState<Evidence>();
  const [etag,setEtag]=useState<string|null>(null);
  const [draft,setDraft]=useState<EditableLink[]>([]);
  const [sourceId,setSourceId]=useState("");
  const [locator,setLocator]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [changeReason,setChangeReason]=useState("");
  const [history,setHistory]=useState<{revisions:{
    revision:number;created_at:string;actor_id:number|null;status:string;
    fingerprint_version:string;change_reason:string;removed_source_ids:number[];links:Link[];
  }[];next_page:number|null;count:number}>();
  const [historyBusy,setHistoryBusy]=useState(false);
  const normalized=(rows:EditableLink[])=>JSON.stringify([...rows].sort(
    (a,b)=>a.source_id-b.source_id).map(row=>({source_id:row.source_id,locator:row.locator.trim()})));
  const linksChanged=Boolean(evidence)&&normalized(draft)!==
    normalized((evidence?.links??[]).map(row=>({source_id:row.source_id,locator:row.locator??""})));
  const dirty=linksChanged||Boolean(sourceId.trim()||locator.trim()||changeReason.trim());
  const errorRef=useRef<HTMLParagraphElement>(null);
  const requestStamp=useRef(0);
  const dirtyReporter=useRef(onDirtyChange);
  dirtyReporter.current=onDirtyChange;
  useEffect(()=>{
    dirtyReporter.current?.(dirty);
    return ()=>{if(dirty)dirtyReporter.current?.(false);};
  },[dirty]);
  const endpoint="/learning/evidence/"+kind+"/"+itemId+"/";
  useEffect(()=>{
    if(!authorized||dirty)return;
    let mounted=true;
    const stamp=++requestStamp.current;
    setEvidence(undefined);setEtag(null);setError("");setLoading(true);setBusy(false);
    setHistory(undefined);setChangeReason("");setSourceId("");setLocator("");
    void cms<Evidence>(endpoint).then(res=>{
      if(mounted&&stamp===requestStamp.current){
        setEvidence(res.data);setEtag(res.etag);setLoading(false);
        setDraft(res.data.links.map(link=>({source_id:link.source_id,locator:link.locator??""})));
      }
    }).catch(e=>{if(mounted&&stamp===requestStamp.current){setError(message(e));setLoading(false);}});
    return ()=>{mounted=false;requestStamp.current++;};
  },[authorized,endpoint,refreshToken]);
  useEffect(()=>{
    if(!dirty)return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",warn);
    return ()=>window.removeEventListener("beforeunload",warn);
  },[dirty]);
  useEffect(()=>{if(error)errorRef.current?.focus();},[error]);
  const refreshEvidence=async()=>{
    if(dirty&&!window.confirm("ویرایش ثبت‌نشدهٔ شواهد کنار گذاشته شود؟"))return;
    const stamp=++requestStamp.current;
    setBusy(true);setError("");
    try{
      const res=await cms<Evidence>(endpoint);
      if(stamp!==requestStamp.current)return;
      setEvidence(res.data);setEtag(res.etag);
      setDraft(res.data.links.map(link=>({source_id:link.source_id,locator:link.locator??""})));
      setChangeReason("");setSourceId("");setLocator("");setHistory(undefined);
    }catch(e){if(stamp===requestStamp.current)setError(message(e));}
    finally{if(stamp===requestStamp.current)setBusy(false);}
  };
  const loadHistory=async(page=1)=>{
    const stamp=requestStamp.current;
    setHistoryBusy(true);setError("");
    try{
      const res=await cms<NonNullable<typeof history>>(endpoint+"history/?page="+page);
      if(stamp!==requestStamp.current)return;
      setHistory(old=>page===1?res.data:{...res.data,revisions:[...(old?.revisions??[]),...res.data.revisions]});
    }catch(e){if(stamp===requestStamp.current)setError(message(e));}
    finally{if(stamp===requestStamp.current)setHistoryBusy(false);}
  };
  const add=()=>{
    const id=Number(sourceId);
    if(!Number.isSafeInteger(id)||id<1||!locator.trim()||locator.length>500||
       draft.some(link=>link.source_id===id)||draft.length>=10){
      setError("شناسهٔ منبع مثبت و یکتا و نشانی ادعا حداکثر ۵۰۰ نویسه لازم است.");return;
    }
    setDraft(old=>[...old,{source_id:id,locator:locator.trim()}]);
    setError("");setSourceId("");setLocator("");
  };
  const save=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();if(!canEdit||busy||blocked||!etag||!linksChanged||
      sourceId.trim()||locator.trim())return;
    const stamp=++requestStamp.current;
    setBusy(true);setError("");
    try{
      const result=await cms<Evidence>(endpoint,{method:"POST",headers:{"If-Match":etag},
        body:JSON.stringify({sources:draft,change_reason:changeReason.trim()})});
      if(stamp!==requestStamp.current)return;
      setEvidence(result.data);setEtag(result.etag);setHistory(undefined);setChangeReason("");
      setDraft(result.data.links.map(link=>({source_id:link.source_id,locator:link.locator??""})));
    }catch(e){if(stamp===requestStamp.current)setError(message(e));}
    finally{if(stamp===requestStamp.current)setBusy(false);}
  };
  if(!authorized)return <p className="muted">برای مشاهدهٔ منابع توضیح، مجوز مشاهدهٔ منابع لازم است.</p>;
  return <section className="card stack" aria-label="منابع توضیح آموزشی">
    <h3>منابع توضیح آموزشی</h3>
    <p className="muted">این پیوندها فقط شواهد خصوصی تألیف‌اند؛ ثبت منبع به معنی تأیید علمی، حق انتشار یا فعال‌سازی نیست.</p>
    {error&&<p role="alert" tabIndex={-1} ref={errorRef}>{error}</p>}
    {!evidence?<p role="status">{loading?"در حال دریافت وضعیت منبع...":"وضعیت منبع قابل دریافت نیست؛ مجوز یا اتصال را بررسی کنید."}</p>:<>
      <p role="status">وضعیت: {evidence.status==="unlinked"?"منبعی ثبت نشده":
        evidence.status==="requires_review"?"شواهد تغییرکرده یا محدود است":"منبع ثبت‌شده، بازبینی علمی انجام نشده"}
        {" | "}نسخهٔ شواهد: {evidence.revision}</p>
      <button className="button secondary" type="button" disabled={busy||blocked}
        onClick={()=>void refreshEvidence()}>بازخوانی وضعیت منبع و مجوزها</button>
      <ul>{evidence.links.map(link=><li key={link.source_id}>
        <strong>{link.source_title??"منبع محدود/تغییرکرده"} (#{link.source_id})</strong>
        {" | "}{label(link.status)}{" | "}<span dir="auto">{link.locator??"نشانی محدود شده"}</span>
        {link.reason&&<span> ({({SOURCE_ARCHIVED:"منبع بایگانی شده است",
          RIGHTS_RESTRICTED:"مجوز منبع محدود یا لغو شده است",
          SOURCE_OR_EXPLANATION_CHANGED:"متن منبع یا توضیح تغییر کرده و نیازمند بازبینی است",
        } as Record<string,string>)[link.reason]??"شواهد نیازمند بازبینی است"})</span>}
      </li>)}</ul>
      {canEdit?<form className="stack" onSubmit={save}>
        <fieldset className="stack" disabled={busy||blocked}>
          <legend>ویرایش پیوندهای قابل‌ردیابی</legend>
          <label>شناسهٔ SourceReference
            <input type="number" min={1} step={1} dir="ltr" value={sourceId}
              onChange={e=>setSourceId(e.target.value)}/></label>
          <label>محل دقیق ادعای پشتیبان در منبع
            <input maxLength={500} value={locator} onChange={e=>setLocator(e.target.value)}
              placeholder="صفحه، بخش یا شناسهٔ قابل‌ردیابی"/></label>
          <button className="button secondary" type="button" disabled={draft.length>=10}
            onClick={add}>افزودن منبع</button>
          {draft.map(link=><div key={link.source_id} className="stack">
            <span>منبع #{link.source_id}</span>
            <label>نشانی ادعا
              <input value={link.locator} maxLength={500}
                onChange={e=>setDraft(old=>old.map(row=>row.source_id===link.source_id?
                  {...row,locator:e.target.value}:row))}/>
            </label>
            <button className="button secondary" type="button"
              onClick={()=>setDraft(old=>old.filter(row=>row.source_id!==link.source_id))}>
              حذف از نسخهٔ جدید
            </button>
          </div>)}
          <label>دلیل تغییر یا حذف پیوند (در صورت حذف حتماً توضیح دهید)
            <textarea maxLength={500} rows={2} value={changeReason}
              onChange={e=>setChangeReason(e.target.value)}
              placeholder="مثلاً منبع فعلی دیگر پشتیبان ادعا نیست"/></label>
          <button type="submit" className="button" disabled={!linksChanged||busy||blocked||!etag||
            Boolean(sourceId.trim()||locator.trim())||
            (evidence.links.some(link=>!draft.some(row=>row.source_id===link.source_id))&&!changeReason.trim())}>
            ذخیرهٔ نسخهٔ جدید شواهد
          </button>
          {dirty&&<p role="status">تغییرات شواهد هنوز ذخیره نشده‌اند.
            {Boolean(sourceId.trim()||locator.trim())&&" ابتدا منبع واردشده را با دکمهٔ افزودن ثبت کنید."}
          </p>}
        </fieldset>
      </form>:<p className="muted">ویرایش پیوند فقط برای محتوای خصوصی با متن توضیح ثبت‌شده و بدون سابقهٔ یادگیرنده مجاز است؛ شواهد قبلی تغییر نمی‌کنند.</p>}
      <div className="stack">
        <button type="button" className="button secondary" disabled={historyBusy||busy}
          onClick={()=>void loadHistory(1)}>مشاهدهٔ تاریخچهٔ نسخه‌های شواهد</button>
        {history&&<section className="stack" aria-label="تاریخچهٔ شواهد">
          <p className="muted">تاریخچه فقط خواندنی است. وضعیت حقوق و نمایش نشانی منابع بر اساس مجوز جاری ارزیابی می‌شوند.</p>
          {history.revisions.length===0?<p>نسخه‌ای ثبت نشده است.</p>:
            <ol>{history.revisions.map(revision=><li key={revision.revision} className="stack">
              <strong>نسخه {revision.revision} | {revision.status==="requires_review"?"نیازمند بازبینی":revision.status==="unlinked"?"بدون پیوند":"منبع پیوست شده"}</strong>
              <span><bdi>{revision.created_at}</bdi> | ثبت‌کننده: {revision.actor_id??"نامشخص"}</span>
              <span>دلیل: {revision.change_reason}</span>
              {revision.removed_source_ids.length>0&&<span>پیوند حذف‌شده در این نسخه: {revision.removed_source_ids.join("، ")}</span>}
              <span>قرارداد: <code dir="ltr">{revision.fingerprint_version}</code></span>
              <ul>{revision.links.map(link=><li key={link.source_id}>
                منبع #{link.source_id} | {label(link.status)}
                {link.locator&&<> | <bdi>{link.locator}</bdi></>}
              </li>)}</ul>
            </li>)}</ol>}
          {history.next_page&&<button type="button" className="button secondary"
            disabled={historyBusy} onClick={()=>void loadHistory(history.next_page!)}>
            نمایش نسخه‌های بعدی
          </button>}
        </section>}
      </div>
    </>}
  </section>;
}
