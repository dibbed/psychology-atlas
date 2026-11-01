"use client";
import { CmsState, useCms } from '@/components/cms/CmsShell';
import { useDomainSchemas } from '@/components/cms/DomainFields';
export default function ContentHome() {
  const {schemas, error, retry} = useDomainSchemas();
  const {can} = useCms();
  if (error) return <CmsState error={error} retry={retry}/>;
  if (!schemas) return <CmsState loading/>;
  return <div className="stack"><div className="cms-title"><p className="eyebrow">محتوای مرجع</p><h1>مدیریت محتوای مرجع</h1><p className="muted">فرم‌ها و دسترسی‌ها از schema فعلی سرور دریافت می‌شوند؛ ذخیرهٔ پیشنهاد به معنی انتشار نیست.</p></div>
    {!schemas.length && <CmsState empty="نوع محتوای مجازی برای حساب فعلی وجود ندارد."/>}
    {schemas.map(schema => <a className="card cms-domain" key={schema.kind} href={`/admin-console/content/${schema.kind}`}><h2>{schema.label}</h2><p>فهرست، جزئیات، پیشنهاد، شواهد و تاریخچه</p><span className="cms-link">باز کردن {schema.kind === 'category' ? 'دسته‌بندی‌ها' : schema.label} ←</span></a>)}
    {schemas.some(schema => schema.domain === "assessment") && <a className="card cms-domain" href="/admin-console/content/assessments"><h2>متادیتا، شواهد و حقوق ابزار سنجش</h2><p>فرم‌ها، نسخه‌ها، مطالعه‌ها و مجوزها مستقل‌اند؛ بدون متن سؤال یا نمره‌گذاری</p></a>}
    {schemas.some(schema => schema.domain === "brain") && <a className="card cms-domain" href="/admin-console/content/brain"><h2>درخت مغز و اثر تغییر والد</h2><p>نمای فعلی درخت، اثر ویرایش و اعتبارسنجی چرخه و جهت بدون انتشار</p></a>}
    {schemas.some(schema => schema.domain === "history") && <a className="card cms-domain" href="/admin-console/content/chronology"><h2>تاریخچه و بدهی ارجاع</h2><p>مرور زمان‌بندی، حفظ سطح قطعیت تاریخ و منابع بررسی‌نشده</p></a>}
    {schemas.some(schema => schema.domain === 'therapy') && <a className="card cms-domain" href="/admin-console/content/therapy-compare"><h2>مقایسهٔ عمومی رویکردهای درمانی</h2><p>پیش‌نمایش از همان دادهٔ عمومی واقعی، بدون نمایش پیشنهادهای منتشرنشده یا رتبه‌بندی اثربخشی</p></a>}
    {schemas.some(schema => schema.domain === 'dsm') && <a className="card cms-domain" href="/admin-console/content/dsm"><h2>درخت و مقایسهٔ DSM</h2><p>نمای محدود فرادادهٔ corpus و ورودی P06</p></a>}
    {can('cms_learning_view') && <a className="card cms-domain" href="/admin-console/content/learning-practice"><h2>چالش روزانه و تمرین خطاهای شناختی</h2><p>Draft خصوصی، پاسخ‌های معتبر و پیش‌نمایش بدون ثبت فعالیت</p></a>}
    {can('cms_learning_view') && <a className="card cms-domain" href="/admin-console/content/learning-flashcards"><h2>کارت‌های یادگیری و SRS</h2><p>ساخت کارت جدید و ویرایش محافظت‌شده، بدون بازنویسی سابقهٔ مرور</p></a>}
    {can('cms_learning_view') && <a className="card cms-domain" href="/admin-console/content/learning-quizzes"><h2>مدیریت آزمون‌های آموزشی</h2><p>ساخت Draft غیرفعال، ویرایش ایمن کلید پاسخ و پیش‌نمایش بدون ثبت تلاش واقعی</p></a>}
    {can('cms_cases_preview') && <a className="card cms-domain" href="/admin-console/content/cases"><h2>بازرسی CaseRevision</h2><p>نمای خصوصی مراحل، انتخاب‌ها و انتقال‌های کیس؛ بدون تغییر تلاش‌های قبلی یا انتشار</p></a>}
  </div>;
}
