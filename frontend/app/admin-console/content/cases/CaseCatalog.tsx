"use client";
import {useEffect, useState, type FormEvent} from "react";
import {cms, CmsError, type CmsPage} from "@/lib/cms";

type Item={case_id:number;slug:string;title:string;is_active:boolean;
  current_revision_id:number|null;draft_revision_id:number|null;structure_mode:string};

export function CaseCatalog({canCreate,onPick,onBeforeCreate}:{
  canCreate:boolean;onPick:(caseId:number,revisionId:number,force?:boolean)=>Promise<void>;
  onBeforeCreate:()=>boolean;
}){
  const [page,setPage]=useState(1);
  const [rows,setRows]=useState<CmsPage<Item>>();
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [title,setTitle]=useState("");
  const [slug,setSlug]=useState("");
  const [summary,setSummary]=useState("");
  const [objective,setObjective]=useState("");
  const [difficulty,setDifficulty]=useState("introductory");
  const refresh=async(p=page)=>{
    setLoading(true);setError("");
    try{
      const response=await cms<CmsPage<Item>>("/cases/?page="+p+"&page_size=30");
      setRows(response.data);
    }catch(failure){setError(failure instanceof CmsError?failure.message:"فهرست کیس‌ها خوانده نشد.");}
    finally{setLoading(false);}
  };
  useEffect(()=>{void refresh(page);},[page]); // eslint-disable-line react-hooks/exhaustive-deps
  const create=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(busy||!canCreate||!onBeforeCreate())return;
    setBusy(true);setError("");
    try{
      const response=await cms<{case_id:number;revision_id:number}>("/cases/",{
        method:"POST",body:JSON.stringify({
          title,slug,patient_summary:summary,educational_objective:objective,difficulty,
        }),
      });
      setTitle("");setSlug("");setSummary("");setObjective("");
      await onPick(response.data.case_id,response.data.revision_id,true);
      await refresh(1);setPage(1);
    }catch(failure){setError(failure instanceof CmsError?failure.message:"ساخت پیش‌نویس جدید انجام نشد.");}
    finally{setBusy(false);}
  };
  const open=async(caseId:number,revisionId:number)=>{
    setBusy(true);setError("");
    try{await onPick(caseId,revisionId);}
    catch(failure){setError(failure instanceof CmsError?failure.message:"باز کردن نسخه انجام نشد.");}
    finally{setBusy(false);}
  };
  return <section className="card stack" aria-labelledby="case-catalog-title">
    <h2 id="case-catalog-title">فهرست کیس‌های آموزشی</h2>
    <p className="muted">نسخهٔ منتشرشده، پیش‌نویس باز و وضعیت دسترسی هر کیس جدا نمایش داده می‌شود.</p>
    {error&&<p role="alert">{error}</p>}
    {loading?<p role="status">در حال دریافت فهرست…</p>:
      <div className="stack">
        {rows?.results.length===0&&<p>هیچ کیسی ثبت نشده است.</p>}
        <ul>{rows?.results.map(item=><li key={item.case_id}>
          <strong>{item.title}</strong> <small dir="ltr">{item.slug} #{item.case_id}</small>
          <span> | {item.is_active?"فعال":"غیرفعال"} </span>
          {item.draft_revision_id!==null&&
            <button type="button" className="button secondary" disabled={busy}
              onClick={()=>open(item.case_id,item.draft_revision_id!)}>باز کردن Draft</button>}
          {item.current_revision_id!==null&&
            <button type="button" className="button secondary" disabled={busy}
              onClick={()=>open(item.case_id,item.current_revision_id!)}>نسخهٔ منتشرشده</button>}
        </li>)}</ul>
        {rows&&rows.count>rows.page_size&&<div className="cms-filters">
          <button type="button" className="button secondary" disabled={loading||page<=1}
            onClick={()=>setPage(page-1)}>صفحهٔ قبل</button>
          <span>صفحهٔ {page} از {Math.ceil(rows.count/rows.page_size)}</span>
          <button type="button" className="button secondary"
            disabled={loading||page*rows.page_size>=rows.count}
            onClick={()=>setPage(page+1)}>صفحهٔ بعد</button>
        </div>}
      </div>}
    {canCreate&&<details className="stack">
      <summary><strong>ایجاد کیس آموزشی جدید در حالت Draft</strong></summary>
      <form className="stack" onSubmit={create}>
        <p className="muted">این فرم کیس را غیرفعال و منتشرنشده می‌سازد. دادهٔ واقعی بیمار وارد نکنید.</p>
        <label>شناسهٔ مسیر انگلیسی
          <input type="text" pattern="[a-z0-9]+(-[a-z0-9]+)*" maxLength={160}
            required dir="ltr" value={slug} onChange={e=>setSlug(e.target.value)}/>
        </label>
        <label>عنوان آموزشی<input type="text" required maxLength={255}
          value={title} onChange={e=>setTitle(e.target.value)}/></label>
        <label>شرح کیس<textarea required maxLength={20000} rows={3}
          value={summary} onChange={e=>setSummary(e.target.value)}/></label>
        <label>هدف آموزشی<textarea rows={2} maxLength={20000}
          value={objective} onChange={e=>setObjective(e.target.value)}/></label>
        <label>سطح
          <select value={difficulty} onChange={e=>setDifficulty(e.target.value)}>
            <option value="introductory">مقدماتی</option>
            <option value="intermediate">متوسط</option>
            <option value="advanced">پیشرفته</option>
          </select>
        </label>
        <button type="submit" className="button" disabled={busy} aria-busy={busy}>
          {busy?"در حال ثبت…":"ساخت کیس و Draft اولیه"}
        </button>
      </form>
    </details>}
  </section>;
}
