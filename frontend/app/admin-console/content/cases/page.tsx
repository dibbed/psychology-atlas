"use client";
import {useEffect, useState, type FormEvent} from "react";
import {cms} from "@/lib/cms";
import {CmsState, useCms} from "@/components/cms/CmsShell";
import {CaseGraphForm} from "./CaseGraphForm";
import {CaseSimulation} from "./CaseSimulation";
import {CaseCatalog} from "./CaseCatalog";
import {CaseRevisionHistory} from "./CaseRevisionHistory";
import {CaseValidation} from "./CaseValidation";
import {CasePublicationWorkflow} from "./CasePublicationWorkflow";

type Step = {id:number;stable_key:string;node_kind:string;title:string;narrative:string;sort_order:number;is_active:boolean};
type Edge = {id:number;source_step_id:number;choice_id:number|null;target_step_id:number|null;outcome:string;is_active:boolean};
type Question = {id:number;step_id:number;scoring_dimension_id:number|null;prompt:string;explanation:string;is_active:boolean};
type Choice = {id:number;question_id:number;text:string;score_value:number;feedback:string;is_active:boolean};
type Graph = {case_id:number;revision_id:number;revision_version:number;revision_status:string;rubric_version:number;
  current_revision_id:number|null;revision_digest:string;entry_step_id:number|null;title:string;patient_summary:string;
  educational_objective:string;valid:boolean;issues:string[];steps:Step[];transitions:Edge[];
  questions:Question[];choices:Choice[];scoring_dimensions:{id:number;stable_key:string;label:string;description:string;is_active:boolean}[];
  publication_available:false;simulation_creates_attempt:false};

export default function CaseGraphInspector(){
  const {can}=useCms();
  const permitted=can("cms_cases_view")&&can("cms_cases_preview");
  const [caseId,setCaseId]=useState("");
  const [revId,setRevId]=useState("");
  const [graph,setGraph]=useState<Graph>();
  const [error,setError]=useState<unknown>();
  const [busy,setBusy]=useState(false);
  const [graphDirty,setGraphDirty]=useState(false);
  const [etag,setEtag]=useState<string|null>(null);
  const [title,setTitle]=useState("");
  const [summary,setSummary]=useState("");
  const [objective,setObjective]=useState("");
  const metadataDirty=!!graph&&(title!==graph.title||summary!==graph.patient_summary||objective!==graph.educational_objective);
  const allowLeave=()=>!(graphDirty||metadataDirty)||window.confirm("تغییرهای ذخیره‌نشدهٔ پیش‌نویس از دست می‌روند. از این نسخه خارج می‌شوید؟");
  useEffect(()=>{
    if(!graphDirty&&!metadataDirty)return;
    const guard=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",guard);
    return ()=>window.removeEventListener("beforeunload",guard);
  },[graphDirty,metadataDirty]);
  const inspect=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();
    if(!allowLeave())return;
    setError(undefined);setGraph(undefined);setEtag(null);
    if(!permitted||!/^[1-9][0-9]*$/.test(caseId)||!/^[1-9][0-9]*$/.test(revId))return;
    setBusy(true);
    try{
      const response=await cms<Graph>("/cases/"+caseId+"/revisions/"+revId+"/graph/");
      setGraph(response.data);setEtag(response.etag);
      setTitle(response.data.title);setSummary(response.data.patient_summary);
      setObjective(response.data.educational_objective);
    }catch(failure){setError(failure);}
    finally{setBusy(false);}
  };
  const reload=async(id:number,forCase=caseId,force=false)=>{
    if(!force&&!allowLeave())return;
    const response=await cms<Graph>("/cases/"+forCase+"/revisions/"+id+"/graph/");
    setGraphDirty(false);
    setCaseId(String(forCase));setRevId(String(id));setGraph(response.data);setEtag(response.etag);
    setTitle(response.data.title);setSummary(response.data.patient_summary);
    setObjective(response.data.educational_objective);
  };
  const clone=async()=>{
    if(!graph||!etag||!can("cms_cases_create")||busy)return;
    setBusy(true);setError(undefined);
    try{
      const result=await cms<{revision_id:number}>(
        "/cases/"+graph.case_id+"/revisions/"+graph.revision_id+"/clone/",
        {method:"POST",headers:{"If-Match":etag},body:"{}"});
      await reload(result.data.revision_id,String(graph.case_id));
    }catch(failure){setError(failure);}
    finally{setBusy(false);}
  };
  const saveMetadata=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(!graph||!etag||graph.revision_status!=="draft"||!can("cms_cases_edit")||busy)return;
    if(graphDirty&&!window.confirm("ساختار گراف ذخیره‌نشده است. با ذخیرهٔ اطلاعات کیس، آن ویرایش‌ها از دست می‌روند. ادامه می‌دهید؟"))return;
    setBusy(true);setError(undefined);
    try{
      await cms("/cases/"+graph.case_id+"/revisions/"+graph.revision_id+"/metadata/",{
        method:"POST",headers:{"If-Match":etag},
        body:JSON.stringify({title,patient_summary:summary,educational_objective:objective}),
      });
      await reload(graph.revision_id,String(graph.case_id),true);
    }catch(failure){setError(failure);}
    finally{setBusy(false);}
  };
  if(!permitted)return <CmsState empty="برای بررسی کیس، مجوز اختصاصی پیش‌نمایش لازم است."/>;
  const stepNames=new Map(graph?.steps.map(step=>[step.id,step.title||step.stable_key])??[]);
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console/content">بازگشت به محتوای مرجع</a>
    <div className="cms-title"><p className="eyebrow">CaseRevision | P12</p>
      <h1>بازرسی گراف کیس آموزشی</h1>
      <p className="muted">بررسی خصوصی هر نسخهٔ کیس بدون ایجاد تلاش دانشجو، امتیاز، فعالیت یا انتشار.</p>
    </div>
    <CaseCatalog canCreate={can("cms_cases_create")}
      onBeforeCreate={allowLeave}
      onPick={(selectedCase,selectedRevision,force)=>reload(selectedRevision,String(selectedCase),force)}/>
    <section className="card stack">
      <h2>انتخاب کیس و نسخه با شناسه</h2>
      <form className="cms-filters" onSubmit={inspect}>
        <label htmlFor="case-id">شناسهٔ Case
          <input id="case-id" type="number" min="1" step="1" required value={caseId} onChange={e=>setCaseId(e.target.value)}/>
        </label>
        <label htmlFor="revision-id">شناسهٔ CaseRevision
          <input id="revision-id" type="number" min="1" step="1" required value={revId} onChange={e=>setRevId(e.target.value)}/>
        </label>
        <button className="button secondary" type="submit" disabled={busy} aria-busy={busy}>{busy?"در حال بررسی…":"نمایش نسخه"}</button>
      </form>
      <p className="muted">ساخت و ویرایش Draft، شامل گراف شاخه‌ای و شبیه‌سازی بی‌اثر آموزشی فعال است. انتشار همچنان نیازمند گیت مستقل است.</p>
    </section>
    {error!=null&&<div role="alert"><CmsState error={error} retry={()=>setError(undefined)}/></div>}
    {graph&&<div className="stack" role="region" aria-label="گراف نسخهٔ کیس">
      <section className="card stack" aria-live="polite">
        <h2>{graph.title||"کیس بدون عنوان"} | نسخهٔ {graph.revision_version}</h2>
        <p>وضعیت: {graph.revision_status} | نسخهٔ جاری: {graph.current_revision_id??"ندارد"}</p>
        <p>{graph.patient_summary}</p><p>{graph.educational_objective}</p>
        <p><strong>{graph.valid?"اعتبار ساختاری: بدون خطا":"خطاهای ساختاری وجود دارد"}</strong></p>
        {!graph.valid&&<ul>{graph.issues.map((issue,index)=><li key={index}><code dir="ltr">{issue}</code></li>)}</ul>}
        <p className="muted">پیش‌نمایش به‌معنی تأیید علمی یا مجوز انتشار نیست. انتشار پویا در P16 انجام می‌شود.</p>
        {graph.revision_status==="published"&&graph.current_revision_id===graph.revision_id&&can("cms_cases_create")&&
          <button className="button secondary" type="button" onClick={clone} disabled={busy||!etag}>
            {busy?"در حال آماده‌سازی…":"ساخت پیش‌نویس مستقل از این نسخه"}
          </button>}
      </section>
      <CaseRevisionHistory caseId={graph.case_id} selectedId={graph.revision_id}
        onPick={revision=>reload(revision,String(graph.case_id))}/>
      {graph.revision_status==="draft"&&can("cms_cases_edit")&&
        <section className="card stack" aria-labelledby="draft-metadata">
          <h2 id="draft-metadata">ویرایش اطلاعات پیش‌نویس</h2>
          <p className="muted">ویرایش فقط روی همین Draft ثبت می‌شود. نسخهٔ منتشرشده و تلاش‌های دانشجویان تغییری نمی‌کنند.</p>
          <form className="stack" onSubmit={saveMetadata}>
            <label htmlFor="draft-title">عنوان<input id="draft-title" required maxLength={255} disabled={busy} value={title} onChange={e=>setTitle(e.target.value)}/></label>
            <label htmlFor="draft-summary">خلاصهٔ کیس<textarea id="draft-summary" required maxLength={20000} rows={4} disabled={busy} value={summary} onChange={e=>setSummary(e.target.value)}/></label>
            <label htmlFor="draft-objective">هدف آموزشی<textarea id="draft-objective" maxLength={20000} rows={3} disabled={busy} value={objective} onChange={e=>setObjective(e.target.value)}/></label>
            <button className="button secondary" type="submit" disabled={busy||!etag}>{busy?"در حال ذخیره…":"ذخیرهٔ اطلاعات پیش‌نویس"}</button>
          </form>
        </section>}
      {graph.revision_status==="draft"&&can("cms_cases_edit")&&etag&&
        <CaseGraphForm key={graph.revision_id+"-"+etag} graph={graph} etag={etag}
          onDirtyChange={setGraphDirty} onSaved={()=>reload(graph.revision_id,String(graph.case_id),true)}/>}
      {can("cms_cases_validate")&&<CaseValidation key={"validation-"+graph.revision_id+"-"+etag}
        caseId={graph.case_id} revisionId={graph.revision_id}/>}
      <CaseSimulation key={"simulation-"+graph.revision_id+"-"+etag} graph={graph}/>
      {can("cms_cases_validate")&&<CasePublicationWorkflow key={"publication-"+graph.revision_id}
        caseId={graph.case_id} revisionId={graph.revision_id} etag={etag}
        digest={graph.revision_digest} status={graph.revision_status}
        onPublished={()=>reload(graph.revision_id,String(graph.case_id),true)}/> }
      <section className="stack" aria-label="نمای گراف ذخیره‌شده">
      <h2>مراحل ({graph.steps.length})</h2>
      {graph.steps.length===0&&<CmsState empty="مرحله‌ای برای این نسخه وجود ندارد."/>}
      {graph.steps.map(step=><details key={step.id} className="card stack" open={step.id===graph.entry_step_id}>
        <summary><strong>{step.title||step.stable_key}</strong> <small>#{step.id} | {step.node_kind} {step.id===graph.entry_step_id?"| شروع":""}</small></summary>
        <p>{step.narrative}</p>
        {graph.questions.filter(q=>q.step_id===step.id).map(q=><div className="stack" key={q.id}>
          <h3>پرسش #{q.id}</h3><p>{q.prompt}</p>
          <ol>{graph.choices.filter(c=>c.question_id===q.id).map(c=><li key={c.id}>{c.text} <small>امتیاز آموزشی: {c.score_value}</small></li>)}</ol>
        </div>)}
        <h3>انتقال‌ها</h3>
        <ul>{graph.transitions.filter(t=>t.source_step_id===step.id).map(t=><li key={t.id}>
          {t.choice_id?"گزینهٔ #"+t.choice_id:"خودکار"}: {t.outcome==="complete"?"پایان":stepNames.get(t.target_step_id??-1)??"نامشخص"}
        </li>)}</ul>
      </details>)}
      </section>
    </div>}
  </div>;
}
