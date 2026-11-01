"use client";
import {useCms} from "@/components/cms/CmsShell";

const sections:{title:string;intro:string;items:{cap:string;label:string;href:string;scope:string}[]}[]=[
  {title:"محتوای علمی و پژوهش",intro:"اصلاح پیش‌نویس با انتشار عمومی متفاوت است.",
    items:[
      {cap:"cms_core_view",label:"محتوای مرجع",href:"/admin-console/content",scope:"طرح، منبع و بازبینی"},
      {cap:"cms_source_view",label:"ثبت و بررسی منابع",href:"/admin-console/sources",scope:"شناسهٔ منبع، چرخهٔ تأیید و سابقه"},
      {cap:"cms_research_view",label:"داده‌های پژوهشی",href:"/admin-console/research",scope:"ورودی پژوهشی، نگاشت و تصمیم"},
      {cap:"cms_review_decide_core_scientific",label:"صف داوری",href:"/admin-console/reviews",scope:"تصمیم توسط بازبین دارای اختیار"},
      {cap:"cms_rights_view",label:"حقوق و استفاده",href:"/admin-console/rights",scope:"حقوق مشروط به منبع و هدف استفاده"},
    ]},
  {title:"یادگیری و کیس‌ها",intro:"تاریخچهٔ یادگیری واقعی را با شبیه‌سازی یکی نگیرید.",
    items:[
      {cap:"cms_cases_view",label:"کیس و گراف",href:"/admin-console/content/cases",scope:"Draft، نسخه، شبیه‌سازی بی‌اثر"},
      {cap:"cms_learning_view",label:"Quiz",href:"/admin-console/content/learning-quizzes",scope:"کلید پاسخ فقط برای محتوای بدون attempt"},
      {cap:"cms_learning_view",label:"Flashcard",href:"/admin-console/content/learning-flashcards",scope:"حفظ هویت و زمان‌بندی SRS"},
      {cap:"cms_learning_view",label:"چالش و تمرین",href:"/admin-console/content/learning-practice",scope:"سؤال، گزینه، پاسخ معتبر، preview"},
      {cap:"cms_study_view",label:"وضعیت Study",href:"/admin-console/study-ops",scope:"شمارش واقعی و بدون دادهٔ فردی"},
    ]},
  {title:"امنیت و عملیات",intro:"برای اطلاعات و عملیات حساس از مجوز مستقل و تأیید دوباره استفاده کنید.",
    items:[
      {cap:"cms_user_view",label:"فهرست حساب‌ها",href:"/admin-console/accounts",scope:"شناسه و وضعیت مجاز، بدون اطلاعات شخصی"},
      {cap:"cms_audit_view",label:"تاریخچهٔ Audit",href:"/admin-console/audit",scope:"اطلاعات رویداد، بدون محتوای خصوصی"},
      {cap:"cms_search",label:"جست‌وجوی داخلی",href:"/admin-console/search",scope:"فقط شناسه‌های محتوای مجاز"},
      {cap:"cms_publication_validate_cases",label:"فهرست موانع انتشار",href:"/admin-console/publication-preflight",scope:"فقط بررسی، نه Apply"},
      {cap:"cms_owner",label:"سلامت عملیات",href:"/admin-console/operations",scope:"گزارش Job/DB/Artifact بدون Restore"},
      {cap:"cms_enter",label:"Jobهای قابل مشاهده",href:"/admin-console/jobs",scope:"Jobها طبق مجوز واقعی سرور"},
    ]},
];
export default function AdminHelp(){
  const {can}=useCms();
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">خانهٔ مدیریت</a>
    <div className="cms-title"><p className="eyebrow">P19 | Admin Guide</p>
      <h1>راهنمای کاربردی مدیریت Psychology Atlas</h1>
      <p className="muted">لینک‌ها با مجوزهای مؤثر شما نمایش داده می‌شوند. وجود صفحه به‌معنی آماده‌بودن تمام اقدام‌های آن حوزه نیست.</p>
    </div>
    {sections.map(section=><section className="card stack" key={section.title}>
      <h2>{section.title}</h2><p className="muted">{section.intro}</p>
      <ul className="stack">{section.items.filter(item=>can(item.cap)).map(item=><li key={item.href}>
        <a className="cms-link" href={item.href}>{item.label}</a>
        <span> | {item.scope}</span>
      </li>)}</ul>
      {!section.items.some(item=>can(item.cap))&&<p>دسترسی فعالی از این گروه ندارید.</p>}
    </section>)}
    <section className="card stack">
      <h2>چه کارهایی هنوز از این پنل آماده نیست؟</h2>
      <p>انتشار پویای عمومی با manifest و receipt کامل P16، export/erase حریم خصوصی P14، correctionهای Study P15، بازگردانی production و تغییر آزاد تنظیمات هنوز گیت‌های تکمیل‌نشده‌اند. گزینه‌ای را صرفاً با تغییر وضعیت پایگاه داده «منتشرشده» یا «بازبینی‌شده» نکنید.</p>
      <h3>در گزارش یک مشکل</h3>
      <p>مسیر مورد استفاده، کد خطای غیرحساس، زمان و مرحله را ثبت کنید. رمز عبور، توکن نشست، پروندهٔ خصوصی یادگیرنده یا متن اختصاصی آزمون را در گزارش عمومی قرار ندهید.</p>
    </section>
  </div>;
}
