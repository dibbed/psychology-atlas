"use client";
import {useEffect,useState,type FormEvent} from "react";
import {cms,CmsError,type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";
import {LearningArchiveAction} from "@/components/cms/LearningArchiveAction";

type Kind="daily"|"distortions";
type Item={item_id:number;prompt:string;is_active:boolean;seed_managed:boolean;archived_at:string|null};
type Choice={id?:number;text:string;is_correct:boolean;is_active?:boolean;concept_id?:number};
type Detail=Item&{kind:Kind;explanation:string;choices:Choice[];valid:boolean;issues:string[];
  history_protected:boolean;publication_available:false;target_concept_id?:number;
  concept_id?:number|null;disorder_id?:number|null;slug?:string;difficulty?:string};
type Draft={prompt:string;explanation:string;choices:Choice[]};
type Result={correct:boolean;explanation:string;preview_only:true};
const empty=():Draft=>({prompt:"",explanation:"",choices:[]});
const message=(e:unknown)=>e instanceof CmsError?e.message:"عملیات در سرور موفق نبود.";
export default function PracticeCMS(){
  const {can}=useCms();const allowed=can("cms_learning_view");
  const [kind,setKind]=useState<Kind>("daily");
  const [items,setItems]=useState<Item[]>([]);
  const [page,setPage]=useState(1);const [total,setTotal]=useState(0);
  const [selected,setSelected]=useState<Detail>();const [etag,setEtag]=useState<string|null>(null);
  const [draft,setDraft]=useState<Draft>(empty);
  const [dirty,setDirty]=useState(false);const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);const [error,setError]=useState("");
  const [creation,setCreation]=useState({slug:"",prompt:"",explanation:"",
    target_concept_id:"",difficulty:"basic"});
  const [preview,setPreview]=useState<Result>();const [previewChoice,setPreviewChoice]=useState("");
  const endpoint="/learning/practice/"+kind+"/";
  useEffect(()=>{
    if(!allowed)return;
    let active=true;
    void cms<CmsPage<Item>>(endpoint+"?page="+page+"&page_size=30")
      .then(r=>{if(active){setItems(r.data.results);setTotal(r.data.count);setLoading(false);}})
      .catch(e=>{if(active){setError(message(e));setLoading(false);}});
    return ()=>{active=false;};
  },[allowed,endpoint,page]);
  useEffect(()=>{
    if(!dirty)return;
    const guard=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",guard);
    return ()=>window.removeEventListener("beforeunload",guard);
  },[dirty]);
  const reload=async(id:number)=>{
    const result=await cms<Detail>(endpoint+id+"/");
    setSelected(result.data);setEtag(result.etag);
    setDraft({prompt:result.data.prompt,explanation:result.data.explanation,
      choices:result.data.choices.map(c=>({...c}))});
    setPreview(undefined);setPreviewChoice("");setDirty(false);
  };
  const refresh=async()=>{
    const r=await cms<CmsPage<Item>>(endpoint+"?page="+page+"&page_size=30");
    setItems(r.data.results);setTotal(r.data.count);
  };
  const open=async(id:number)=>{
    if(dirty&&!window.confirm("ویرایش ذخیره‌نشده کنار گذاشته شود؟"))return;
    setBusy(true);setError("");
    try{await reload(id);}catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const switchKind=(value:Kind)=>{
    if(busy)return;
    if(dirty&&!window.confirm("ویرایش‌های ثبت‌نشده کنار گذاشته شوند؟"))return;
    setKind(value);setPage(1);setSelected(undefined);setError("");setLoading(true);setDirty(false);
  };
  const create=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();setBusy(true);setError("");
    try{
      const payload=kind==="daily"?{
        prompt:creation.prompt,explanation:creation.explanation,concept_id:null,disorder_id:null,
      }:{
        slug:creation.slug,prompt:creation.prompt,explanation:creation.explanation,
        difficulty:creation.difficulty,target_concept_id:Number(creation.target_concept_id),
      };
      const result=await cms<{item_id:number}>(endpoint,{method:"POST",body:JSON.stringify(payload)});
      setCreation({slug:"",prompt:"",explanation:"",difficulty:"basic",target_concept_id:""});
      await refresh();await reload(result.data.item_id);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const change=(field:"prompt"|"explanation",value:string)=>{
    setDraft(o=>({...o,[field]:value}));setDirty(true);setPreview(undefined);
  };
  const changeChoice=(index:number,field:"text"|"concept_id"|"is_correct",value:string|boolean)=>{
    setDraft(o=>({...o,choices:o.choices.map((c,i)=>{
      if(field==="is_correct")return {...c,is_correct:i===index};
      if(i!==index)return c;
      return {...c,[field]:field==="concept_id"?Number(value):value};
    })}));setDirty(true);setPreview(undefined);
  };
  const add=()=>{
    setDraft(o=>({...o,choices:[...o.choices,{text:"",is_correct:o.choices.length===0,
      ...(kind==="distortions"?{concept_id:selected?.target_concept_id??0}:{})}]}));setDirty(true);
  };
  const remove=(index:number)=>{
    if(draft.choices.length<=2)return;
    setDraft(o=>{
      const rows=o.choices.filter((_,i)=>i!==index);
      if(!rows.some(c=>c.is_correct))rows[0]={...rows[0],is_correct:true};
      return {...o,choices:rows};
    });setDirty(true);
  };
  const save=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();if(!selected||!etag||!dirty)return;
    setBusy(true);setError("");
    try{
      const result=await cms<Detail>(endpoint+selected.item_id+"/edit/",{
        method:"POST",headers:{"If-Match":etag},
        body:JSON.stringify({prompt:draft.prompt,explanation:draft.explanation,
          choices:draft.choices.map(c=>({
            text:c.text,is_correct:c.is_correct,
            ...(kind==="distortions"?{concept_id:c.concept_id}:{}),
          }))}),
      });
      await reload(result.data.item_id);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const simulate=async(e:FormEvent<HTMLFormElement>)=>{
    e.preventDefault();if(!selected||!previewChoice)return;
    setBusy(true);setError("");setPreview(undefined);
    try{
      const res=await cms<Result>(endpoint+selected.item_id+"/simulate/",{
        method:"POST",body:JSON.stringify({choice_id:Number(previewChoice)}),
      });
      setPreview(res.data);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  if(!allowed)return <CmsState empty="برای ویرایش تمرین‌های آموزشی به مجوز اختصاصی نیاز است."/>;
  const editable=Boolean(selected&&!selected.archived_at&&!selected.is_active&&!selected.seed_managed&&!selected.history_protected&&can("cms_learning_edit"));
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console/content">بازگشت به محتوای مرجع</a>
    <div className="cms-title"><p className="eyebrow">P13 | Practice</p>
      <h1>تمرین‌های آموزشی و چالش روزانه</h1>
      <p className="muted">متن و کلید پاسخ فقط برای آیتم غیرفعال و بدون سابقه قابل‌ویرایش است. پیش‌نمایش هیچ رکورد یادگیری نمی‌سازد.</p>
    </div>
    <label>نوع تمرین
      <select disabled={busy} value={kind} onChange={e=>switchKind(e.target.value as Kind)}>
        <option value="daily">چالش روزانه</option>
        <option value="distortions">تمرین خطاهای شناختی</option>
      </select>
    </label>
    {error&&<p role="alert">{error}</p>}
    <section className="card stack">
      <h2>فهرست {kind==="daily"?"چالش‌ها":"تمرین خطاهای شناختی"}</h2>
      {loading?<CmsState loading/>:<ul>{items.map(item=><li key={item.item_id}>
        <strong>{item.prompt.slice(0,90)}</strong> | {item.archived_at?"بایگانی‌شده":item.is_active?"فعال":"غیرفعال"}
        <button className="button secondary" type="button" disabled={busy}
          onClick={()=>void open(item.item_id)}>باز کردن</button>
      </li>)}</ul>}
      {total>30&&<div className="cms-filters">
        <button type="button" className="button secondary" disabled={page<=1}
          onClick={()=>{setPage(p=>p-1);setLoading(true);}}>قبل</button>
        <span>صفحهٔ {page} از {Math.ceil(total/30)}</span>
        <button type="button" className="button secondary" disabled={page*30>=total}
          onClick={()=>{setPage(p=>p+1);setLoading(true);}}>بعد</button>
      </div>}
    </section>
    {can("cms_learning_create")&&<section className="card stack">
      <h2>ساخت آیتم خصوصی و غیرفعال</h2>
      <form className="stack" onSubmit={create}>
        {kind==="distortions"&&<>
          <label>شناسهٔ لاتین<input required dir="ltr" pattern="[a-z0-9]+(-[a-z0-9]+)*"
            value={creation.slug} onChange={e=>setCreation(o=>({...o,slug:e.target.value}))}/></label>
          <label>شناسهٔ مفهوم درست (از بخش Concepts)
            <input required type="number" min={1} value={creation.target_concept_id}
              onChange={e=>setCreation(o=>({...o,target_concept_id:e.target.value}))}/>
          </label>
          <label>سطح<select value={creation.difficulty}
            onChange={e=>setCreation(o=>({...o,difficulty:e.target.value}))}>
            <option value="basic">مقدماتی</option>
            <option value="intermediate">متوسط</option>
            <option value="advanced">پیشرفته</option>
          </select></label>
        </>}
        <label>صورت مسئله<textarea required maxLength={20000} rows={3} value={creation.prompt}
          onChange={e=>setCreation(o=>({...o,prompt:e.target.value}))}/></label>
        <label>توضیح آموزشی<textarea maxLength={20000} rows={2} value={creation.explanation}
          onChange={e=>setCreation(o=>({...o,explanation:e.target.value}))}/></label>
        <button type="submit" className="button secondary" disabled={busy}>ثبت آیتم غیرفعال</button>
      </form>
    </section>}
    {selected&&<section className="card stack">
      <h2>ویرایش آیتم #{selected.item_id}</h2>
      <p>وضعیت اعتبار: {selected.valid?"معتبر":"نیازمند اصلاح"} |
        {selected.history_protected?" حفاظت‌شده به‌علت سابقهٔ پاسخ":""}</p>
      {!editable&&<p className="muted">ویرایش آیتم بایگانی، فعال، Seed یا دارای attempt مسدود است؛ تاریخچهٔ دانشجو حفظ می‌شود.</p>}
      <LearningArchiveAction key={"archive-"+kind+"-"+selected.item_id} kind={kind} itemId={selected.item_id}
        etag={etag} archivedAt={selected.archived_at} blocked={busy||dirty} onBusyChange={setBusy}
        onArchived={async at=>{
          const id=selected.item_id;setSelected(old=>old?.item_id===id?{...old,is_active:false,archived_at:at}:old);
          await Promise.all([reload(id),refresh()]);
        }}/>
      {editable&&<form className="stack" onSubmit={save}>
        <fieldset className="stack" disabled={busy}><legend>ویرایش محتوای تمرین</legend>
        <label>سؤال<textarea required rows={3} maxLength={20000} value={draft.prompt}
          onChange={e=>change("prompt",e.target.value)}/></label>
        <label>توضیح<textarea rows={2} maxLength={20000} value={draft.explanation}
          onChange={e=>change("explanation",e.target.value)}/></label>
        <fieldset className="stack"><legend>گزینه‌های پاسخ ({draft.choices.length})</legend>
          {draft.choices.map((choice,i)=><div key={i} className="card stack">
            <label>گزینه {i+1}<input required maxLength={kind==="daily"?20000:300}
              value={choice.text} onChange={e=>changeChoice(i,"text",e.target.value)}/></label>
            {kind==="distortions"&&<label>شناسهٔ Concept این گزینه
              <input required type="number" min={1} value={choice.concept_id??""}
                onChange={e=>changeChoice(i,"concept_id",e.target.value)}/>
            </label>}
            <label><input type="radio" name="correct-answer" checked={choice.is_correct}
              onChange={()=>changeChoice(i,"is_correct",true)}/> پاسخ صحیح</label>
            <button type="button" className="button secondary" disabled={draft.choices.length<=2}
              onClick={()=>remove(i)}>حذف گزینه</button>
          </div>)}
          <button type="button" className="button secondary" onClick={add} disabled={draft.choices.length>=10}>
            افزودن گزینه</button>
        </fieldset>
        <button className="button" type="submit" disabled={busy||!dirty||!etag}>ذخیرهٔ پیش‌نویس</button>
        {dirty&&<p role="status">ویرایش ذخیره‌نشده دارید.</p>}
        </fieldset>
      </form>}
      {selected.valid&&!dirty&&can("cms_learning_preview")&&
        <form className="stack" onSubmit={simulate}>
          <h3>پیش‌نمایش بی‌اثر</h3>
          <label>گزینهٔ فرضی
            <select required value={previewChoice} onChange={e=>setPreviewChoice(e.target.value)}>
              <option value="">انتخاب کنید</option>
              {selected.choices.filter(c=>c.is_active!==false).map(c=>
                <option key={c.id} value={c.id}>{c.text}</option>)}
            </select>
          </label>
          <button type="submit" className="button secondary" disabled={busy||!previewChoice}>
            مشاهدهٔ بازخورد آموزشی</button>
        </form>}
      {preview&&<div role="status" aria-live="polite">
        {preview.correct?"گزینه صحیح است.":"گزینه نادرست است."} {preview.explanation}
        <p className="muted">نتیجهٔ این پیش‌نمایش در پروفایل دانشجو ثبت نمی‌شود.</p>
      </div>}
      <p className="muted">انتشار و فعال‌سازی تا پایان P16 غیرفعال است.</p>
    </section>}
  </div>;
}
