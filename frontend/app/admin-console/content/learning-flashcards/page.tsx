"use client";
import {useEffect, useState, type FormEvent} from "react";
import {cms, type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";
import {LearningArchiveAction} from "@/components/cms/LearningArchiveAction";

type Item={flashcard_id:number;slug:string;is_active:boolean;seed_managed:boolean;archived_at:string|null};
type Detail=Item&{front:string;back:string;hint:string;difficulty:string;
  concept_id:number|null;disorder_id:number|null;history_protected:boolean;
  publication_available:false};
type FormData={front:string;back:string;hint:string;difficulty:string;concept_id:string;disorder_id:string};
const empty:FormData={front:"",back:"",hint:"",difficulty:"basic",concept_id:"",disorder_id:""};
const message=(x:unknown)=>x instanceof Error?x.message:"درخواست انجام نشد.";
function cardPayload(value:FormData){
  const data={...value,concept_id:value.concept_id===""?null:Number(value.concept_id),
    disorder_id:value.disorder_id===""?null:Number(value.disorder_id)};
  if([data.concept_id,data.disorder_id].some(id=>id!==null&&(!Number.isSafeInteger(id)||id<1)))
    throw new Error("شناسهٔ مفهوم و اختلال باید عدد صحیح مثبت باشند.");
  return data;
}
export default function FlashcardCMS(){
  const {can}=useCms();
  const allowed=can("cms_learning_view");
  const [items,setItems]=useState<Item[]>([]);
  const [page,setPage]=useState(1);
  const [count,setCount]=useState(0);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [slug,setSlug]=useState("");
  const [form,setForm]=useState<FormData>(empty);
  const [selected,setSelected]=useState<Detail>();
  const [etag,setEtag]=useState<string|null>(null);
  const [draft,setDraft]=useState<FormData>(empty);
  const [dirty,setDirty]=useState(false);
  useEffect(()=>{
    if(!allowed)return;
    let mounted=true;
    void cms<CmsPage<Item>>("/learning/flashcards/?page="+page+"&page_size=30")
      .then(result=>{if(mounted){setItems(result.data.results);setCount(result.data.count);setLoading(false);}})
      .catch(reason=>{if(mounted){setError(message(reason));setLoading(false);}});
    return ()=>{mounted=false;};
  },[allowed,page]);
  useEffect(()=>{
    if(!dirty)return;
    const guard=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};
    window.addEventListener("beforeunload",guard);
    return ()=>window.removeEventListener("beforeunload",guard);
  },[dirty]);
  const reload=async(id:number)=>{
    const res=await cms<Detail>("/learning/flashcards/"+id+"/");
    setSelected(res.data);setEtag(res.etag);
    setDraft({front:res.data.front,back:res.data.back,hint:res.data.hint,
      difficulty:res.data.difficulty,concept_id:String(res.data.concept_id??""),disorder_id:String(res.data.disorder_id??"")});
    setDirty(false);
  };
  const refresh=async()=>{
    const res=await cms<CmsPage<Item>>("/learning/flashcards/?page="+page+"&page_size=30");
    setItems(res.data.results);setCount(res.data.count);
  };
  const pick=async(id:number)=>{
    if(dirty&&!window.confirm("تغییر ذخیره‌نشده کنار گذاشته شود؟"))return;
    setBusy(true);setError("");
    try{await reload(id);}catch(e){setError(message(e));}finally{setBusy(false);}
  };
  const create=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();if(busy)return;
    if(dirty&&!window.confirm("تغییر ذخیره‌نشده کنار گذاشته شود؟"))return;
    setBusy(true);setError("");
    try{
      const res=await cms<{flashcard_id:number}>("/learning/flashcards/",{
        method:"POST",body:JSON.stringify({...cardPayload(form),slug}),
      });
      setSlug("");setForm(empty);await refresh();await reload(res.data.flashcard_id);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const save=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(!selected||!etag||!dirty||busy)return;
    setBusy(true);setError("");
    try{
      await cms("/learning/flashcards/"+selected.flashcard_id+"/metadata/",{
        method:"POST",headers:{"If-Match":etag},body:JSON.stringify(cardPayload(draft)),
      });
      await reload(selected.flashcard_id);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  if(!allowed)return <CmsState empty="دسترسی اختصاصی مدیریت محتوای یادگیری لازم است."/>;
  const edit=Boolean(selected&&!selected.archived_at&&!selected.is_active&&!selected.seed_managed&&!selected.history_protected&&can("cms_learning_edit"));
  const fields=(value:FormData,change:(field:keyof FormData,val:string)=>void)=>(
    <>
      <label>روی کارت<textarea required rows={3} maxLength={20000}
        value={value.front} onChange={e=>change("front",e.target.value)}/></label>
      <label>پشت کارت<textarea required rows={3} maxLength={20000}
        value={value.back} onChange={e=>change("back",e.target.value)}/></label>
      <label>راهنما<textarea rows={2} maxLength={20000}
        value={value.hint} onChange={e=>change("hint",e.target.value)}/></label>
      <label>سطح
        <select value={value.difficulty} onChange={e=>change("difficulty",e.target.value)}>
          <option value="basic">مقدماتی</option>
          <option value="intermediate">متوسط</option>
          <option value="advanced">پیشرفته</option>
        </select>
      </label>
      <label>شناسهٔ مفهوم مرتبط (اختیاری)<input type="number" min="1" step="1" dir="ltr"
        value={value.concept_id} onChange={e=>change("concept_id",e.target.value)}/></label>
      <label>شناسهٔ اختلال مرتبط (اختیاری)<input type="number" min="1" step="1" dir="ltr"
        value={value.disorder_id} onChange={e=>change("disorder_id",e.target.value)}/></label>
    </>);
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console/content">بازگشت به مدیریت محتوا</a>
    <div className="cms-title"><p className="eyebrow">P13 | Flashcards</p>
      <h1>کارت‌های آموزشی و حفاظت SRS</h1>
      <p className="muted">هویت و زمان‌بندی مرورهای دانشجو مستقل از ویرایشگرند. فقط کارت غیرفعال بدون سابقهٔ یادگیری و غیر Seed ویرایش می‌شود.</p>
    </div>
    {error&&<p role="alert">{error}</p>}
    <section className="card stack">
      <h2>کارت‌های ثبت‌شده</h2>
      {loading?<CmsState loading/>:<ul>{items.map(item=><li key={item.flashcard_id}>
        <strong>{item.slug}</strong> | {item.archived_at?"بایگانی‌شده":item.is_active?"فعال":"غیرفعال"}
        <button type="button" className="button secondary" disabled={busy}
          onClick={()=>void pick(item.flashcard_id)}>باز کردن</button>
      </li>)}</ul>}
      {count>30&&<div className="cms-filters">
        <button type="button" className="button secondary" disabled={page<=1}
          onClick={()=>{setPage(page-1);setLoading(true);}}>قبل</button>
        <span>صفحهٔ {page} از {Math.ceil(count/30)}</span>
        <button type="button" className="button secondary" disabled={page*30>=count}
          onClick={()=>{setPage(page+1);setLoading(true);}}>بعد</button>
      </div>}
    </section>
    {can("cms_learning_create")&&<section className="card stack">
      <h2>ساخت Flashcard غیرفعال</h2>
      <form className="stack" onSubmit={create}>
        <fieldset className="stack" disabled={busy}><legend>محتوای کارت</legend>
        <label>شناسهٔ لاتین<input dir="ltr" required pattern="[a-z0-9]+(-[a-z0-9]+)*"
          maxLength={180} value={slug} onChange={e=>setSlug(e.target.value)}/></label>
        {fields(form,(key,val)=>setForm(o=>({...o,[key]:val})))}
        <button className="button secondary" type="submit" disabled={busy}>ساخت کارت خصوصی</button>
        </fieldset>
      </form>
    </section>}
    {selected&&<section className="card stack">
      <h2>کارت: {selected.slug}</h2>
      <p>{selected.front}</p><details><summary>نمای خصوصی پشت کارت</summary><p>{selected.back}</p></details>
      {!edit&&<p>ویرایش قفل است: کارت بایگانی یا فعال است، از Seed آمده یا پیشرفت یادگیرنده دارد. دادهٔ SRS دست‌نخورده می‌ماند.</p>}
      <LearningArchiveAction key={"archive-card-"+selected.flashcard_id} kind="flashcard" itemId={selected.flashcard_id}
        etag={etag} archivedAt={selected.archived_at} blocked={busy||dirty} onBusyChange={setBusy}
        onArchived={async at=>{
          const id=selected.flashcard_id;setSelected(old=>old?.flashcard_id===id?{...old,is_active:false,archived_at:at}:old);
          await Promise.all([reload(id),refresh()]);
        }}/>
      {edit&&<form className="stack" onSubmit={save}>
        <fieldset className="stack" disabled={busy}><legend>ویرایش کارت خصوصی</legend>
        {fields(draft,(key,val)=>{setDraft(o=>({...o,[key]:val}));setDirty(true);})}
        <button className="button" type="submit" disabled={busy||!dirty||!etag}>
          {busy?"در حال ذخیره…":"ذخیرهٔ Draft کارت"}
        </button>
        {dirty&&<p className="muted" role="status">ویرایش ذخیره‌نشده دارید.</p>}
        </fieldset>
      </form>}
      <p className="muted">انتشار عمومی فقط پس از گیت علمی/حقوقی P16 ممکن می‌شود.</p>
    </section>}
  </div>;
}
