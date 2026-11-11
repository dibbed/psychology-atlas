"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {cms,CmsError,type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Kind="clinical_case"|"quiz"|"flashcard"|"source_reference"|"research_dataset"|"research_record"|"audit_event";
type Item={kind:Kind;resource_id:number;slug:string;is_active?:boolean;label?:string};
type Result=CmsPage<Item>&{scope:string;domain:string;query:string};
const target:Record<Kind,string>={
  clinical_case:"/admin-console/content/cases",
  quiz:"/admin-console/content/learning-quizzes",
  flashcard:"/admin-console/content/learning-flashcards",
  source_reference:"/admin-console/sources",
  research_dataset:"/admin-console/research/",
  research_record:"/admin-console/research/records/",
  audit_event:"/admin-console/audit/",
};
const label:Record<Kind,string>={
  clinical_case:"کیس آموزشی",quiz:"آزمون آموزشی",flashcard:"فلش‌کارت",
  source_reference:"منبع پژوهشی",
  research_dataset:"مجموعه‌دادهٔ پژوهشی داخلی",
  research_record:"رکورد پژوهشی داخلی",
  audit_event:"رویداد Audit",
};
export default function PrivateSearch(){
  const {can}=useCms();const allowed=can("cms_search");
  const canCases=can("cms_cases_view"),canLearning=can("cms_learning_view"),canSources=can("cms_source_view");
  const canResearch=can("cms_research_view"),canAudit=can("cms_audit_view");
  const [term,setTerm]=useState("");const [domain,setDomain]=useState("all");
  const [page,setPage]=useState(1);const [data,setData]=useState<Result>();
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const requestGeneration=useRef(0);
  useEffect(()=>()=>{requestGeneration.current++;},[]);
  const clearResults=()=>{
    requestGeneration.current++;
    setData(undefined);setError("");setBusy(false);setPage(1);
  };
  const query=async(nextPage:number)=>{
    if(busy||!allowed)return;
    const generation=++requestGeneration.current;
    setBusy(true);setError("");
    try{
      const params=new URLSearchParams({q:term.trim(),domain,page:String(nextPage),page_size:"30"});
      const res=await cms<Result>("/search/?"+params.toString());
      if(generation!==requestGeneration.current)return;
      setData(res.data);setPage(nextPage);
    }catch(e){
      if(generation!==requestGeneration.current)return;
      setError(e instanceof CmsError?e.message:"جست‌وجو انجام نشد.");setData(undefined);
    }finally{if(generation===requestGeneration.current)setBusy(false);}
  };
  const submit=(event:FormEvent<HTMLFormElement>)=>{event.preventDefault();void query(1);};
  if(!allowed)return <CmsState empty="برای جست‌وجوی داخلی به مجوز مستقل cms_search نیاز است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title">
      <p className="eyebrow">P17 | Internal Search</p><h1>جست‌وجوی خصوصی محتوای مجاز</h1>
      <p className="muted">جست‌وجوی خصوصی فقط شناسه‌ها و کلیدهای مجاز کیس، محتوای آموزشی و رکوردهای پژوهشی را بررسی می‌کند؛ منبع با عنوان محدود و Audit فقط با شمارهٔ دقیق رویداد پیدا می‌شود. متن بیمار، پاسخ، متن خام مجموعه‌داده، جزئیات حساب و سوابق یادگیری جست‌وجو یا نمایش داده نمی‌شوند. نتیجه مجوز انتشار نیست.</p>
    </div>
    <form className="card stack" onSubmit={submit}>
      <label>شناسه یا کلید لاتین (برای Audit شمارهٔ دقیق)
        <input type="search" dir="ltr" required pattern="[A-Za-z0-9-]{2,80}" maxLength={80}
          value={term} onChange={e=>{clearResults();setTerm(e.target.value);}}/>
      </label>
      <label>حوزه
        <select value={domain} onChange={e=>{clearResults();setDomain(e.target.value);}}>
          <option value="all">تمام حوزه‌های مجاز من</option>
          {canCases&&<option value="cases">کیس‌ها</option>}
          {canLearning&&<option value="learning">محتوای یادگیری</option>}
          {canSources&&<option value="sources">منابع مجاز</option>}
          {canResearch&&<option value="research">کلید مجموعه‌داده و رکورد پژوهشی</option>}
          {canAudit&&<option value="audit">شناسهٔ دقیق رویداد Audit</option>}
        </select>
      </label>
      <button className="button" type="submit" disabled={busy||term.trim().length<2}>جست‌وجو</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {busy&&<p role="status">در حال جست‌وجو…</p>}
    {data&&<section className="card stack">
      <h2>نتایج: {data.count.toLocaleString("fa-IR")}</h2>
      {data.results.length===0?<p>هیچ شناسهٔ مطابق پیدا نشد.</p>:
        <ul className="stack">{data.results.map(row=><li key={row.kind+"-"+row.resource_id}>
          <strong>{label[row.kind]}</strong> <code dir="ltr">{row.label??row.slug}</code>
          <span> | #{row.resource_id} {row.is_active!==undefined?` | ${row.is_active?"فعال":"غیرفعال"}`:" | وضعیت انتشار از این جست‌وجو تعیین نمی‌شود"} </span>
          <a className="cms-link" href={target[row.kind]+(
            row.kind==="research_dataset"||row.kind==="research_record"||row.kind==="audit_event"?
              row.resource_id:"")}>باز کردن حوزه برای بازرسی</a>
        </li>)}</ul>}
      {data.count>data.page_size&&<div className="cms-filters">
        <button className="button secondary" type="button" disabled={busy||page<=1}
          onClick={()=>void query(page-1)}>قبل</button>
        <span>صفحهٔ {page} از {Math.ceil(data.count/data.page_size)}</span>
        <button className="button secondary" type="button" disabled={busy||page*data.page_size>=data.count}
          onClick={()=>void query(page+1)}>بعد</button>
      </div>}
    </section>}
  </div>;
}
