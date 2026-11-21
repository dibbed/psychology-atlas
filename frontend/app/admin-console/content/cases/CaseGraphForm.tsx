"use client";
import {useEffect, useRef, useState, type FormEvent} from "react";
import {cms, CmsError} from "@/lib/cms";

export type InspectorGraph = {
  case_id: number; revision_id: number; rubric_version: number; entry_step_id: number | null;
  scoring_dimensions: {id:number;stable_key:string;label:string;description:string;is_active:boolean}[];
  steps: {id:number;stable_key:string;node_kind:string;title:string;narrative:string;is_active:boolean}[];
  questions: {id:number;step_id:number;scoring_dimension_id:number|null;prompt:string;explanation:string;is_active:boolean}[];
  choices: {id:number;question_id:number;text:string;score_value:number;feedback:string;is_active:boolean}[];
  transitions: {id:number;source_step_id:number;choice_id:number|null;target_step_id:number|null;outcome:string;is_active:boolean}[];
};
type Step = {key:string;kind:string;title:string;narrative:string;is_active:boolean};
type Dimension = {key:string;label:string;description:string;is_active:boolean};
type Question = {key:string;step_key:string;prompt:string;explanation:string;dimension_key:string|null;is_active:boolean};
type Choice = {key:string;question_key:string;text:string;score_value:number;feedback:string;is_active:boolean};
type Transition = {source_key:string;choice_key:string|null;target_key:string|null;outcome:string;is_active:boolean};
type Draft = {
  entry_step_key:string|null;rubric_version:number;
  steps:Step[];scoring_dimensions:Dimension[];questions:Question[];
  choices:Choice[];transitions:Transition[];
};
type Group = "steps"|"scoring_dimensions"|"questions"|"choices"|"transitions";
type FieldValue = string|number|boolean|null;

function snapshot(graph:InspectorGraph):Draft{
  const steps=new Map(graph.steps.map(s=>[s.id,s.stable_key]));
  const dims=new Map(graph.scoring_dimensions.map(d=>[d.id,d.stable_key]));
  return {
    entry_step_key:graph.entry_step_id?steps.get(graph.entry_step_id)??null:null,
    rubric_version:graph.rubric_version,
    steps:graph.steps.map(s=>({key:s.stable_key,kind:s.node_kind,title:s.title,
      narrative:s.narrative,is_active:s.is_active})),
    scoring_dimensions:graph.scoring_dimensions.map(d=>({key:d.stable_key,label:d.label,
      description:d.description,is_active:d.is_active})),
    questions:graph.questions.map(q=>({key:"q"+q.id,step_key:steps.get(q.step_id)??"",
      prompt:q.prompt,explanation:q.explanation,dimension_key:q.scoring_dimension_id?
      dims.get(q.scoring_dimension_id)??null:null,is_active:q.is_active})),
    choices:graph.choices.map(c=>({key:"c"+c.id,question_key:"q"+c.question_id,
      text:c.text,score_value:c.score_value,feedback:c.feedback,is_active:c.is_active})),
    transitions:graph.transitions.map(t=>({source_key:steps.get(t.source_step_id)??"",
      choice_key:t.choice_id?"c"+t.choice_id:null,
      target_key:t.target_step_id?steps.get(t.target_step_id)??null:null,
      outcome:t.outcome,is_active:t.is_active})),
  };
}
function unusedKey(prefix:string, rows:{key:string}[]):string{
  let n=1;
  while(rows.some(r=>r.key===prefix+n))n++;
  return prefix+n;
}
export function CaseGraphForm({graph,etag,onSaved,onDirtyChange}:{
  graph:InspectorGraph;etag:string;onSaved:()=>Promise<void>;
  onDirtyChange:(dirty:boolean)=>void;
}){
  const [draft,setDraft]=useState<Draft>(()=>snapshot(graph));
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [status,setStatus]=useState("");
  const alertRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{onDirtyChange(dirty);},[dirty,onDirtyChange]);
  useEffect(()=>{
    if(!dirty)return;
    const guard=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",guard);
    return ()=>window.removeEventListener("beforeunload",guard);
  },[dirty]);
  const change=(group:Group,index:number,field:string,value:FieldValue)=>{
    setDraft(old=>({...old,[group]:old[group].map((row,i)=>i===index?{...row,[field]:value}:row)}) as Draft);
    setDirty(true);setStatus("");
  };
  const setEntry=(value:string|null)=>{setDraft(old=>({...old,entry_step_key:value}));setDirty(true);};
  const add=(group:Group)=>{
    setDraft(old=>{
      const next:Record<Group,Step|Dimension|Question|Choice|Transition>={
        steps:{key:unusedKey("step",old.steps),kind:"information",title:"",narrative:"",is_active:true},
        scoring_dimensions:{key:unusedKey("dim",old.scoring_dimensions),label:"",description:"",is_active:true},
        questions:{key:unusedKey("q",old.questions),step_key:old.steps[0]?.key??"",
          prompt:"",explanation:"",dimension_key:null,is_active:true},
        choices:{key:unusedKey("c",old.choices),question_key:old.questions[0]?.key??"",
          text:"",score_value:0,feedback:"",is_active:true},
        transitions:{source_key:old.steps[0]?.key??"",choice_key:null,target_key:null,
          outcome:"complete",is_active:true},
      };
      return {...old,[group]:[...old[group],next[group]]} as Draft;
    });
    setDirty(true);setStatus("");
  };
  const remove=(group:Group,index:number)=>{
    if(!window.confirm("این مورد و ارتباط‌های وابسته از پیش‌نویس حذف شوند؟ ذخیره فقط پس از ثبت فرم انجام می‌شود."))return;
    setDraft(old=>{
      const next:Draft={...old,[group]:old[group].filter((_,i)=>i!==index)} as Draft;
      if(group==="steps"){
        const key=old.steps[index].key;
        const qs=next.questions.filter(q=>q.step_key!==key);
        const ids=new Set(qs.map(q=>q.key));
        const cs=next.choices.filter(c=>ids.has(c.question_key));
        const choiceIds=new Set(cs.map(c=>c.key));
        next.questions=qs;next.choices=cs;
        next.transitions=next.transitions.filter(t=>t.source_key!==key &&
          t.target_key!==key && (!t.choice_key||choiceIds.has(t.choice_key)));
        if(next.entry_step_key===key)next.entry_step_key=null;
      }
      if(group==="questions"){
        const key=old.questions[index].key;
        next.choices=next.choices.filter(c=>c.question_key!==key);
        const ids=new Set(next.choices.map(c=>c.key));
        next.transitions=next.transitions.filter(t=>!t.choice_key||ids.has(t.choice_key));
      }
      if(group==="choices"){
        const key=old.choices[index].key;
        next.transitions=next.transitions.filter(t=>t.choice_key!==key);
      }
      if(group==="scoring_dimensions"){
        const key=old.scoring_dimensions[index].key;
        next.questions=next.questions.map(q=>q.dimension_key===key?{...q,dimension_key:null}:q);
      }
      return next;
    });
    setDirty(true);setStatus("");
  };
  const move=(group:Group,index:number,offset:number)=>{
    if(index+offset<0||index+offset>=draft[group].length)return;
    setDraft(old=>{
      const rows=[...old[group]];[rows[index],rows[index+offset]]=[rows[index+offset],rows[index]];
      return {...old,[group]:rows} as Draft;
    });
    setDirty(true);
  };
  const save=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(!dirty||busy)return;
    setBusy(true);setError("");setStatus("");
    try{
      const result=await cms<{valid:boolean;issues:string[]}>(
        "/cases/"+graph.case_id+"/revisions/"+graph.revision_id+"/graph/edit/",
        {method:"POST",headers:{"If-Match":etag},body:JSON.stringify(draft)});
      setStatus(result.data.valid?"گراف پیش‌نویس ذخیره شد و از نظر ساختار معتبر است.":
        "گراف پیش‌نویس ذخیره شد، اما "+result.data.issues.length+" خطای ساختاری دارد.");
      setDirty(false);
      await onSaved();
    }catch(failure){
      setError(failure instanceof CmsError?failure.message:
        "ذخیره انجام نشد. گراف سرور تغییر نکرده است؛ ورودی‌ها را بررسی کنید.");
      alertRef.current?.focus();
    }finally{setBusy(false);}
  };
  const val=(group:Group,index:number,field:string)=>(
    (draft[group][index] as unknown as Record<string,FieldValue>)[field]
  );
  const input=(group:Group,index:number,field:string,label:string,maxLength=20000)=>{
    const value=val(group,index,field);
    return <label key={field}>{label}
      {maxLength>255?<textarea rows={2} maxLength={maxLength} value={String(value??"")}
        onChange={e=>change(group,index,field,e.target.value)}/>:
        <input type="text" maxLength={maxLength} value={String(value??"")}
        onChange={e=>change(group,index,field,e.target.value)}/>}
    </label>;
  };
  const select=(group:Group,index:number,field:string,label:string,items:{value:string;label:string}[])=>(
    <label key={field}>{label}
      <select value={String(val(group,index,field)??"")}
        onChange={e=>change(group,index,field,e.target.value||null)}>
        {items.map(item=><option key={item.value} value={item.value}>{item.label}</option>)}
      </select>
    </label>);
  const toggle=(group:Group,index:number)=><label>
    <input type="checkbox" checked={Boolean(val(group,index,"is_active"))}
      onChange={e=>change(group,index,"is_active",e.target.checked)}/> فعال
  </label>;
  const controls=(group:Group,index:number)=><div className="cms-filters">
    <button type="button" className="button secondary" disabled={index===0}
      onClick={()=>move(group,index,-1)}>بالا</button>
    <button type="button" className="button secondary" disabled={index===draft[group].length-1}
      onClick={()=>move(group,index,1)}>پایین</button>
    <button type="button" className="button secondary" onClick={()=>remove(group,index)}>حذف از Draft</button>
  </div>;
  const steps=[{value:"",label:"انتخاب مرحله"},...draft.steps.map(s=>({value:s.key,label:s.title||s.key}))];
  const questions=[{value:"",label:"انتخاب پرسش"},...draft.questions.map(q=>({value:q.key,label:q.prompt.slice(0,60)||q.key}))];
  const choices=[{value:"",label:"انتقال خودکار"},...draft.choices.map(c=>({value:c.key,label:c.text.slice(0,60)||c.key}))];
  const dims=[{value:"",label:"بدون بُعد"},...draft.scoring_dimensions.map(d=>({value:d.key,label:d.label||d.key}))];
  return <section className="card stack" aria-labelledby="p12-form-title">
    <h2 id="p12-form-title">ویرایش ساختار CaseRevision (فقط Draft)</h2>
    <p className="muted">افزودن، حذف، و جابه‌جایی عناصر فقط پس از ذخیره در سرور ثبت می‌شود. شناسه‌های فنی پایدارند؛ پاسخ‌ها و تلاش‌های قبلی کپی نمی‌شوند.</p>
    <div ref={alertRef} tabIndex={-1} role={error?"alert":"status"} aria-live="polite">
      {error||status||null}
    </div>
    <form className="stack" onSubmit={save}>
      <fieldset className="stack">
        <legend>نسخه و مسیر شروع</legend>
        <label>نقطه شروع
          <select value={draft.entry_step_key??""} onChange={e=>setEntry(e.target.value||null)}>
            {steps.map(s=><option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        <label>نسخهٔ rubric
          <select value={draft.rubric_version} onChange={e=>{
            setDraft(old=>({...old,rubric_version:Number(e.target.value)}));setDirty(true);
          }}><option value={0}>Legacy (0)</option><option value={1}>Dimensions (1)</option></select>
        </label>
      </fieldset>
      <fieldset className="stack">
        <legend>مراحل ({draft.steps.length})</legend>
        {draft.steps.map((s,i)=><details key={s.key} className="card stack">
          <summary>{s.title||s.key} <small dir="ltr">{s.key}</small></summary>
          <div className="stack">
            {input("steps",i,"title","عنوان",255)}
            {input("steps",i,"narrative","روایت آموزشی")}
            {select("steps",i,"kind","نوع مرحله",[
              {value:"information",label:"اطلاعاتی"},{value:"decision",label:"تصمیم"},{value:"terminal",label:"پایان"}])}
            {toggle("steps",i)}{controls("steps",i)}
          </div>
        </details>)}
        <button type="button" className="button secondary" onClick={()=>add("steps")}>افزودن مرحله</button>
      </fieldset>
      <fieldset className="stack">
        <legend>ابعاد امتیازدهی ({draft.scoring_dimensions.length})</legend>
        {draft.scoring_dimensions.map((d,i)=><details key={d.key} className="card stack">
          <summary>{d.label||d.key} <small dir="ltr">{d.key}</small></summary>
          <div className="stack">{input("scoring_dimensions",i,"label","عنوان بُعد",160)}
            {input("scoring_dimensions",i,"description","توضیح")}
            {toggle("scoring_dimensions",i)}{controls("scoring_dimensions",i)}</div>
        </details>)}
        <button type="button" className="button secondary" onClick={()=>add("scoring_dimensions")}>افزودن بُعد</button>
      </fieldset>
      <fieldset className="stack">
        <legend>پرسش‌ها ({draft.questions.length})</legend>
        {draft.questions.map((q,i)=><details key={q.key} className="card stack">
          <summary>{q.prompt.slice(0,60)||q.key} <small dir="ltr">{q.key}</small></summary>
          <div className="stack">
            {select("questions",i,"step_key","مرحلهٔ مربوط",steps)}
            {input("questions",i,"prompt","متن سؤال")}
            {input("questions",i,"explanation","توضیح")}
            {select("questions",i,"dimension_key","بُعد امتیازدهی",dims)}
            {toggle("questions",i)}{controls("questions",i)}
          </div>
        </details>)}
        <button type="button" className="button secondary" onClick={()=>add("questions")}>افزودن سؤال</button>
      </fieldset>
      <fieldset className="stack">
        <legend>گزینه‌ها ({draft.choices.length})</legend>
        {draft.choices.map((c,i)=><details key={c.key} className="card stack">
          <summary>{c.text.slice(0,60)||c.key} <small dir="ltr">{c.key}</small></summary>
          <div className="stack">
            {select("choices",i,"question_key","پرسش مربوط",questions)}
            {input("choices",i,"text","متن گزینه")}
            {input("choices",i,"feedback","بازخورد")}
            <label>امتیاز گزینه<input type="number" step={1} min={-10000} max={10000}
              value={c.score_value} onChange={e=>change("choices",i,"score_value",Number(e.target.value))}/></label>
            {toggle("choices",i)}{controls("choices",i)}
          </div>
        </details>)}
        <button type="button" className="button secondary" onClick={()=>add("choices")}>افزودن گزینه</button>
      </fieldset>
      <fieldset className="stack">
        <legend>انتقال‌ها ({draft.transitions.length})</legend>
        {draft.transitions.map((t,i)=><details key={"transition-"+i} className="card stack">
          <summary>انتقال {i+1}: {t.source_key||"نامشخص"} → {t.outcome==="complete"?"پایان":t.target_key||"نامشخص"}</summary>
          <div className="stack">
            {select("transitions",i,"source_key","مرحله مبدأ",steps)}
            {select("transitions",i,"choice_key","گزینهٔ شرط (یا خودکار)",choices)}
            {select("transitions",i,"outcome","نتیجه",[
              {value:"continue",label:"ادامه به گام مقصد"},{value:"complete",label:"پایان"}])}
            {select("transitions",i,"target_key","مرحله مقصد (برای ادامه)",steps)}
            {toggle("transitions",i)}{controls("transitions",i)}
          </div>
        </details>)}
        <button type="button" className="button secondary" onClick={()=>add("transitions")}>افزودن انتقال</button>
      </fieldset>
      <section className="stack" aria-label="نمای ساختار زنده">
        <h3>نمای مسیرها پیش از ذخیره</h3>
        <ol>{draft.steps.map(step=><li key={step.key}>
          <strong>{step.title||step.key}</strong> ({step.kind})
          <ul>{draft.transitions.filter(t=>t.source_key===step.key).map((t,i)=><li key={i}>
            {t.choice_key??"خودکار"} → {t.outcome==="complete"?"پایان":t.target_key||"بدون مقصد"}
          </li>)}</ul>
        </li>)}</ol>
      </section>
      <button type="submit" className="button" disabled={!dirty||busy} aria-busy={busy}>
        {busy?"در حال ذخیره…":"ذخیرهٔ ساختار Draft"}
      </button>
      {dirty&&<p className="muted" role="status">تغییر ذخیره‌نشده دارید. هنگام خروج از صفحه هشدار داده می‌شود.</p>}
    </form>
  </section>;
}
