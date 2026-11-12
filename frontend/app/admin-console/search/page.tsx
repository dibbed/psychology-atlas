"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {cms,CmsError,type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Kind="content_proposal"|"clinical_case"|"quiz"|"flashcard"|"source_reference"|"research_dataset"|"research_record"|"audit_event"|"review_task"|"admin_job"|"concept_alias"|"therapy_alias"|"technique_alias"|"psychologist_alias"|"theory_alias"|"brain_anatomical_alias"|"brain_network_alias"|"assessment_alias";
type Item={kind:Kind;resource_id:number|string;slug:string;is_active?:boolean;label?:string;review_kind?:string;review_state?:string;collection_kind?:string};
type Result=CmsPage<Item>&{scope:string;domain:string;query:string};
const target:Record<Kind,string>={
  content_proposal:"/admin-console/content/",
  clinical_case:"/admin-console/content/cases",
  quiz:"/admin-console/content/learning-quizzes",
  flashcard:"/admin-console/content/learning-flashcards",
  source_reference:"/admin-console/sources",
  research_dataset:"/admin-console/research/",
  research_record:"/admin-console/research/records/",
  audit_event:"/admin-console/audit/",
  review_task:"/admin-console/reviews/",
  admin_job:"/admin-console/jobs/",
  concept_alias:"/admin-console/content/concept-alias",
  therapy_alias:"/admin-console/content/therapy-alias",
  technique_alias:"/admin-console/content/technique-alias",
  psychologist_alias:"/admin-console/content/psychologist-alias",
  theory_alias:"/admin-console/content/theory-alias",
  brain_anatomical_alias:"/admin-console/content/brain-anatomical-alias",
  brain_network_alias:"/admin-console/content/brain-network-alias",
  assessment_alias:"/admin-console/content/assessment-alias",
};
const label:Record<Kind,string>={
  content_proposal:"پیشنهاد ویرایش نسخه‌مند",clinical_case:"کیس آموزشی",quiz:"آزمون آموزشی",flashcard:"فلش‌کارت",
  source_reference:"منبع پژوهشی",
  research_dataset:"مجموعه‌دادهٔ پژوهشی داخلی",
  research_record:"رکورد پژوهشی داخلی",
  audit_event:"رویداد Audit",
  review_task:"وظیفهٔ بازبینی",admin_job:"Job عملیاتی",
  concept_alias:"نام جایگزین مفهوم",therapy_alias:"نام جایگزین درمان",
  technique_alias:"نام جایگزین تکنیک",psychologist_alias:"نام جایگزین روان‌شناس",
  theory_alias:"نام جایگزین نظریه",brain_anatomical_alias:"نام جایگزین ساختار مغز",
  brain_network_alias:"نام جایگزین شبکهٔ مغز",assessment_alias:"نام جایگزین ابزار ارزیابی",
};
export default function PrivateSearch(){
  const {can}=useCms();const allowed=can("cms_search");
  const canCases=can("cms_cases_view"),canLearning=can("cms_learning_view"),canSources=can("cms_source_view");
  const canResearch=can("cms_research_view"),canAudit=can("cms_audit_view"),canOwner=can("cms_owner");
  const canAliases=["cms_core_view","cms_therapy_view","cms_history_view","cms_brain_view","cms_assessment_view"].some(cap=>can(cap));
  const canProposals=["cms_core_view","cms_dsm_view","cms_therapy_view","cms_history_view","cms_brain_view","cms_assessment_view"].some(cap=>can(cap));
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
      <p className="muted">جست‌وجوی داخلی شناسه‌ها و کلیدهای مجاز را بررسی می‌کند. Alias فقط با عبارت لاتین دقیق و مجوز همان حوزه، بدون نمایش متن یا نام والد پیدا می‌شود. پیشنهادهای ویرایش هم فقط با UUID دقیق و مجوز همان حوزه قابل‌یافتن‌اند. منبع با عنوان محدود یا شناسهٔ عددی دقیق، Audit و Task با شمارهٔ دقیق، و Job با UUID پیدا می‌شوند. متن بیمار، پاسخ، متن خام، جزئیات حساب و تاریخچهٔ یادگیری نمایش داده نمی‌شوند. نتیجه مجوز انتشار نیست.</p>
    </div>
    <form className="card stack" onSubmit={submit}>
      <label>شناسه یا کلید لاتین (Task و Audit: شماره، Job: UUID)
        <input type="search" dir="ltr" required pattern="[A-Za-z0-9-]{1,80}" minLength={["tasks","audit","sources","all"].includes(domain)?1:2} maxLength={80}
          value={term} onChange={e=>{clearResults();setTerm(e.target.value);}}/>
      </label>
      <label>حوزه
        <select value={domain} onChange={e=>{clearResults();setDomain(e.target.value);}}>
          <option value="all">تمام حوزه‌های مجاز من</option>
          {canProposals&&<option value="proposals">پیشنهادهای نسخه‌مند با UUID دقیق</option>}
          {canCases&&<option value="cases">کیس‌ها</option>}
          {canLearning&&<option value="learning">محتوای یادگیری</option>}
          {canSources&&<option value="sources">منابع مجاز</option>}
          {canResearch&&<option value="research">کلید مجموعه‌داده و رکورد پژوهشی</option>}
          {canAudit&&<option value="audit">شناسهٔ دقیق رویداد Audit</option>}
          {canAliases&&<option value="aliases">نام جایگزین، تطبیق لاتین دقیق</option>}
          {canOwner&&<option value="tasks">شناسهٔ دقیق وظیفهٔ بازبینی</option>}
          {canOwner&&<option value="jobs">UUID دقیق Job</option>}
        </select>
      </label>
      <button className="button" type="submit" disabled={busy||term.trim().length<(["tasks","audit","sources","all"].includes(domain)?1:2)}>جست‌وجو</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {busy&&<p role="status">در حال جست‌وجو…</p>}
    {data&&<section className="card stack">
      <h2>نتایج: {data.count.toLocaleString("fa-IR")}</h2>
      {data.results.length===0?<p>هیچ شناسهٔ مطابق پیدا نشد.</p>:
        <ul className="stack">{data.results.map(row=><li key={row.kind+"-"+row.resource_id}>
          <strong>{label[row.kind]}</strong> <code dir="ltr">{row.label??row.slug}</code>
          <span> | #{row.resource_id} {row.is_active!==undefined?` | ${row.is_active?"فعال":"غیرفعال"}`:" | وضعیت انتشار از این جست‌وجو تعیین نمی‌شود"} </span>
          <a className="cms-link" href={row.collection_kind?
            "/admin-console/content/"+encodeURIComponent(row.collection_kind):
            row.kind==="source_reference"?
              target.source_reference+"/"+encodeURIComponent(String(row.resource_id)):
            row.kind==="review_task"&&row.review_kind&&row.review_state?
              target.review_task+encodeURIComponent(row.review_kind)+"/"+encodeURIComponent(row.review_state):
              target[row.kind]+(row.kind==="research_dataset"||row.kind==="research_record"||row.kind==="audit_event"||row.kind==="admin_job"?row.resource_id:"")}>باز کردن حوزه برای بازرسی</a>
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
