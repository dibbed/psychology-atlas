"use client";
import {useEffect, useState} from "react";
import {cms, CmsError, type CmsPage} from "@/lib/cms";

type Version={
  revision_id:number;version:number;status:string;title:string;
  content_hash:string;published_at:string|null;entry_step_id:number|null;
  rubric_version:number;attempt_count:number;
};
type History=CmsPage<Version> & {case_id:number;current_revision_id:number|null};
export function CaseRevisionHistory({caseId,selectedId,onPick}:{
  caseId:number;selectedId:number;onPick:(revisionId:number)=>Promise<void>;
}){
  const [page,setPage]=useState(1);
  const [data,setData]=useState<History>();
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let active=true;
    void cms<History>("/cases/"+caseId+"/revisions/?page="+page+"&page_size=30")
      .then(r=>{if(active){setData(r.data);setError("");}})
      .catch(e=>{if(active)setError(e instanceof CmsError?e.message:"تاریخچهٔ نسخه‌ها در دسترس نیست.");});
    return ()=>{active=false;};
  },[caseId,page,selectedId]);
  const inspect=async(revisionId:number)=>{
    setBusy(true);setError("");
    try{await onPick(revisionId);}
    catch(e){setError(e instanceof CmsError?e.message:"این نسخه باز نشد.");}
    finally{setBusy(false);}
  };
  return <section className="card stack" aria-labelledby="case-versions-title">
    <h2 id="case-versions-title">تاریخچهٔ نسخه‌ها و حفاظت attempt</h2>
    <p className="muted">تعداد تلاش‌ها فقط آمار تجمیعی است؛ هویت یادگیرندگان اینجا نمایش داده نمی‌شود. پیش‌نویس جایگزین نسخهٔ جاری نشده است.</p>
    {error&&<p role="alert">{error}</p>}
    {!data&&!error&&<p role="status">در حال دریافت تاریخچه…</p>}
    {data&&<ul className="stack">{data.results.map(item=><li key={item.revision_id}>
      <strong>نسخهٔ {item.version}</strong> | {item.status} |
      {item.revision_id===data.current_revision_id?" نسخهٔ جاری":""}
      <span> | تلاش‌های ثبت‌شده: {item.attempt_count}</span>
      <button className="button secondary" type="button" disabled={busy||item.revision_id===selectedId}
        onClick={()=>inspect(item.revision_id)}>بازرسی همین نسخه</button>
      {item.published_at&&<small> | انتشار ثبت‌شده: {item.published_at}</small>}
    </li>)}</ul>}
    {data&&data.count>data.page_size&&<div className="cms-filters">
      <button type="button" className="button secondary" onClick={()=>setPage(Math.max(1,page-1))}
        disabled={page<=1}>قبل</button>
      <span>صفحهٔ {page}</span>
      <button type="button" className="button secondary" onClick={()=>setPage(page+1)}
        disabled={page*data.page_size>=data.count}>بعد</button>
    </div>}
  </section>;
}
