"use client";
import {useMemo, useState, type FormEvent} from "react";
import {cms, CmsError} from "@/lib/cms";
import type {InspectorGraph} from "./CaseGraphForm";

type SimulationGraph=InspectorGraph & {valid:boolean;issues:string[]};
type Result={
  completed:boolean;preview_only:true;awarded_score:number;max_score:number;
  trace:{step_id:number;title:string;kind:string;feedback:string;
    selected_choice_id:number|null;awarded_score:number;max_score:number}[];
};
type Hop={step:number;title:string;kind:string;selected:number|null;choices:{id:number;text:string}[]};

function route(graph:SimulationGraph,picks:Record<string,number>):{hops:Hop[];choices:number[];ready:boolean;error:string}{
  const hops:Hop[]=[];const chosen:number[]=[];let stepId=graph.entry_step_id;
  const visited=new Set<number>();
  for(let n=0;n<=graph.steps.length;n++){
    if(stepId===null)return {hops,choices:chosen,ready:true,error:""};
    const step=graph.steps.find(s=>s.id===stepId && s.is_active);
    if(!step)return {hops,choices:chosen,ready:false,error:"مرحله معتبر نیست."};
    if(visited.has(stepId))return {hops,choices:chosen,ready:false,error:"دور در مسیر مشاهده شد."};
    visited.add(stepId);
    const hop:Hop={step:stepId,title:step.title||step.stable_key,kind:step.node_kind,
      selected:null,choices:[]};
    if(step.node_kind==="terminal"){hops.push(hop);return {hops,choices:chosen,ready:true,error:""};}
    if(step.node_kind==="decision"){
      const q=graph.questions.find(q=>q.step_id===stepId && q.is_active);
      hop.choices=graph.choices.filter(c=>c.question_id===q?.id&&c.is_active)
        .map(c=>({id:c.id,text:c.text}));
      const selected=picks[String(stepId)];
      hop.selected=selected??null;
      hops.push(hop);
      if(!selected)return {hops,choices:chosen,ready:false,error:""};
      const choice=hop.choices.find(c=>c.id===selected);
      if(!choice)return {hops,choices:chosen,ready:false,error:"گزینه انتخاب‌شده در این مسیر معتبر نیست."};
      chosen.push(selected);
      const transition=graph.transitions.find(t=>t.source_step_id===stepId&&t.choice_id===selected&&t.is_active);
      if(!transition)return {hops,choices:chosen,ready:false,error:"انتقال برای این گزینه تعریف نشده است."};
      if(transition.outcome==="complete")return {hops,choices:chosen,ready:true,error:""};
      stepId=transition.target_step_id;
    }else{
      hops.push(hop);
      const transition=graph.transitions.find(t=>t.source_step_id===stepId&&t.choice_id===null&&t.is_active);
      if(!transition)return {hops,choices:chosen,ready:false,error:"انتقال خودکار تعریف نشده است."};
      if(transition.outcome==="complete")return {hops,choices:chosen,ready:true,error:""};
      stepId=transition.target_step_id;
    }
  }
  return {hops,choices:chosen,ready:false,error:"حداکثر طول مسیر رعایت نشده است."};
}

export function CaseSimulation({graph}: {graph:SimulationGraph}){
  const [picks,setPicks]=useState<Record<string,number>>({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [result,setResult]=useState<Result>();
  const path=useMemo(()=>route(graph,picks),[graph,picks]);
  const run=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(!graph.valid||!path.ready||busy)return;
    setError("");setResult(undefined);setBusy(true);
    try{
      const response=await cms<Result>(
        "/cases/"+graph.case_id+"/revisions/"+graph.revision_id+"/simulate/",
        {method:"POST",body:JSON.stringify({choice_ids:path.choices})});
      setResult(response.data);
    }catch(failure){setError(failure instanceof CmsError?failure.message:"مسیر شبیه‌سازی معتبر نیست.");}
    finally{setBusy(false);}
  };
  return <section className="card stack" aria-labelledby="simulation-title">
    <h2 id="simulation-title">شبیه‌سازی مسیر آموزشی (بدون ذخیرهٔ پیشرفت)</h2>
    <p className="muted">انتخاب‌ها فقط در این صفحه استفاده می‌شوند. نتیجه آزمون بالینی، نمرهٔ واقعی دانشجو یا تأیید علمی نیست.</p>
    {!graph.valid?<p role="alert">تا برطرف‌شدن خطاهای ساختاری گراف، شبیه‌سازی انجام نمی‌شود.</p>:
      <form onSubmit={run} className="stack">
        <ol>{path.hops.map(h=><li key={h.step}>
          <strong>{h.title}</strong> <small>({h.kind})</small>
          {h.kind==="decision"&&<label>انتخاب مسیر این گام
            <select value={h.selected??""} required onChange={e=>{
              setPicks(old=>({...old,[String(h.step)]:Number(e.target.value)}));
              setResult(undefined);
            }}>
              <option value="">انتخاب کنید</option>
              {h.choices.map(c=><option key={c.id} value={c.id}>{c.text}</option>)}
            </select>
          </label>}
        </li>)}</ol>
        {path.error&&<p role="alert">{path.error}</p>}
        <button className="button secondary" type="submit"
          disabled={busy||!path.ready} aria-busy={busy}>{busy?"در حال بررسی…":"اجرای شبیه‌سازی بدون ثبت سابقه"}</button>
      </form>}
    {error&&<p role="alert">{error}</p>}
    {result&&<div className="stack" role="status" aria-live="polite">
      <p><strong>شبیه‌سازی تکمیل شد.</strong> امتیاز فرضی مسیر: {result.awarded_score} از {result.max_score}</p>
      <ol>{result.trace.map((event,i)=><li key={i}>
        {event.title}: {event.awarded_score!==0?"امتیاز "+event.awarded_score:""}
        {event.feedback&&<p>{event.feedback}</p>}
      </li>)}</ol>
      <p className="muted">هیچ تلاش، فعالیت یا نتیجهٔ یادگیری واقعی ثبت نشد.</p>
    </div>}
  </section>;
}
