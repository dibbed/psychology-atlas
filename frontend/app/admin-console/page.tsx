"use client";
import { useEffect, useState } from "react";
import { ArrowLeft, FilePenLine, History, Library } from "lucide-react";
import { cms, CmsDashboard, CmsError, cmsDate } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { CmsState, useCms } from "@/components/cms/CmsShell";

export default function AdminHome() {
  const { can } = useCms();
  const [data, setData] = useState<CmsDashboard>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const allowed = can("cms_dashboard");
  useEffect(() => {
    if (!allowed) return;
    let active = true; setData(undefined); setError(undefined);
    cms<CmsDashboard>("/dashboard/").then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [allowed, retry]);
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  if (error) return <CmsState error={error} retry={() => setRetry(value => value + 1)} />;
  if (!data) return <CmsState loading />;
  const category = data.content?.find(item => item.kind === "category");
  return <div className="stack">
    <div className="cms-title"><p className="eyebrow">فضای کار تحریریه</p><h1>خانهٔ مدیریت</h1><p className="muted">پیشنهادهای محتوا و ردِ عملیات در همین محیط</p></div>
    <div className="cms-metrics">
      {category && <><a className="card cms-metric" href="/admin-console/content/category"><Library aria-hidden="true" /><span>دسته‌بندی‌های دارای سابقهٔ CMS</span><strong>{faNumber(category.total)}</strong><small>تمام anchorها، شامل میراث و پیش‌نویس <ArrowLeft size={14} /></small></a>
        <a className="card cms-metric" href="/admin-console/content/category?status=draft"><FilePenLine aria-hidden="true" /><span>آخرین نسخهٔ پیش‌نویس دسته‌بندی</span><strong>{faNumber(category.drafts)}</strong><small>آخرین revision هر دسته‌بندی <ArrowLeft size={14} /></small></a></>}
      {data.audit && <a className="card cms-metric" href="/admin-console/audit"><History aria-hidden="true" /><span>رویدادهای ثبت‌شده</span><strong>{faNumber(data.audit.count)}</strong><small>کل تاریخچهٔ مجاز، همهٔ outcomeها <ArrowLeft size={14} /></small></a>}
    </div>
    <p className="cms-freshness">اندازه‌گیری سرور: <time dateTime={data.measured_at}>{cmsDate(data.measured_at)}</time> · زمان محلی مرورگر · شمارش anchorهای CMS، نه آمار انتشار عمومی</p>
    {can("cms_enter") && <section className="card stack"><h2>راهنمای فارسی مدیر</h2><p className="muted">مسیرهای واقعی محتوا، داوری، کاربران، یادگیری و عملیات؛ با توضیح مرزهای تکمیل‌نشده</p><a className="button secondary" href="/admin-console/help">خواندن راهنما</a></section>}
    {can("cms_owner") && <section className="card stack"><h2>تحلیل شمارش‌های داخلی CMS</h2><p className="muted">مخرج جداگانه برای رکوردها، نسخه‌ها، وظایف بازبینی و حقوق ثبت‌شده؛ بدون فرض اعتبار انتشار</p><a className="button secondary" href="/admin-console/analytics">باز کردن گزارش داخلی</a></section>}
    {can("cms_owner") && <section className="card stack"><h2>سلامت سرویس، صف Job و وضعیت Backup</h2><p className="muted">مشاهدهٔ فرادادهٔ عملیاتی بدون اجرای ترمینال، SQL، backup یا restore</p><a className="button secondary" href="/admin-console/operations">بررسی سلامت عملیات</a></section>}
    {can("cms_search") && <section className="card stack"><h2>جست‌وجوی داخلی امن</h2><p className="muted">پیداکردن محتوای مجاز با شناسهٔ لاتین، بدون نمایه‌کردن دادهٔ خصوصی کاربران</p><a className="button secondary" href="/admin-console/search">باز کردن جست‌وجوی داخلی</a></section>}
    {(can("cms_publication_validate_cases") || can("cms_publication_validate_learning")) && <section className="card stack"><h2>بررسی مقدماتی انتشار</h2><p className="muted">صف خصوصی نامزدها و موانع حقوقی و علمی، بدون دسترسی به Apply یا انتشار عمومی</p><a className="button secondary" href="/admin-console/publication-preflight">مشاهدهٔ صف انتشار</a></section>}
    {can("cms_study_view") && <section className="card stack"><h2>عملیات Study و توصیه‌ها</h2><p className="muted">شمارش مستقیم وضعیت برنامه‌ها، بلوک‌ها، جلسات و بازخورد بدون دسترسی به داده‌های خصوصی یادگیرندگان</p><a className="button secondary" href="/admin-console/study-ops">گزارش عملیاتی Study</a></section>}
    {can("cms_user_view") && <section className="card stack"><h2>مدیریت امن حساب‌ها</h2><p className="muted">جست‌وجوی حساب و نمایش مجوزهای قابل‌مشاهده، بدون دسترسی به دادهٔ خصوصی یادگیری</p><a className="button secondary" href="/admin-console/accounts">باز کردن فهرست حساب‌ها</a></section>}
    {can("cms_core_view") && <section className="card stack"><h2>بررسی پیشنهادهای مرجع</h2><p className="muted">بررسی جداگانهٔ منابع و متن علمی دسته‌بندی‌ها و اختلال‌ها؛ تأیید به معنی انتشار نیست.</p><a className="button secondary" data-testid="dashboard-review-link" href="/admin-console/reviews">صف بررسی پیشنهادها</a></section>}
    {data.audit && <section className="card"><div className="cms-section-head"><h2>آخرین عملیات ثبت‌شده</h2><a className="cms-link" href="/admin-console/audit">همهٔ رویدادها</a></div>
      {data.audit.latest.length ? <ul className="cms-event-list">{data.audit.latest.map(event => <li key={event.id}><a href={`/admin-console/audit/${event.id}`}><bdi>{event.action}</bdi><span>{event.outcome === "success" ? "انجام‌شده" : event.outcome === "denied" ? "ردشده" : "ناموفق"}</span><time dateTime={event.created_at}>{cmsDate(event.created_at)}</time></a></li>)}</ul> : <CmsState empty="هنوز رویدادی در این محیط ثبت نشده است." />}
    </section>}
    <section className="cms-unavailable"><h2>بخش‌های نیازمند پذیرش نهایی</h2><p>انتشار چنددامنه، تنظیمات نسخه‌دار با مصرف‌کنندگان کامل، بازیابی Backup/Restore و آمار عمومی هنوز تأیید نهایی ندارند. مدیریت Job و حقوق محتوا مسیرهای محدود خود را دارند، اما به‌تنهایی مجوز انتشار نیستند. آمار استفاده از جست‌وجوی عمومی از این گزارش محاسبه نمی‌شود.</p></section>
  </div>;
}
