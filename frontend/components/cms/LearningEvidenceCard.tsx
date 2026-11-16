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

export function LearningEvidenceCard({kind,itemId,editable,blocked=false}:{
  kind:LearningEvidenceKind;itemId:number;editable:boolean;blocked?:boolean;
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
  const [dirty,setDirty]=useState(false);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const errorRef=useRef<HTMLParagraphElement>(null);
  const endpoint="/learning/evidence/"+kind+"/"+itemId+"/";
  useEffect(()=>{
    if(!authorized)return;
    let mounted=true;
    setEvidence(undefined);setEtag(null);setDirty(false);setError("");setLoading(true);
    void cms<Evidence>(endpoint).then(res=>{
      if(mounted){
        setEvidence(res.data);setEtag(res.etag);setLoading(false);
        setDraft(res.data.links.map(link=>({source_id:link.source_id,locator:link.locator??""})));
      }
    }).catch(e=>{if(mounted){setError(message(e));setLoading(false);}});
    return ()=>{mounted=false;};
  },[authorized,endpoint]);
  useEffect(()=>{
    if(!dirty)return;
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",warn);
    return ()=>window.removeEventListener("beforeunload",warn);
  },[dirty]);
  useEffect(()=>{if(error)errorRef.current?.focus();},[error]);
  const refreshEvidence=async()=>{
    if(dirty&&!window.confirm("ویرایش ثبت‌نشدهٔ شواهد کنار گذاشته شود؟"))return;
    setBusy(true);setError("");
    try{
      const res=await cms<Evidence>(endpoint);
      setEvidence(res.data);setEtag(res.etag);
      setDraft(res.data.links.map(link=>({source_id:link.source_id,locator:link.locator??""})));
      setDirty(false);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const add=()=>{
    const id=Number(sourceId);
    if(!Number.isSafeInteger(id)||id<1||!locator.trim()||locator.length>500||
       draft.some(link=>link.source_id===id)||draft.length>=10){
      setError("شناسهٔ منبع مثبت و یکتا و نشانی ادعا حداکثر ۵۰۰ نویسه لازم است.");return;
    }
    setDraft(old=>[...old,{source_id:id,locator:locator.trim()}]);
    setDirty(true);setError("");setSourceId("");setLocator("");
  };
  const save=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();if(!canEdit||busy||blocked||!etag||!dirty)return;
    setBusy(true);setError("");
    try{
      const result=await cms<Evidence>(endpoint,{method:"POST",headers:{"If-Match":etag},
        body:JSON.stringify({sources:draft})});
      setEvidence(result.data);setEtag(result.etag);setDirty(false);
      setDraft(result.data.links.map(link=>({source_id:link.source_id,locator:link.locator??""})));
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
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
                onChange={e=>{setDraft(old=>old.map(row=>row.source_id===link.source_id?
                  {...row,locator:e.target.value}:row));setDirty(true);}}/>
            </label>
            <button className="button secondary" type="button"
              onClick={()=>{setDraft(old=>old.filter(row=>row.source_id!==link.source_id));setDirty(true);}}>
              حذف از نسخهٔ جدید
            </button>
          </div>)}
          <button type="submit" className="button" disabled={!dirty||busy||blocked||!etag}>
            ذخیرهٔ نسخهٔ جدید شواهد
          </button>
          {dirty&&<p role="status">تغییرات شواهد هنوز ذخیره نشده‌اند.</p>}
        </fieldset>
      </form>:<p className="muted">ویرایش پیوند فقط برای محتوای خصوصی با متن توضیح ثبت‌شده و بدون سابقهٔ یادگیرنده مجاز است؛ شواهد قبلی تغییر نمی‌کنند.</p>}
    </>}
  </section>;
}
