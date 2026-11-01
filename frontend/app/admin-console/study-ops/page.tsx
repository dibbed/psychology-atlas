"use client";
import {useEffect,useState} from "react";
import {cms,CmsError} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Counter={total:number;by_status:Record<string,number>};
type Overview={scope:string;as_of:string;plans:Counter;blocks:Counter;
  sessions:Counter;activities:Counter;feedback:Counter;
  mastery_inferred_from_session_completion:false};
const kinds:{key:keyof Pick<Overview,"plans"|"blocks"|"sessions"|"activities"|"feedback">;title:string;description:string}[]=[
  {key:"plans",title:"برنامه‌های مطالعه",description:"همهٔ برنامه‌های موجود، براساس وضعیت واقعی"},
  {key:"blocks",title:"بلوک‌های مطالعه",description:"بلوک‌ها براساس pending، completed و وضعیت‌های دیگر"},
  {key:"sessions",title:"جلسه‌های مطالعه",description:"مدت و وضعیت جلسه، جدا از شواهد یادگیری"},
  {key:"activities",title:"رویدادهای ثبت‌شده",description:"فقط تعداد رویدادهای واقعی موتور یادگیری"},
  {key:"feedback",title:"بازخورد پیشنهادها",description:"تعداد بازخوردهای ذخیره‌شده، بدون حدس رضایت"},
];
export default function StudyOps(){
  const {can}=useCms();const allowed=can("cms_study_view");
  const [data,setData]=useState<Overview>();
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);const [reload,setReload]=useState(0);
  useEffect(()=>{
    if(!allowed)return;let active=true;
    setBusy(true);setError("");
    void cms<Overview>("/study/overview/")
      .then(r=>{if(active)setData(r.data);})
      .catch(e=>{if(active)setError(e instanceof CmsError?e.message:"وضعیت عملیاتی دریافت نشد.");})
      .finally(()=>{if(active)setBusy(false);});
    return ()=>{active=false;};
  },[allowed,reload]);
  if(!allowed)return <CmsState empty="دسترسی به بازرسی عملیاتی Study نیازمند مجوز cms_study_view است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title"><p className="eyebrow">P15 | Study Operations</p>
      <h1>وضعیت عملیاتی موتور مطالعه</h1>
      <p className="muted">آمار این صفحه مستقیم از داده‌های ثبت‌شدهٔ سرور محاسبه می‌شود. این بخش هویت، یادداشت، نمره یا سابقهٔ فردی کاربران را نشان نمی‌دهد و هیچ پیشرفتی ایجاد نمی‌کند.</p>
    </div>
    <button className="button secondary" type="button" disabled={busy}
      onClick={()=>setReload(v=>v+1)}>{busy?"در حال دریافت…":"نوسازی وضعیت از سرور"}</button>
    {error&&<p role="alert">{error}</p>}
    {busy&&!data&&<CmsState loading/>}
    {data&&<>
      <p className="muted">آخرین اندازه‌گیری سرور: <time dateTime={data.as_of}>{data.as_of}</time></p>
      <div className="cms-metrics">{kinds.map(item=>{
        const metric=data[item.key];
        return <section key={item.key} className="card stack">
          <h2>{item.title}</h2>
          <p className="muted">{item.description}</p>
          <p><strong>{metric.total.toLocaleString("fa-IR")}</strong> رکورد</p>
          <dl>{Object.entries(metric.by_status).map(([name,count])=>
            <div key={name} className="cms-filters"><dt><code dir="ltr">{name}</code></dt>
              <dd>{count.toLocaleString("fa-IR")}</dd></div>)}</dl>
        </section>;
      })}</div>
      <p className="muted">تکمیل یک جلسه به‌تنهایی به معنی mastery یا کسب امتیاز علمی نیست؛ نرخ‌های بدون مخرج معتبر نمایش داده نمی‌شوند.</p>
    </>}
  </div>;
}
