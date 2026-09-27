"use client";

import Link from "next/link";
import { ArrowUpLeft, Bookmark, BookOpen, CalendarDays, FileText, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import StudyHeatmap from "@/components/StudyHeatmap";
import StudyRecommendationsV2 from "@/components/StudyRecommendationsV2";
import { api } from "@/lib/api";
import { clearTokens, hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";

type Topic = { slug: string; name_fa?: string; name_en?: string; progress_percent: number };
type Attempt = { id: number; slug: string; title: string; score: number; max_score?: number };
type Dashboard = {
  streak: number; study_days: number; review_due: number; review_new: number;
  saved_topics: number; notes_count: number; topics_studied: number;
  heatmap: { date: string; count: number }[];
  continue_learning: Topic[]; continue_concepts: Topic[];
  recent_quizzes: Attempt[]; recent_cases: Attempt[];
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    const controller = new AbortController();
    api<Dashboard>("/dashboard/", { signal: controller.signal }, true).then(setData).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setError(reason instanceof Error ? reason.message : "دریافت داشبورد انجام نشد.");
      if (!hasToken()) location.href = "/login";
    });
    return () => controller.abort();
  }, []);
  if (error) return <main className="shell page"><div className="card error-state"><h1>داشبورد بارگذاری نشد</h1><p>{error}</p><div className="actions"><button className="button primary" onClick={() => location.reload()}>تلاش دوباره</button><button className="button" onClick={() => { clearTokens(); location.href = "/login"; }}>ورود دوباره</button></div></div></main>;
  if (!data) return <main className="shell page dashboard-page"><div className="dashboard-skeleton" role="status">در حال آماده‌کردن داشبورد…</div></main>;
  const recent = [
    ...data.continue_learning.slice(0, 2).map(item => ({ ...item, href: `/disorders/${item.slug}`, kind: "اختلال" })),
    ...data.continue_concepts.slice(0, 2).map(item => ({ ...item, href: `/concepts/${item.slug}`, kind: "مفهوم" })),
  ].slice(0, 3);
  return <main className="shell page stack dashboard-page">
    <header className="dashboard-head"><div><span className="eyebrow">فضای من</span><h1>مسیر یادگیری تو</h1><p>فعالیت ثبت‌شده را مرور کن و قدم بعدی را انتخاب کن.</p></div><Link href="/study" className="button primary">مرکز مطالعه <ArrowUpLeft size={16} aria-hidden="true" /></Link></header>
    <section className="dashboard-priority" aria-label="اقدام‌های مهم">
      <div className="dashboard-next">
        <span className="eyebrow">ادامهٔ مطالعه</span>
        {recent.length ? <><h2>{recent[0].name_fa || recent[0].name_en}</h2><p>{recent[0].kind}ی که اخیراً مطالعه کرده‌ای.</p><Link className="button primary" href={recent[0].href}>ادامه دادن <ArrowUpLeft size={16} /></Link></> : <><h2>از یک موضوع شروع کن</h2><p>هنوز موضوعی در پیشرفت مطالعه‌ات ثبت نشده است.</p><Link className="button primary" href="/disorders">کاوش اختلالات</Link></>}
      </div>
      <Link href="/flashcards" className="dashboard-review"><RotateCcw size={20} aria-hidden="true" /><span>صف مرور</span><strong>{faNumber(data.review_due)}</strong><small>فلش‌کارت موعدرسیده</small><span className="dashboard-action">باز کردن صف <ArrowUpLeft size={15} aria-hidden="true" /></span></Link>
    </section>
    <div className="dashboard-summary" aria-label="خلاصهٔ فعالیت">
      <div><CalendarDays size={18} aria-hidden="true" /><strong>{faNumber(data.study_days)}</strong><span>روز دارای فعالیت</span></div>
      <div><BookOpen size={18} aria-hidden="true" /><strong>{faNumber(data.topics_studied)}</strong><span>موضوع مطالعه‌شده</span></div>
      <div><Bookmark size={18} aria-hidden="true" /><strong>{faNumber(data.saved_topics)}</strong><span>ذخیره‌شده</span></div>
      <div><FileText size={18} aria-hidden="true" /><strong>{faNumber(data.notes_count)}</strong><span>یادداشت</span></div>
    </div>
    <div className="dashboard-content-grid">
      <section className="card dashboard-activity"><div className="dashboard-section-head"><div><span className="eyebrow">۴۲ روز اخیر</span><h2>فعالیت مطالعه</h2></div><span>{faNumber(data.streak)} روز زنجیرهٔ فعلی</span></div><StudyHeatmap days={data.heatmap || []} /><p className="muted small">هر خانه، تعداد فعالیت‌های ثبت‌شده در همان روز را نشان می‌دهد.</p></section>
      <section className="card"><div className="dashboard-section-head"><div><span className="eyebrow">سنجش و تمرین</span><h2>آخرین فعالیت‌ها</h2></div><Link href="/case-analytics" className="text-link">تحلیل کیس‌ها</Link></div>
        <div className="dashboard-activity-list">
          {data.recent_quizzes.slice(0, 2).map(item => <Link href={`/quizzes/${item.slug}`} key={`q-${item.id}`}><span>آزمون</span><strong>{item.title}</strong><ArrowUpLeft size={16} aria-hidden="true" /></Link>)}
          {data.recent_cases.slice(0, 2).map(item => <Link href={`/cases/${item.slug}`} key={`c-${item.id}`}><span>کیس</span><strong>{item.title}</strong><ArrowUpLeft size={16} aria-hidden="true" /></Link>)}
          {!data.recent_quizzes.length && !data.recent_cases.length && <p className="muted">هنوز آزمون یا کیس تکمیل‌شده‌ای ثبت نشده است. <Link href="/cases">کیس‌ها را ببین</Link></p>}
        </div>
      </section>
    </div>
    {recent.length > 1 && <section className="dashboard-recent"><div className="dashboard-section-head"><div><span className="eyebrow">مسیرهای باز</span><h2>موضوع‌های اخیر</h2></div></div><div>{recent.slice(1).map(item => <Link href={item.href} key={item.href}><span>{item.kind}</span><strong>{item.name_fa || item.name_en}</strong><ArrowUpLeft size={16} aria-hidden="true" /></Link>)}</div></section>}
    <StudyRecommendationsV2 dueCards={data.review_due} />
    <section className="dashboard-library-links"><Link href="/saved"><Bookmark size={18} aria-hidden="true" /> ذخیره‌شده‌ها <ArrowUpLeft size={15} aria-hidden="true" /></Link><Link href="/notes"><FileText size={18} aria-hidden="true" /> یادداشت‌ها <ArrowUpLeft size={15} aria-hidden="true" /></Link></section>
  </main>;
}
