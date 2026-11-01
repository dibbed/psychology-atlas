"use client";
import {useEffect, useState, type FormEvent} from "react";
import {cms, CmsError, type CmsPage} from "@/lib/cms";
import {CmsState, useCms} from "@/components/cms/CmsShell";

type Row={quiz_id:number;slug:string;title:string;is_active:boolean;seed_managed:boolean};
type Choice={id?:number;text:string;is_correct:boolean;is_active?:boolean};
type Question={id?:number;prompt:string;explanation:string;is_active?:boolean;choices:Choice[]};
type Details={quiz_id:number;slug:string;title:string;description:string;is_active:boolean;
  seed_managed:boolean;history_protected:boolean;questions:Question[];
  valid:boolean;issues:string[];publication_available:false};
type Result={score_percent:number;preview_only:true;correct_count:number;total_questions:number;
  feedback:{question_id:number;correct:boolean;explanation:string}[]};
const newQuestion=():Question=>({prompt:"",explanation:"",choices:[
  {text:"",is_correct:true},{text:"",is_correct:false},
]});
function errorMessage(value:unknown){
  return value instanceof CmsError?value.message:"درخواست انجام نشد. دسترسی یا داده‌ها را بررسی کنید.";
}
export default function LearningQuizEditor(){
  const {can}=useCms();
  const allowed=can("cms_learning_view");
  const [list,setList]=useState<Row[]>([]);
  const [page,setPage]=useState(1);
  const [count,setCount]=useState(0);
  const [selected,setSelected]=useState<Details>();
  const [etag,setEtag]=useState<string|null>(null);
  const [draft,setDraft]=useState<Question[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [feedback,setFeedback]=useState<Result>();
  const [answers,setAnswers]=useState<Record<number,number>>({});
  const [dirty,setDirty]=useState(false);
  const [slug,setSlug]=useState("");
  const [title,setTitle]=useState("");
  const [description,setDescription]=useState("");
  useEffect(()=>{
    if(!allowed)return;
    let valid=true;
    void cms<CmsPage<Row>>("/learning/quizzes/?page="+page+"&page_size=30")
      .then(r=>{if(valid){setList(r.data.results);setCount(r.data.count);setLoading(false);}})
      .catch(e=>{if(valid){setError(errorMessage(e));setLoading(false);}});
    return ()=>{valid=false;};
  },[allowed,page]);
  useEffect(()=>{
    if(!dirty)return;
    const prevent=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";};
    window.addEventListener("beforeunload",prevent);
    return ()=>window.removeEventListener("beforeunload",prevent);
  },[dirty]);
  const load=async(id:number)=>{
    const result=await cms<Details>("/learning/quizzes/"+id+"/");
    setSelected(result.data);setEtag(result.etag);
    setDraft(result.data.questions.map(q=>({...q,
      choices:q.choices.map(c=>({...c}))})));
    setFeedback(undefined);setAnswers({});setDirty(false);
  };
  const open=async(id:number)=>{
    if(dirty&&!window.confirm("تغییرات ذخیره‌نشده کنار گذاشته شوند؟"))return;
    setBusy(true);setError("");
    try{await load(id);}catch(e){setError(errorMessage(e));}
    finally{setBusy(false);}
  };
  const refresh=async()=>{const r=await cms<CmsPage<Row>>("/learning/quizzes/?page="+page+"&page_size=30");setList(r.data.results);setCount(r.data.count);};
  const create=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();if(busy||!can("cms_learning_create"))return;
    setBusy(true);setError("");
    try{
      const r=await cms<{quiz_id:number}>("/learning/quizzes/",{method:"POST",
        body:JSON.stringify({slug,title,description,disorder_id:null})});
      setSlug("");setTitle("");setDescription("");
      await refresh();await load(r.data.quiz_id);
    }catch(e){setError(errorMessage(e));}
    finally{setBusy(false);}
  };
  const update=(index:number,field:"prompt"|"explanation",value:string)=>{
    setDraft(old=>old.map((q,i)=>i===index?{...q,[field]:value}:q));setDirty(true);setFeedback(undefined);
  };
  const changeChoice=(qi:number,ci:number,field:"text"|"is_correct",value:string|boolean)=>{
    setDraft(old=>old.map((q,i)=>i!==qi?q:{...q,choices:q.choices.map((c,j)=>{
      if(field==="is_correct")return {...c,is_correct:j===ci};
      return j===ci?{...c,text:String(value)}:c;
    })}));setDirty(true);setFeedback(undefined);
  };
  const move=(index:number,offset:number)=>{
    if(index+offset<0||index+offset>=draft.length)return;
    setDraft(old=>{const rows=[...old];[rows[index],rows[index+offset]]=[rows[index+offset],rows[index]];return rows;});
    setDirty(true);
  };
  const save=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();
    if(!selected||!etag||!can("cms_learning_edit")||busy)return;
    setBusy(true);setError("");
    try{
      const response=await cms("/learning/quizzes/"+selected.quiz_id+"/questions/replace/",{
        method:"POST",headers:{"If-Match":etag},
        body:JSON.stringify({questions:draft.map(q=>({
          prompt:q.prompt,explanation:q.explanation,
          choices:q.choices.map(c=>({text:c.text,is_correct:c.is_correct})),
        }))}),
      });
      await load(selected.quiz_id);
      if(response.data)setError("");
    }catch(e){setError(errorMessage(e));}
    finally{setBusy(false);}
  };
  const simulate=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();
    if(!selected||busy)return;
    setBusy(true);setError("");setFeedback(undefined);
    try{
      const r=await cms<Result>("/learning/quizzes/"+selected.quiz_id+"/simulate/",{
        method:"POST",body:JSON.stringify({answers:selected.questions.filter(q=>q.is_active!==false).map(
          q=>({question_id:q.id,choice_id:answers[q.id??-1]}))}),
      });
      setFeedback(r.data);
    }catch(e){setError(errorMessage(e));}
    finally{setBusy(false);}
  };
  if(!allowed)return <CmsState empty="برای مدیریت سؤال‌های آموزشی، مجوز مدیریت محتوای یادگیری لازم است."/>;
  const editable=selected&&!selected.is_active&&!selected.seed_managed&&!selected.history_protected&&can("cms_learning_edit");
  return <div className="stack" dir="rtl">
    <a href="/admin-console/content" className="cms-link">بازگشت به محتوا</a>
    <div className="cms-title"><p className="eyebrow">P13 | Learning editor</p>
      <h1>مدیریت آزمون‌های آموزشی</h1>
      <p className="muted">ویرایش سؤال‌ها فقط روی Quiz غیرفعال، بدون سابقهٔ پاسخ و غیر Seed مجاز است. انتشار نیازمند تأیید منابع، علم و حقوق استفاده در P16 است.</p>
    </div>
    {error&&<p role="alert">{error}</p>}
    <section className="card stack">
      <h2>فهرست آزمون‌ها</h2>
      {loading?<CmsState loading/>:<ul>{list.map(item=><li key={item.quiz_id}>
        <strong>{item.title}</strong> <small dir="ltr">{item.slug}</small>
        <span> | {item.is_active?"فعال":"غیرفعال"} </span>
        <button type="button" className="button secondary" disabled={busy}
          onClick={()=>void open(item.quiz_id)}>باز کردن</button>
      </li>)}</ul>}
      {count>30&&<div className="cms-filters">
        <button className="button secondary" type="button" disabled={page<=1}
          onClick={()=>{setPage(page-1);setLoading(true);}}>قبل</button>
        <span>صفحهٔ {page} از {Math.ceil(count/30)}</span>
        <button className="button secondary" type="button" disabled={page*30>=count}
          onClick={()=>{setPage(page+1);setLoading(true);}}>بعد</button>
      </div>}
    </section>
    {can("cms_learning_create")&&<section className="card stack">
      <h2>ساخت آزمون غیرفعال و منتشرنشده</h2>
      <form className="stack" onSubmit={create}>
        <label>شناسهٔ لاتین<input required dir="ltr" pattern="[a-z0-9]+(-[a-z0-9]+)*"
          maxLength={160} value={slug} onChange={e=>setSlug(e.target.value)}/></label>
        <label>عنوان<input required maxLength={255} value={title} onChange={e=>setTitle(e.target.value)}/></label>
        <label>شرح<textarea rows={2} maxLength={20000}
          value={description} onChange={e=>setDescription(e.target.value)}/></label>
        <button className="button secondary" type="submit" disabled={busy}>ساخت Draft غیرفعال</button>
      </form>
    </section>}
    {selected&&<section className="card stack">
      <h2>{selected.title}</h2>
      <p className="muted">نسخهٔ داخلی #{selected.quiz_id} | {selected.is_active?"فعال":"غیرفعال"} | اعتبار ساختاری: {selected.valid?"معتبر":"نیازمند اصلاح"}</p>
      {!editable&&<p>سؤال‌های این آزمون به علت فعال بودن، مدیریت Seed یا وجود تلاش‌های قدیمی قفل هستند. کلید پاسخ و تاریخچه از این ویرایشگر تغییر نمی‌کنند.</p>}
      {selected.issues.length>0&&<ul>{selected.issues.map((issue,i)=><li key={i}><code dir="ltr">{issue}</code></li>)}</ul>}
      {editable&&<form className="stack" onSubmit={save}>
        <h3>سؤال‌ها ({draft.length})</h3>
        {draft.map((q,i)=><details className="card stack" key={i}>
          <summary>سؤال {i+1}: {q.prompt.slice(0,60)||"بدون متن"}</summary>
          <div className="stack">
            <label>متن سؤال<textarea required rows={2} maxLength={20000}
              value={q.prompt} onChange={e=>update(i,"prompt",e.target.value)}/></label>
            <label>توضیح علمی و آموزشی<textarea rows={2} maxLength={20000}
              value={q.explanation} onChange={e=>update(i,"explanation",e.target.value)}/></label>
            <fieldset className="stack"><legend>گزینه‌ها و یک پاسخ صحیح</legend>
              {q.choices.map((c,j)=><div className="cms-filters" key={j}>
                <label>گزینه {j+1}<input required maxLength={20000} value={c.text}
                  onChange={e=>changeChoice(i,j,"text",e.target.value)}/></label>
                <label><input type="radio" name={"correct-"+i} checked={c.is_correct}
                  onChange={()=>changeChoice(i,j,"is_correct",true)}/> پاسخ درست</label>
                <button type="button" className="button secondary" disabled={q.choices.length<=2}
                  onClick={()=>{setDraft(old=>old.map((v,k)=>{
                    if(k!==i)return v;
                    const remaining=v.choices.filter((_,idx)=>idx!==j);
                    if(!remaining.some(c=>c.is_correct))remaining[0]={...remaining[0],is_correct:true};
                    return {...v,choices:remaining};
                  }));setDirty(true);}}>حذف گزینه</button>
              </div>)}
              <button type="button" className="button secondary" disabled={q.choices.length>=10}
                onClick={()=>{setDraft(old=>old.map((v,k)=>k===i?
                  {...v,choices:[...v.choices,{text:"",is_correct:false}]}:v));setDirty(true);}}>افزودن گزینه</button>
            </fieldset>
            <div className="cms-filters">
              <button type="button" className="button secondary" disabled={i===0}
                onClick={()=>move(i,-1)}>بالا</button>
              <button type="button" className="button secondary" disabled={i===draft.length-1}
                onClick={()=>move(i,1)}>پایین</button>
              <button type="button" className="button secondary" onClick={()=>{
                if(window.confirm("این سؤال از Draft حذف شود؟")){setDraft(old=>old.filter((_,k)=>k!==i));setDirty(true);}
              }}>حذف سؤال</button>
            </div>
          </div>
        </details>)}
        <button type="button" className="button secondary" disabled={draft.length>=100}
          onClick={()=>{setDraft(old=>[...old,newQuestion()]);setDirty(true);}}>افزودن سؤال</button>
        <button type="submit" className="button" disabled={busy||!dirty||!etag}>
          {busy?"در حال ذخیره…":"ذخیرهٔ سؤال‌ها در Draft"}
        </button>
        {dirty&&<p className="muted" role="status">تغییر ذخیره‌نشده دارید. در صورت خروج هشدار نمایش داده می‌شود.</p>}
      </form>}
      {!dirty&&selected.valid&&can("cms_learning_preview")&&
        <form className="stack" onSubmit={simulate}>
          <h3>آزمون فرضی، بدون ذخیرهٔ پاسخ یا امتیاز دانشجو</h3>
          {selected.questions.filter(q=>q.is_active!==false).map(q=><fieldset className="stack" key={q.id}>
            <legend>{q.prompt}</legend>
            {q.choices.filter(c=>c.is_active!==false).map(choice=><label key={choice.id}>
              <input type="radio" name={"answer-"+q.id} required
                checked={answers[q.id??-1]===choice.id}
                onChange={()=>setAnswers(old=>({...old,[q.id??-1]:choice.id!}))}/>
              {choice.text}
            </label>)}
          </fieldset>)}
          <button type="submit" className="button secondary" disabled={busy}>اجرای پیش‌نمایش بی‌اثر</button>
        </form>}
      {feedback&&<div className="stack" aria-live="polite" role="status">
        <p><strong>امتیاز فرضی: {feedback.score_percent}٪</strong>، {feedback.correct_count} پاسخ درست از {feedback.total_questions}</p>
        <p className="muted">نتیجه فقط پیش‌نمایش است و هیچ سابقهٔ یادگیری ایجاد نشده.</p>
        <ul>{feedback.feedback.map(item=><li key={item.question_id}>
          سؤال #{item.question_id}: {item.correct?"درست":"نادرست"} | {item.explanation}
        </li>)}</ul>
      </div>}
    </section>}
  </div>;
}
