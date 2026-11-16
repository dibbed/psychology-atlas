"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {CmsError,type CmsPage} from "@/lib/cms";
import {type AdminArtifact,type AdminJob,type LearningKind,learningKindLabels,mutationBlocked} from "@/lib/cmsJobs";
import {faNumber} from "@/lib/fa";
import ArtifactCard from "@/components/cms/ArtifactCard";
import {CmsState} from "@/components/cms/CmsShell";
import {PrivateMutationError,usePrivateCms} from "@/components/cms/CmsJobsShared";

type Entry={kind:LearningKind;resource_id:number;etag:string;label:string};
type Selection=Pick<Entry,"kind"|"resource_id"|"etag">;
const example=JSON.stringify({schema_version:"psychology-atlas-learning-authoring-v1",items:[
  {kind:"quiz",key:"quiz-example",fields:{slug:"transfer-example-quiz",title:"نمونهٔ آزمون خصوصی",description:"",
    disorder_slug:null,questions:[{prompt:"صورت مسئلهٔ نمونه",explanation:"توضیح نمونه",choices:[
      {text:"گزینهٔ درست نمونه",is_correct:true},{text:"گزینهٔ دیگر",is_correct:false}]}]}},
  {kind:"flashcard",key:"card-example",fields:{slug:"transfer-example-card",front:"نمونهٔ روی کارت",
    back:"نمونهٔ پشت کارت",hint:"",difficulty:"basic",concept_slug:null,disorder_slug:null}},
  {kind:"daily",key:"daily-example",fields:{prompt:"نمونهٔ چالش روزانه",explanation:"توضیح نمونه",concept_slug:null,
    disorder_slug:null,choices:[{text:"گزینهٔ درست نمونه",is_correct:true},{text:"گزینهٔ دیگر",is_correct:false}]}},
  {kind:"distortions",key:"practice-example",fields:{slug:"transfer-example-practice",prompt:"صورت مسئلهٔ نمونه",
    explanation:"توضیح نمونه",difficulty:"basic",target_concept_slug:"replace-with-active-distortion-slug",choices:[
      {concept_slug:"replace-with-active-distortion-slug",text:"گزینهٔ هدف",is_correct:true},
      {concept_slug:"replace-with-another-active-distortion-slug",text:"گزینهٔ دیگر",is_correct:false}]}},
]},null,2);

export default function LearningTransfer(){
  const {can,request,current,setDirty}=usePrivateCms();
  const canImport=can("cms_learning_view")&&can("cms_learning_create")&&can("cms_learning_edit")&&can("cms_artifact_upload");
  const canExport=can("cms_learning_view")&&can("cms_learning_export");
  const [kind,setKind]=useState<LearningKind>("quiz"),[page,setPage]=useState(1),[reload,setReload]=useState(0);
  const [data,setData]=useState<CmsPage<Entry>>(),[readError,setReadError]=useState<unknown>();
  const [selected,setSelected]=useState<Entry[]>([]),[file,setFile]=useState<File>();
  const [artifactId,setArtifactId]=useState<string>(),[jobId,setJobId]=useState<string>();
  const [writeError,setWriteError]=useState<unknown>(),[busy,setBusy]=useState(false),[cardBusy,setCardBusy]=useState(false);
  const input=useRef<HTMLInputElement>(null),lock=useRef(false);
  const pending=useRef<{key:string;items:Selection[]}|null>(null);
  const blocked=mutationBlocked(writeError);
  const uncertain=writeError instanceof CmsError&&writeError.code==="UNKNOWN_OUTCOME"&&!!pending.current;
  useEffect(()=>{setDirty(busy||cardBusy||!!file||selected.length>0);return()=>setDirty(false);},[busy,cardBusy,file,selected.length,setDirty]);
  useEffect(()=>{
    if(!canExport)return;
    let active=true;const abort=new AbortController();setData(undefined);setReadError(undefined);
    void request<CmsPage<Entry>>(`/learning/transfer/selection/?kind=${kind}&page=${page}&page_size=20`,{signal:abort.signal})
      .then(result=>{if(active&&current())setData(result.data);})
      .catch(error=>{if(active&&current())setReadError(error);});
    return()=>{active=false;abort.abort();};
  },[canExport,request,current,kind,page,reload]);

  async function upload(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!file||!canImport||busy||cardBusy||lock.current||blocked)return;
    if(!file.name.toLowerCase().endsWith(".json")||!file.size||file.size>1024*1024){
      setWriteError(new CmsError(400,"JSON_LIMIT","یک فایل JSON غیرخالی با حجم حداکثر یک مگابایت انتخاب کنید."));return;
    }
    lock.current=true;setBusy(true);setWriteError(undefined);
    const body=new FormData();body.set("kind","learning_json");body.set("file",new File([file],file.name,{type:"application/json"}));
    try{
      const result=await request<{artifact:AdminArtifact}>("/artifacts/",{method:"POST",body});
      if(current()){setArtifactId(result.data.artifact.id);setFile(undefined);if(input.current)input.current.value="";}
    }catch(error){if(current())setWriteError(error);}
    finally{lock.current=false;if(current())setBusy(false);}
  }
  function toggle(row:Entry){
    if(busy||cardBusy||uncertain)return;pending.current=null;
    setSelected(previous=>previous.some(item=>item.kind===row.kind&&item.resource_id===row.resource_id)
      ?previous.filter(item=>item.kind!==row.kind||item.resource_id!==row.resource_id)
      :previous.length<20?[...previous,row]:previous);
  }
  async function exportItems(){
    if(!canExport||busy||cardBusy||lock.current||(blocked&&!uncertain)||(!selected.length&&!pending.current))return;
    pending.current??={key:crypto.randomUUID(),items:selected.map(({kind,resource_id,etag})=>({kind,resource_id,etag}))};
    lock.current=true;setBusy(true);setWriteError(undefined);setJobId(undefined);
    try{
      const result=await request<{job:AdminJob}>("/learning/transfer/export/",{method:"POST",
        body:JSON.stringify({items:pending.current.items,request_key:pending.current.key})});
      if(current()){setJobId(result.data.job.id);setSelected([]);pending.current=null;}
    }catch(error){if(current())setWriteError(error);}
    finally{lock.current=false;if(current())setBusy(false);}
  }
  function refresh(){
    if(busy||cardBusy||uncertain)return;
    setWriteError(undefined);setSelected([]);pending.current=null;setReload(value=>value+1);
  }
  if(!canImport&&!canExport)return <CmsState empty="برای انتقال خصوصی، مجوز ورود یا خروجی محتوای آموزشی لازم است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console/content">بازگشت به محتوای مرجع</a>
    <header className="cms-title"><h1>انتقال خصوصی محتوای آموزشی</h1>
      <p className="muted">ورود فقط Draft تازه و غیرفعال می‌سازد؛ محتوای قبلی، پاسخ‌ها و SRS بازنویسی نمی‌شوند. خروجی شامل هیچ اطلاعات کاربر یا سابقهٔ یادگیری نیست.</p>
      <p className="muted">قالب انتقال نسخهٔ اول هنوز پیوندهای منبعِ توضیح علمی را منتقل نمی‌کند؛ برای جلوگیری از حذف بی‌صدای استناد، خروجی محتوایی که اکنون منبع به آن پیوست است با خطای مشخص مسدود می‌شود. در فایل ورودی نیز هیچ منبع علمی یا تأیید بازبینی به‌طور خودکار ساخته نمی‌شود.</p>
    </header>
    <p className="cms-notice">این انتقال، تأیید علمی یا حقوقی و مجوز انتشار ایجاد نمی‌کند. فقط محتوای خصوصی، غیربذری، بایگانی‌نشده و بدون سابقه برای خروجی مجاز است.</p>
    {uncertain?<p role="alert">نتیجهٔ ثبت نامعلوم است؛ انتخاب‌ها و کلید همان درخواست حفظ شده‌اند. فقط تطبیق همان درخواست مجاز است.</p>:
      <PrivateMutationError error={writeError} prefix="artifact" busy={busy} reload={refresh}/>}
    {canImport&&<section className="card stack"><h2>ورود بسته به Draft تازه</h2>
      <p>چهار نوع آزمون، فلش‌کارت، چالش روزانه و تمرین خطاهای شناختی پشتیبانی می‌شوند. حداکثر یک مگابایت، ۲۰ آیتم، ۲۰۰ سؤال و ۲۰۰۰ گزینه.</p>
      <details><summary>قالب نسخه‌مند و نمونهٔ هر چهار نوع</summary>
        <p>نمونه آزمایشی است. slug هدف و گزینه‌های تمرین باید با مفاهیم فعالِ واقعی از نوع خطای شناختی جایگزین شوند. ارتباط اختیاری با مفهوم یا اختلال از slug معتبر استفاده می‌کند.</p>
        <label>نمونهٔ قالب بستهٔ خصوصی<textarea readOnly dir="ltr" rows={12} value={example} spellCheck={false}/></label>
        <a className="cms-link" download="learning-authoring-example.json" href={"data:application/json;charset=utf-8,"+encodeURIComponent(example)}>دریافت نمونه برای ویرایش محلی</a>
      </details>
      <form className="stack" onSubmit={upload}><fieldset disabled={busy||cardBusy||blocked} className="cms-fieldset">
        <label>فایل بستهٔ آموزشی<input ref={input} type="file" accept=".json,application/json" required onChange={event=>setFile(event.target.files?.[0])}/></label>
        <button className="button primary" disabled={!file} type="submit">بارگذاری بسته در قرنطینه</button>
      </fieldset></form>
      <p className="muted">پس از بارگذاری، اعتبارسنجی و ایجاد کار ورود را جداگانه تأیید کنید؛ شروع کار به معنی موفقیت نیست.</p>
      {artifactId&&<ArtifactCard key={artifactId} id={artifactId} onBusy={setCardBusy}/>}
    </section>}
    {canExport&&<section className="card stack"><h2>خروجی خصوصی از نسخه‌های انتخاب‌شده</h2>
      <p>انتخاب‌ها نسخهٔ زمان انتخاب را نگه می‌دارند؛ سرور پیش از ساخت فایل، همان نسخه‌ها و مجوز جاری را دوباره بررسی می‌کند.</p>
      <fieldset className="cms-fieldset" disabled={busy||cardBusy||uncertain}>
        <label>نوع محتوا برای خروجی<select value={kind} onChange={event=>{setKind(event.target.value as LearningKind);setPage(1);}}>
          {Object.entries(learningKindLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}
        </select></label>
        {readError?<CmsState error={readError} retry={()=>setReload(value=>value+1)}/>:!data?<CmsState loading/>:!data.results.length?
          <CmsState empty="محتوای خصوصیِ بدون سابقه در این فهرست وجود ندارد."/>:<ul>{data.results.map(row=>{
            const checked=selected.some(item=>item.kind===row.kind&&item.resource_id===row.resource_id);
            return <li key={row.kind+"-"+row.resource_id}><label><input type="checkbox" checked={checked}
              disabled={!checked&&selected.length>=20} onChange={()=>toggle(row)}/><bdi>{row.label}</bdi> · #{faNumber(row.resource_id)}</label></li>;
          })}</ul>}
        {data&&data.count>20&&<div className="cms-actions"><button type="button" className="button secondary" disabled={page<=1} onClick={()=>setPage(value=>value-1)}>قبل</button>
          <span>صفحهٔ {faNumber(page)}</span><button type="button" className="button secondary" disabled={page*20>=data.count} onClick={()=>setPage(value=>value+1)}>بعد</button></div>}
      </fieldset>
      <p role="status">انتخاب‌شده: {faNumber(selected.length)} از ۲۰</p>
      <div className="cms-actions"><button type="button" className="button primary" disabled={busy||cardBusy||!selected.length||(blocked&&!uncertain)} onClick={()=>void exportItems()}>
        {uncertain?"تطبیق همان درخواست خروجی":"ثبت کار خروجی خصوصی"}</button>
        <button type="button" className="button secondary" disabled={busy||cardBusy||uncertain} onClick={refresh}>بازخوانی و پاک‌کردن انتخاب قدیمی</button>
      </div>
      {uncertain&&<p className="cms-id">کلید پیگیری: <bdi>{pending.current?.key}</bdi></p>}
      {jobId&&<a className="cms-link" href={"/admin-console/jobs/"+encodeURIComponent(jobId)}>پیگیری کار خروجی خصوصی</a>}
      <p className="muted">دریافت بسته به مجوز خروجی آموزشی و مجوز جداگانهٔ دریافت فایل خصوصی نیاز دارد. فایل مدت‌دار است و لغو دسترسی فوراً اعمال می‌شود.</p>
    </section>}
  </div>;
}
