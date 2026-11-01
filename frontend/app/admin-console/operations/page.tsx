"use client";
import {useEffect,useState} from "react";
import {cms,CmsError} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Health={
  scope:string;as_of:string;
  database:{connection:string;vendor:string;atlas_applied_migrations:number;
    atlas_latest_applied:string|null;migration_state:string};
  jobs:{total:number;by_status:Record<string,number>;oldest_queued_at:string|null;stale_lease_count:number};
  worker:{alive_confirmed:false;latest_job_heartbeat:string|null;notice:string};
  artifacts:{total:number;unpurged_bytes:number;unpurged_count:number};
  backup:{state:string;reason:string};
};
export default function OperationsHealth(){
  const {can}=useCms();const allowed=can("cms_owner");
  const [data,setData]=useState<Health>();
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const [version,setVersion]=useState(0);
  useEffect(()=>{
    if(!allowed)return;
    let active=true;setBusy(true);setError("");
    void cms<Health>("/operations/health/")
      .then(res=>{if(active)setData(res.data);})
      .catch(e=>{if(active)setError(e instanceof CmsError?e.message:"وضعیت عملیاتی دریافت نشد.");})
      .finally(()=>{if(active)setBusy(false);});
    return ()=>{active=false;};
  },[allowed,version]);
  if(!allowed)return <CmsState empty="گزارش عملیات زیرساخت فقط برای مالک CMS در دسترس است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title"><p className="eyebrow">P18 | Operations</p>
      <h1>سلامت سرویس و صف عملیاتی</h1>
      <p className="muted">فقط قرائت واقعی از دیتابیس و Jobهای ثبت‌شده است؛ دسترسی به ترمینال، SQL، secret، فایل backup یا Restore در این صفحه وجود ندارد.</p>
    </div>
    <button type="button" className="button secondary" disabled={busy}
      onClick={()=>setVersion(v=>v+1)}>{busy?"در حال دریافت…":"بررسی دوباره"}</button>
    {error&&<p role="alert">{error}</p>}
    {busy&&!data&&<CmsState loading/>}
    {data&&<div className="stack">
      <p className="muted">زمان ثبت سرور: <time dateTime={data.as_of}>{data.as_of}</time></p>
      <section className="card stack"><h2>دیتابیس و Migration</h2>
        <p>اتصال: <strong>{data.database.connection}</strong></p>
        <p>موتور: <code>{data.database.vendor}</code></p>
        <p>Migrationهای اعمال‌شدهٔ Atlas: {data.database.atlas_applied_migrations.toLocaleString("fa-IR")}</p>
        <p>آخرین Migration اعمال‌شده: <code dir="ltr">{data.database.atlas_latest_applied??"ثبت نشده"}</code></p>
        <p className="muted">این گزارش فقط سابقهٔ Apply است و به‌تنهایی drift schema یا آمادگی production را اثبات نمی‌کند.</p>
      </section>
      <section className="card stack"><h2>صف Job</h2>
        <p>کل: {data.jobs.total.toLocaleString("fa-IR")} | Lease منقضی: {data.jobs.stale_lease_count.toLocaleString("fa-IR")}</p>
        <ul>{Object.entries(data.jobs.by_status).map(([status,count])=>
          <li key={status}><code>{status}</code> : {count.toLocaleString("fa-IR")}</li>)}</ul>
        <p>قدیمی‌ترین Job صف: {data.jobs.oldest_queued_at??"وجود ندارد"}</p>
      </section>
      <section className="card stack"><h2>Worker و Artifact</h2>
        <p>آخرین heartbeat مشاهده‌شده: {data.worker.latest_job_heartbeat??"هیچ‌کدام"}</p>
        <p><strong>زنده بودن Worker هنوز تأیید نشده است.</strong> heartbeat قدیمی به‌تنهایی تضمین کارکرد نیست.</p>
        <p>Artifactها: {data.artifacts.total.toLocaleString("fa-IR")}</p>
        <p>Artifact پاک‌نشده: {data.artifacts.unpurged_count.toLocaleString("fa-IR")} |
          مجموع بایت: {data.artifacts.unpurged_bytes.toLocaleString("fa-IR")}</p>
      </section>
      <section className="card stack"><h2>Backup</h2>
        <p><strong>Adapter پشتیبان‌گیری از این پنل متصل نیست.</strong></p>
        <p className="muted">وضعیت: {data.backup.state} | این موضوع به معنای فقدان backup در کل محیط نیست، فقط این مسیر CMS قابلیت اجرای آن را ندارد.</p>
      </section>
    </div>}
  </div>;
}
