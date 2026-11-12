"use client";
import {useEffect,useState} from "react";
import {cms,CmsError} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Readiness={
  scope:"owner_only_operational_release_gate_observations";
  as_of:string;release_ready:false;public_apply_authorized:false;
  database:{vendor:string;connection:string;atlas_applied_migrations:number;
    atlas_expected_leaf_count:number;pending_atlas_migrations:number;
    migration_history_matches_files:boolean;schema_integrity_proven:false;
    required_runtime_foreign_key_count:number;missing_runtime_foreign_key_count:number;
    runtime_foreign_keys_present:boolean};
  worker:{alive_confirmed:false;successful_polls_recorded:number;
    poll_recently_observed:boolean};
  preparation:{recorded_dossiers:number;publication_approved_dossiers:number;
    attestations_proven:false};
  receipt_observations:{case_receipt_mismatches:number;
    source_receipt_mismatches:number;source_receipt_sample_complete:boolean};
  backup:{state:string;reason:string};hard_blockers:string[];
  manual_decision_required:true;notice:string;
};
const blockerNames:Record<string,string>={
  real_scientific_rights_attestation:"تأیید علمی و حقوقی مستقلِ متصل به نسخه",
  multidomain_public_apply:"انتشار عمومی چنددامنه‌ای همراه با بازیابی و رسید",
  retention_legal_hold_approval:"قانون تأییدشدهٔ نگهداری و Legal Hold",
  live_worker_supervision:"نظارت واقعی Process Manager و سلامت Worker",
  representative_backup_restore:"پشتیبان‌گیری و بازیابی نمایندهٔ محیط واقعی",
  production_tls_secrets:"امنیت TLS، Secrets و تنظیمات سرور واقعی",
  hosted_ci_and_full_db_acceptance:"پذیرش تست‌های Hosted CI و دیتابیس مقصد",
  explicit_release_authorization:"تصمیم و مجوز صریح انسانی برای Release",
  atlas_migration_history_not_current:"Migrationهای Atlas با فایل‌های کد هماهنگ نیستند",
  atlas_runtime_tables_missing:"حداقل یک جدول حیاتی CMS با وجود تاریخچهٔ Migration ثبت‌شده در دیتابیس وجود ندارد",
  atlas_runtime_columns_missing:"حداقل یک ستون ضروری در جدول‌های حیاتی CMS وجود ندارد؛ انتشار و بررسی مدل‌ها مسدود است",
  atlas_runtime_idempotency_constraints_missing:"محدودیت یکتایی ضروری برای جلوگیری از درخواست تکراری و رسید تکراری از ساختار دیتابیس حذف شده است",
  atlas_runtime_foreign_keys_missing:"حداقل یک رابطهٔ Foreign Key ضروری در ساختار دیتابیس وجود ندارد؛ انتشار تا بررسی و بازیابی ساختار مسدود است",
  observed_receipt_inconsistencies:"مغایرت در رسیدهای ثبت‌شدهٔ انتشار یا منابع",
  source_receipt_audit_sample_incomplete:"همهٔ رسیدهای منابع در سقف نمونه بررسی نشده‌اند",
};
type Health={
  scope:string;as_of:string;
  database:{connection:string;vendor:string;atlas_applied_migrations:number;
    atlas_latest_applied:string|null;migration_state:string};
  jobs:{total:number;by_status:Record<string,number>;oldest_queued_at:string|null;stale_lease_count:number;
    queued_ready_count:number;queued_scheduled_count:number;
    oldest_ready_at:string|null;next_scheduled_at:string|null;
    ready_queue_age_seconds:number|null;
    running_expired_lease_count:number;running_missing_lease_count:number;
    worker_liveness_proven:false;notice:string};
  worker:{alive_confirmed:false;latest_job_heartbeat:string|null;notice:string;
    last_successful_poll_at:string|null;successful_polls_recorded:number;
    fresh_window_seconds:number;poll_recently_observed:boolean};
  queue_triage:{scope:string;threshold_seconds:number;ready_count:number;
    scheduled_future_count:number;overdue_ready_count:number;
    running_expired_lease_count:number;running_missing_lease_count:number;
    signals:string[];requires_operator_review:boolean;
    worker_outage_proven:false;automatic_repair_available:false;notice:string};
  artifacts:{total:number;unpurged_bytes:number;unpurged_count:number};
  backup:{state:string;reason:string};
  source_plan_receipts:{
    scope:"source_plan_receipt_history_and_bounded_result_sample";
    source_plans_total:number;source_plans_without_receipt:number;
    source_receipts_total:number;source_histories_total:number;
    source_receipts_without_history:number;source_histories_without_receipt:number;
    sampled_receipts:number;sample_complete:boolean;
    source_receipt_result_history_mismatches:number;source_receipt_result_successor_mismatches:number;
    total_observed_mismatches:number;full_source_integrity_proven:false;
    repair_available:false;notice:string;
  };
  publication_receipts:{
    scope:"case_revision_structural_receipts_only";
    case_plans_total:number;case_plans_applied:number;case_plans_withdrawn:number;
    case_receipts_total:number;case_plans_missing_applied_receipt:number;
    case_plans_missing_withdrawn_receipt:number;case_receipt_digest_mismatches:number;
    total_observed_mismatches:number;full_publication_integrity_proven:false;
    repair_available:false;notice:string;
  };
};
export default function OperationsHealth(){
  const {can}=useCms();const allowed=can("cms_owner");
  const [data,setData]=useState<Health>();
  const [readiness,setReadiness]=useState<Readiness>();
  const [gateError,setGateError]=useState("");
  const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const [version,setVersion]=useState(0);
  useEffect(()=>{
    if(!allowed)return;
    let active=true;setBusy(true);setError("");setGateError("");
    void Promise.allSettled([
      cms<Health>("/operations/health/"),
      cms<Readiness>("/operations/release-readiness/"),
    ]).then(([health,gates])=>{
      if(!active)return;
      if(health.status==="fulfilled")setData(health.value.data);
      else{setData(undefined);setError(health.reason instanceof CmsError?
        health.reason.message:"گزارش سلامت عملیاتی دریافت نشد.");}
      if(gates.status==="fulfilled")setReadiness(gates.value.data);
      else{setReadiness(undefined);setGateError(gates.reason instanceof CmsError?
        gates.reason.message:"گزارش گیت‌های Release در دسترس نیست و انتشار نباید انجام شود.");}
    }).finally(()=>{if(active)setBusy(false);});
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
    {gateError&&<p role="alert">{gateError}</p>}
    {busy&&!data&&<CmsState loading/>}
    {data&&<div className="stack">
      <p className="muted">زمان ثبت سرور: <time dateTime={data.as_of}>{data.as_of}</time></p>
      <section className="card stack"><h2>دیتابیس و Migration</h2>
        <p>اتصال: <strong>{data.database.connection}</strong></p>
        <p>موتور: <code>{data.database.vendor}</code></p>
        <p>Migrationهای اعمال‌شدهٔ Atlas: {data.database.atlas_applied_migrations.toLocaleString("fa-IR")}</p>
        <p>آخرین Migration اعمال‌شده: <code dir="ltr" style={{display:"block",overflowWrap:"anywhere"}}>{data.database.atlas_latest_applied??"ثبت نشده"}</code></p>
        <p className="muted">این گزارش فقط سابقهٔ Apply است و به‌تنهایی drift schema یا آمادگی production را اثبات نمی‌کند.</p>
      </section>
      {readiness&&<section className="card stack" aria-label="گیت‌های آمادگی انتشار P21">
        <h2>گیت‌های انتشار v1.0، فقط گزارش</h2>
        <p role="status"><strong>انتشار هنوز مجاز نیست.</strong> این گزارش فقط شواهد محلی ثبت‌شده را نشان می‌دهد و امکان Release یا Deploy ندارد.</p>
        <p>پرونده‌های آماده‌سازی موجود: {readiness.preparation.recorded_dossiers.toLocaleString("fa-IR")}؛
          تأیید انتشار واقعی از این پرونده‌ها: {readiness.preparation.publication_approved_dossiers.toLocaleString("fa-IR")}</p>
        <p>Migrationهای Atlas در فایل‌ها ولی اعمال‌نشده:
          {readiness.database.pending_atlas_migrations.toLocaleString("fa-IR")}؛
          مطابقت تاریخچهٔ Migration با فایل‌ها: {readiness.database.migration_history_matches_files?"بله":"خیر"}</p>
        <p>روابط Foreign Key حیاتیِ مورد انتظار: {readiness.database.required_runtime_foreign_key_count.toLocaleString("fa-IR")}؛
          رابطهٔ مفقود در ساختار: {readiness.database.missing_runtime_foreign_key_count.toLocaleString("fa-IR")}</p>
        <p className="muted">وجود تعریف روابط خارجی در Schema، بررسی تمام ردیف‌های داده یا تأیید محیط Production نیست.</p>
        <p>مغایرت‌های ساختاری رسیدهای کیس: {readiness.receipt_observations.case_receipt_mismatches.toLocaleString("fa-IR")}؛
          منابع: {readiness.receipt_observations.source_receipt_mismatches.toLocaleString("fa-IR")}</p>
        <h3>موانع باقی‌ماندهٔ Release</h3>
        <ul>{readiness.hard_blockers.map(code=>
          <li key={code}>{blockerNames[code]??code}</li>)}</ul>
        <p className="muted">صفر شدن یک شمارش یا تازه بودن Poll، جای تأیید انسانی، حقوقی، علمی، CI یا تست Backup/Restore واقعی را نمی‌گیرد.</p>
      </section>}
      <section className="card stack" aria-label="وضعیت صف آماده و زمان‌بندی‌شده"><h2>صف Job</h2>
        <p>کل: {data.jobs.total.toLocaleString("fa-IR")}</p>
        <ul>{Object.entries(data.jobs.by_status).map(([status,count])=>
          <li key={status}><code>{status}</code> : {count.toLocaleString("fa-IR")}</li>)}</ul>
        <p>در صف آمادهٔ اجرا: <strong>{data.jobs.queued_ready_count.toLocaleString("fa-IR")}</strong>؛
          زمان‌بندی‌شده برای آینده: <strong>{data.jobs.queued_scheduled_count.toLocaleString("fa-IR")}</strong></p>
        <p>قدیمی‌ترین زمان آمادهٔ اجرا: {data.jobs.oldest_ready_at??"موردی وجود ندارد"}؛
          عمر انتظار پس از موعد اجرا: {data.jobs.ready_queue_age_seconds===null?"قابل محاسبه نیست":data.jobs.ready_queue_age_seconds.toLocaleString("fa-IR")+" ثانیه"}</p>
        <p>نزدیک‌ترین Job زمان‌بندی‌شده: {data.jobs.next_scheduled_at??"موردی وجود ندارد"}</p>
        <p>Job در حال اجرا با Lease منقضی: {data.jobs.running_expired_lease_count.toLocaleString("fa-IR")}؛
          Job در حال اجرا با توکن یا تاریخ انقضای Lease ناقص: {data.jobs.running_missing_lease_count.toLocaleString("fa-IR")}</p>
        <p className="muted">این اعداد تصویر لحظه‌ای وضعیت‌های ثبت‌شده‌اند. زمان‌بندی آینده عقب‌ماندگی Worker نیست؛ Lease ناقص نیز به‌تنهایی اثبات توقف Worker نیست. زنده‌بودن واقعی Worker هنوز احراز نشده است.</p>
      </section>
      <section className="card stack" aria-label="نشانه‌های نیازمند بررسی صف P18">
        <h2>تشخیص اولیهٔ صف، بدون تغییر Job</h2>
        <p role="status">{data.queue_triage.requires_operator_review?
          "در وضعیت ثبت‌شدهٔ صف، مواردی برای بررسی اپراتور دیده شده است.":
          "در بررسی محدود فعلی نشانهٔ مشخصی دیده نشد؛ این نتیجه به معنی سالم بودن قطعی Worker نیست."}</p>
        <p>Job آمادهٔ اجرا با تأخیر بیش از {data.queue_triage.threshold_seconds.toLocaleString("fa-IR")} ثانیه:
          {data.queue_triage.overdue_ready_count.toLocaleString("fa-IR")}</p>
        <p>Lease منقضی: {data.queue_triage.running_expired_lease_count.toLocaleString("fa-IR")}؛
          Lease با توکن یا انقضای ناقص: {data.queue_triage.running_missing_lease_count.toLocaleString("fa-IR")}</p>
        <p className="muted">Jobهای زمان‌بندی‌شده برای آینده در تأخیر صف حساب نمی‌شوند. این اعداد از وضعیت ثبت‌شده‌اند و اثبات خرابی Process، SLA یا حق Repair خودکار نیستند.</p>
      </section>
      <section className="card stack" aria-label="شواهد Poll موفق Worker"><h2>Worker و Artifact</h2>
        <p>آخرین Poll موفق ثبت‌شده: {data.worker.last_successful_poll_at??"هنوز ثبت نشده است"}</p>
        <p>Pollهای موفق ثبت‌شده: {data.worker.successful_polls_recorded.toLocaleString("fa-IR")}؛
          پنجرهٔ تازگی: {data.worker.fresh_window_seconds.toLocaleString("fa-IR")} ثانیه</p>
        <p role="status">{data.worker.poll_recently_observed?
          "Poll موفق در پنجرهٔ تازگی مشاهده شده است؛ زنده بودن فعلی Worker اثبات نمی‌شود.":
          "Poll موفق تازه مشاهده نشده است؛ ممکن است Worker اجرا نشده، متوقف یا مشغول اجرای Job طولانی باشد."}</p>
        <p>آخرین Heartbeat مرتبط با Job: {data.worker.latest_job_heartbeat??"هیچ‌کدام"}</p>
        <p><strong>زنده بودن Worker هنوز تأیید نشده است.</strong> Poll ذخیره‌شده جای نظارت Process Manager و تست E2E صف را نمی‌گیرد.</p>
        <p>Artifactها: {data.artifacts.total.toLocaleString("fa-IR")}</p>
        <p>Artifact پاک‌نشده: {data.artifacts.unpurged_count.toLocaleString("fa-IR")} |
          مجموع بایت: {data.artifacts.unpurged_bytes.toLocaleString("fa-IR")}</p>
      </section>
      <section className="card stack" aria-label="بازبینی ساختاری رسیدهای انتشار">
        <h2>رسیدهای انتشار CaseRevision، فقط بررسی ساختاری</h2>
        <p>برنامه‌ها: {data.publication_receipts.case_plans_total.toLocaleString("fa-IR")}؛
          وضعیت Applied: {data.publication_receipts.case_plans_applied.toLocaleString("fa-IR")}؛
          Withdrawn: {data.publication_receipts.case_plans_withdrawn.toLocaleString("fa-IR")}</p>
        <p>رسیدها: {data.publication_receipts.case_receipts_total.toLocaleString("fa-IR")}</p>
        <p role="status">مغایرت‌های مشاهده‌شده: {data.publication_receipts.total_observed_mismatches.toLocaleString("fa-IR")}</p>
        <ul>
          <li>Applied بدون رسید: {data.publication_receipts.case_plans_missing_applied_receipt.toLocaleString("fa-IR")}</li>
          <li>Withdrawn بدون رسید: {data.publication_receipts.case_plans_missing_withdrawn_receipt.toLocaleString("fa-IR")}</li>
          <li>ناسازگاری اثرانگشت رسید و برنامه: {data.publication_receipts.case_receipt_digest_mismatches.toLocaleString("fa-IR")}</li>
        </ul>
        <p className="muted">صفر بودن مغایرت به معنی تأیید علمی/حقوقی یا سلامت کامل انتشار و وضعیت عمومی نیست. بررسی خودکار بدون تغییر داده انجام می‌شود؛ Repair از این صفحه وجود ندارد.</p>
      </section>
      <section className="card stack" aria-label="بررسی ساختاری رسیدهای طرح منبع">
        <h2>رسید و تاریخچهٔ Source Plan، فقط بررسی ساختاری</h2>
        <p>طرح‌ها: {data.source_plan_receipts.source_plans_total.toLocaleString("fa-IR")}؛
          رسیدها: {data.source_plan_receipts.source_receipts_total.toLocaleString("fa-IR")}؛
          ردیف‌های تاریخچه: {data.source_plan_receipts.source_histories_total.toLocaleString("fa-IR")}</p>
        <p>طرح‌های بدون رسید: {data.source_plan_receipts.source_plans_without_receipt.toLocaleString("fa-IR")}.
          <span className="muted"> طرح پیش‌نمایش ممکن است هنوز اعمال نشده باشد؛ این عدد به‌تنهایی خطا نیست.</span></p>
        <p role="status">مغایرت‌های ساختاری مشاهده‌شده: {data.source_plan_receipts.total_observed_mismatches.toLocaleString("fa-IR")}</p>
        <ul>
          <li>رسید بدون تاریخچه: {data.source_plan_receipts.source_receipts_without_history.toLocaleString("fa-IR")}</li>
          <li>تاریخچه بدون رسید برنامه: {data.source_plan_receipts.source_histories_without_receipt.toLocaleString("fa-IR")}</li>
          <li>ناسازگاری شناسه‌های تاریخچه در نتیجهٔ رسید: {data.source_plan_receipts.source_receipt_result_history_mismatches.toLocaleString("fa-IR")}</li>
          <li>ناسازگاری شناسه‌های جانشین در نتیجهٔ رسید: {data.source_plan_receipts.source_receipt_result_successor_mismatches.toLocaleString("fa-IR")}</li>
        </ul>
        <p>رسیدهای بررسی‌شده برای تطبیق شناسه: {data.source_plan_receipts.sampled_receipts.toLocaleString("fa-IR")}؛
          {data.source_plan_receipts.sample_complete?" همهٔ رسیدهای فعلی در سقف نمونه قرار داشتند.":" سقف ۲۰۰ رسید اخیر؛ بخشی از رسیدها بررسی نشده‌اند."}</p>
        <p className="muted">شمار مغایرت‌ها جمع نشانه‌هاست و ممکن است یک رکورد چند بار شمرده شود. هیچ شناسه یا محتوای خصوصی نشان داده نمی‌شود؛ تطبیق شناسه‌ها اثبات سلامت Apply، حق انتشار، بازبینی علمی یا کامل بودن Backup نیست. Repair و تغییر داده وجود ندارد.</p>
      </section>
      <section className="card stack"><h2>Backup</h2>
        <p><strong>Adapter پشتیبان‌گیری از این پنل متصل نیست.</strong></p>
        <p className="muted">وضعیت: {data.backup.state} | این موضوع به معنای فقدان backup در کل محیط نیست، فقط این مسیر CMS قابلیت اجرای آن را ندارد.</p>
      </section>
    </div>}
  </div>;
}
