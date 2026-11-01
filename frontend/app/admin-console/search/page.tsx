"use client";
import {useState,type FormEvent} from "react";
import {cms,CmsError,type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Kind="clinical_case"|"quiz"|"flashcard"|"source_reference";
type Item={kind:Kind;resource_id:number;slug:string;is_active?:boolean;label?:string};
type Result=CmsPage<Item>&{scope:string;domain:string;query:string};
const target:Record<Kind,string>={
  clinical_case:"/admin-console/content/cases",
  quiz:"/admin-console/content/learning-quizzes",
  flashcard:"/admin-console/content/learning-flashcards",
  source_reference:"/admin-console/sources",
};
const label:Record<Kind,string>={
  clinical_case:"کیس آموزشی",quiz:"آزمون آموزشی",flashcard:"فلش‌کارت",
  source_reference:"منبع پژوهشی",
};
export default function PrivateSearch(){
  const {can}=useCms();const allowed=can("cms_search");
  const canCases=can("cms_cases_view"),canLearning=can("cms_learning_view"),canSources=can("cms_source_view");
  const [term,setTerm]=useState("");const [domain,setDomain]=useState("all");
  const [page,setPage]=useState(1);const [data,setData]=useState<Result>();
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const query=async(nextPage:number)=>{
    if(busy||!allowed)return;
    setBusy(true);setError("");
    try{
      const params=new URLSearchParams({q:term.trim(),domain,page:String(nextPage),page_size:"30"});
      const res=await cms<Result>("/search/?"+params.toString());
      setData(res.data);setPage(nextPage);
    }catch(e){setError(e instanceof CmsError?e.message:"جست‌وجو انجام نشد.");setData(undefined);}
    finally{setBusy(false);}
  };
  const submit=(event:FormEvent<HTMLFormElement>)=>{event.preventDefault();void query(1);};
  if(!allowed)return <CmsState empty="برای جست‌وجوی داخلی به مجوز مستقل cms_search نیاز است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title">
      <p className="eyebrow">P17 | Internal Search</p><h1>جست‌وجوی خصوصی محتوای مجاز</h1>
      <p className="muted">این جست‌وجوی خصوصی، شناسهٔ لاتین Quiz، Flashcard و Case و عنوان منابع مجاز را بررسی می‌کند. متن بیمار، پاسخ، ایمیل، سوابق یادگیری و متن استناد نمایش داده نمی‌شوند. نتیجهٔ منبع به معنی تأیید علمی یا مجوز انتشار نیست.</p>
    </div>
    <form className="card stack" onSubmit={submit}>
      <label>بخشی از شناسهٔ لاتین
        <input type="search" dir="ltr" required pattern="[A-Za-z0-9-]{2,80}" maxLength={80}
          value={term} onChange={e=>setTerm(e.target.value)}/>
      </label>
      <label>حوزه
        <select value={domain} onChange={e=>setDomain(e.target.value)}>
          <option value="all">تمام حوزه‌های مجاز من</option>
          {canCases&&<option value="cases">کیس‌ها</option>}
          {canLearning&&<option value="learning">محتوای یادگیری</option>}
          {canSources&&<option value="sources">منابع مجاز</option>}
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
          <a className="cms-link" href={target[row.kind]}>باز کردن حوزه برای بازرسی</a>
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
