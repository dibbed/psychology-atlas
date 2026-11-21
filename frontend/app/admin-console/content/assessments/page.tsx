"use client";
import {CmsState, useCms} from "@/components/cms/CmsShell";
import {useDomainSchemas} from "@/components/cms/DomainFields";

const sections = [
  {kind:"assessment-instrument", heading:"خانوادهٔ ابزار", description:"نام و سازه، با شناسهٔ ثابت؛ نه فرم یا پاسخ‌نامه"},
  {kind:"assessment-version", heading:"نسخه و ویرایش", description:"نسخهٔ دقیق، نوع فرم و محدودیت‌های گزارش‌شده"},
  {kind:"assessment-language-form", heading:"فرم زبان و اقتباس", description:"ترجمه و اقتباس جدا از مجوز و اعتبار علمی"},
  {kind:"assessment-validation-study", heading:"مطالعهٔ اعتبارسنجی", description:"نمونه، روش، جمعیت و منبع هر ادعا"},
  {kind:"assessment-psychometric-evidence", heading:"یافتهٔ روان‌سنجی", description:"آمار نقل‌شده، عدم‌قطعیت، محدودیت و محل استخراج"},
  {kind:"assessment-alias", heading:"نام‌های جایگزین", description:"نام خانوادگی و نسخه با منبع، بدون ادغام هویت‌ها"},
  {kind:"assessment-access", heading:"حقوق و دسترسی", description:"حقوق هر نسخه و فرم، نوع ماده و کاربرد جداگانه"},
  {kind:"assessment-relation", heading:"ادعای علمی به سازه", description:"رابطهٔ دقیق با مفهوم، علامت یا اختلال، بدون تشخیص"},
  {kind:"assessment-source", heading:"منابع ادعاها", description:"منابع جدا برای هر هویت، نسخه، فرم و رابطه"},
];

export default function AssessmentEditorHome() {
  const {can} = useCms();
  const {schemas, error, retry} = useDomainSchemas();
  if (!can("cms_assessment_view"))
    return <CmsState empty="برای مشاهدهٔ ابزارهای سنجش، دسترسی دامنهٔ Assessment لازم است."/>;
  if (error) return <CmsState error={error} retry={retry}/>;
  if (!schemas) return <CmsState loading/>;
  const available = new Set(schemas.filter(s=>s.domain==="assessment").map(s=>s.kind));
  return <main className="stack" dir="rtl">
    <a href="/admin-console/content" className="cms-link">→ محتوای مرجع</a>
    <div className="cms-title">
      <p className="eyebrow">اطلس ابزارهای سنجش</p>
      <h1>مدیریت متادیتای ابزار، منبع و مجوز</h1>
      <p className="muted">نسخه‌ها، ترجمه‌ها، مطالعات و حقوق مستقل‌اند. ثبت یا تأیید پیش‌نویس به معنی انتشار یا اجازهٔ تکثیر نیست.</p>
    </div>
    <p className="cms-notice">این بخش فقط فرادادهٔ قابل استناد را مدیریت می‌کند. متن سؤال، کلید تصحیح، نمره‌گذاری، راهنمای مالکیتی و توصیهٔ تشخیصی را وارد نکنید. وضعیت مجوز یا اعتبار نامشخص، «مجاز» یا «تأییدشده» فرض نمی‌شود.</p>
    {!available.size && <CmsState empty="ویرایشگرهای Assessment هنوز برای این حساب فعال نشده‌اند."/ >}
    <div className="stack">
      {sections.filter(section=>available.has(section.kind)).map(section=>
        <a href={`/admin-console/content/${section.kind}`} className="card cms-domain" key={section.kind}>
          <h2>{section.heading}</h2>
          <p>{section.description}</p>
          <span className="cms-link">باز کردن ویرایشگر محدود ←</span>
        </a>)}
    </div>
  </main>;
}
