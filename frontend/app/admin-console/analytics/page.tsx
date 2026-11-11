"use client";
import {useEffect,useState} from "react";
import {cms,CmsError} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type DomainCounts={states:number;with_current_revision:number};
type Analytics={
  scope:"owner_recorded_pipeline_counts_only";measured_at:string;
  content:{
    states_total:number;states_with_current_revision:number;states_without_current_revision:number;
    revisions_total:number;current_revision_statuses:Record<string,number>;
    recorded_publication_markers:Record<string,number>;pointer_state_mismatches:number;
    by_domain:Record<string,DomainCounts>;publication_markers_are_authorization:false;
  };
  reviews:{tasks_total:number;tasks_by_status:Record<string,number>;decisions_total:number;task_status_not_verified_approval:true};
  governance:Record<"rights"|"terminology",{total:number;by_status:Record<string,number>;
    decisions_total:number;status_not_verified_clearance:true}>;
  jobs:{total:number;by_status:Record<string,number>};
  sources:{canonical_references_total:number;versioned_source_states_total:number;
    archived_states_total:number;deleted_states_total:number};
  publication_authorized:false;scientific_rights_attested:false;
  complete_release_readiness_proven:false;notice:string;
};
const domains:Record<string,string>={
  core:"مفاهیم و اختلال‌ها",dsm:"DSM",therapy:"درمان‌ها",history:"تاریخچه و نظریه‌ها",
  brain:"اطلس مغز",assessment:"ارزیابی‌ها",unmapped:"خارج از دامنهٔ ثبت‌شده"
};
const statuses:Record<string,string>={
  draft:"پیش‌نویس",submitted:"ارسال‌شده",in_review:"در حال بررسی",changes_requested:"نیازمند اصلاح",
  approved:"وضعیت ثبت‌شدهٔ تأیید",superseded:"جایگزین‌شده",discarded:"کنارگذاشته‌شده",
  legacy:"دادهٔ موروثی",queued:"در صف",assigned:"ارجاع‌شده",rejected:"ردشده",
  cancelled:"لغوشده",current:"علامت فعلی",pending_update:"در انتظار تغییر",
  withdrawn:"برداشته‌شده",never_published:"هرگز منتشرنشده",revoked:"لغو اعتبار",
  running:"در حال اجرا",succeeded:"موفق",failed:"ناموفق",reconciling:"در حال تطبیق",
  other:"وضعیت دیگر"
};
function DisplayCounts({counts}:{counts:Record<string,number>}){
  return <ul>{Object.entries(counts).map(([key,value])=><li key={key}>
    {statuses[key]??key}: <strong>{value.toLocaleString("fa-IR")}</strong>
  </li>)}</ul>;
}
export default function AnalyticsOverview(){
  const {can}=useCms();const allowed=can("cms_owner");
  const [data,setData]=useState<Analytics>();
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const [generation,setGeneration]=useState(0);
  useEffect(()=>{
    if(!allowed)return;
    let active=true;setBusy(true);setError("");setData(undefined);
    void cms<Analytics>("/analytics/overview/")
      .then(result=>{if(active)setData(result.data);})
      .catch(e=>{if(active)setError(e instanceof CmsError?e.message:"گزارش دریافت نشد.");})
      .finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[allowed,generation]);
  if(!allowed)return <CmsState empty="این گزارش فقط برای مالک CMS در دسترس است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title"><p className="eyebrow">P19 | Internal Analytics</p>
      <h1>گزارش شمارش مسیرهای داخلی CMS</h1>
      <p className="muted">فقط شمارش رکوردهای موجود است. وضعیت ثبت‌شدهٔ تأیید، مدرک علمی یا حقوقی معتبر و مجوز انتشار نیست. این گزارش شامل اطلاعات یا رفتار فردی کاربران نمی‌شود.</p>
    </div>
    <button type="button" className="button secondary" disabled={busy} onClick={()=>setGeneration(n=>n+1)}>
      {busy?"در حال دریافت…":"بازخوانی شمارش‌ها"}</button>
    {error&&<p role="alert">{error}</p>}
    {busy&&!data&&<CmsState loading/>}
    {data&&<>
      <p className="muted">زمان سنجش سرور: <time dateTime={data.measured_at}>{data.measured_at}</time></p>
      <section className="card stack">
        <h2>مخرج شمارش محتوای مدیریتی</h2>
        <p>رکوردهای ContentState: <strong>{data.content.states_total.toLocaleString("fa-IR")}</strong>؛
          دارای نسخهٔ جاری: {data.content.states_with_current_revision.toLocaleString("fa-IR")}؛
          بدون نسخهٔ جاری: {data.content.states_without_current_revision.toLocaleString("fa-IR")}</p>
        <p>همهٔ نسخه‌های ذخیره‌شده (از جمله نسخه‌های قدیمی): {data.content.revisions_total.toLocaleString("fa-IR")}</p>
        <p>ارجاع نسخهٔ جاری به رکورد نادرست: {data.content.pointer_state_mismatches.toLocaleString("fa-IR")}</p>
        <div className="cms-table-wrap"><table><thead><tr><th scope="col">حوزه</th><th scope="col">کل رکوردها</th><th scope="col">دارای نسخهٔ جاری</th></tr></thead>
          <tbody>{Object.entries(data.content.by_domain).map(([name,value])=><tr key={name}>
            <th scope="row">{domains[name]??name}</th><td>{value.states.toLocaleString("fa-IR")}</td>
            <td>{value.with_current_revision.toLocaleString("fa-IR")}</td>
          </tr>)}</tbody></table></div>
        <h3>وضعیت آخرین نسخهٔ مرتبط</h3><DisplayCounts counts={data.content.current_revision_statuses}/>
        <h3>علامت انتشار ثبت‌شده در ContentState</h3><DisplayCounts counts={data.content.recorded_publication_markers}/>
        <p className="muted">مخرج وضعیت نسخه، فقط رکوردهای دارای نسخهٔ جاری است. تعداد کل نسخه‌ها مخرج جداگانه دارد. حتی علامت current، بدون گیت‌های مستقل P16 اثبات مجوز انتشار نیست.</p>
      </section>
      <section className="card stack"><h2>داوری‌های ثبت‌شده</h2>
        <p>وظایف: {data.reviews.tasks_total.toLocaleString("fa-IR")}؛ تصمیم‌های ذخیره‌شده: {data.reviews.decisions_total.toLocaleString("fa-IR")}</p>
        <DisplayCounts counts={data.reviews.tasks_by_status}/>
        <p className="muted">وضعیت approved در ReviewTask به‌تنهایی صحت تصمیم، تازه بودن مدرک یا تأیید انتشار را اثبات نمی‌کند.</p>
      </section>
      {(["rights","terminology"] as const).map(kind=><section className="card stack" key={kind}>
        <h2>{kind==="rights"?"سوابق حقوق محتوا":"اصطلاحات و ترجمه"}</h2>
        <p>رکوردها: {data.governance[kind].total.toLocaleString("fa-IR")}؛
          تصمیم‌ها: {data.governance[kind].decisions_total.toLocaleString("fa-IR")}</p>
        <DisplayCounts counts={data.governance[kind].by_status}/>
        <p className="muted">وضعیت approved صرفاً یک وضعیت پایگاه‌داده است، نه اثبات اعتبار حقوقی یا علمی.</p>
      </section>)}
      <section className="card stack"><h2>صف پردازش و منابع</h2>
        <p>کل Jobها: {data.jobs.total.toLocaleString("fa-IR")}</p><DisplayCounts counts={data.jobs.by_status}/>
        <p>منابع مرجع: {data.sources.canonical_references_total.toLocaleString("fa-IR")}؛
          وضعیت‌های نسخه‌دار منبع: {data.sources.versioned_source_states_total.toLocaleString("fa-IR")}؛
          آرشیوشده: {data.sources.archived_states_total.toLocaleString("fa-IR")}؛
          علامت حذف: {data.sources.deleted_states_total.toLocaleString("fa-IR")}</p>
        <p className="muted">منابع مرجع و SourceState دو جمعیت متفاوت‌اند و نباید از هم کم شوند.</p>
      </section>
      <p className="muted" role="status">این شمارش‌ها به‌تنهایی گواه سلامت جامع، نسخهٔ یکپارچهٔ هم‌زمان، حق انتشار یا آمادگی Release نیستند. هیچ داده‌ای تغییر نمی‌کند.</p>
    </>}
  </div>;
}
