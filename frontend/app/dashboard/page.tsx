"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { clearTokens, hasToken } from "@/lib/auth";
import { faNumber, faPercent } from "@/lib/fa";
import StudyHeatmap from "@/components/StudyHeatmap";

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    api("/dashboard/", {}, true)
      .then(setData)
      .catch((e: any) => {
        setError(e.message || "دریافت داشبورد انجام نشد.");
        if (!hasToken()) setTimeout(() => { location.href = "/login"; }, 500);
      });
  }, []);

  if (error) {
    return (
      <main className="shell page">
        <div className="card error-state">
          <h2>داشبورد بارگذاری نشد</h2><p>{error}</p>
          <div className="actions" style={{ marginTop: 16 }}>
            <button className="button primary" onClick={() => location.reload()}>تلاش دوباره</button>
            <button className="button" onClick={() => { clearTokens(); location.href = "/login"; }}>ورود دوباره</button>
          </div>
        </div>
      </main>
    );
  }

  if (!data) return <main className="shell page"><p className="muted">در حال بارگذاری داشبورد...</p></main>;

  return (
    <main className="shell page stack">
      <div className="dashboard-v3-head">
        <div><div className="meta">Dashboard V3</div><h1 className="section-title" style={{ fontSize: 44 }}>فعالیت را به تصمیم بعدی مطالعه وصل کن.</h1><p className="section-copy">Progress، Streak، Heatmap، SRS و Recommendation همگی از داده ثبت‌شده حساب تو ساخته می‌شوند.</p></div>
        <div className="actions analytics-head-actions">
          <Link className="button primary" href="/study">باز کردن مرکز مطالعه</Link>
          <Link className="button" href="/case-analytics">تحلیل کیس‌های من</Link>
        </div>
      </div>

      <div className="stats stats-8">
        <div className="stat"><strong>{faNumber(data.streak)}</strong><span>روز Streak</span></div>
        <div className="stat"><strong>{faNumber(data.topics_studied)}</strong><span>موضوع مطالعه‌شده</span></div>
        <div className="stat"><strong>{faNumber(data.concepts_mastered)}</strong><span>مفهوم تسلط‌یافته</span></div>
        <div className="stat"><strong>{faNumber(data.review_due)}</strong><span>کارت موعدرسیده</span></div>
        <div className="stat"><strong>{faPercent(data.quiz_accuracy)}</strong><span>میانگین آزمون</span></div>
        <div className="stat"><strong>{faPercent(data.case_accuracy)}</strong><span>میانگین کیس</span></div>
        <div className="stat"><strong>{faNumber(data.saved_topics)}</strong><span>ذخیره‌شده</span></div>
        <div className="stat"><strong>{faNumber(data.notes_count)}</strong><span>یادداشت</span></div>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="meta">۴۲ روز اخیر</div><h2>Study Heatmap</h2>
          <StudyHeatmap days={data.heatmap || []} />
          <p className="muted small" style={{ marginTop: 12 }}>{faNumber(data.study_days)} روز دارای فعالیت ثبت‌شده در تاریخچه فعلی.</p>
        </section>
        <section className="card">
          <div className="meta">Review Queue</div><h2>{faNumber(data.review_due)} مرور موعدرسیده</h2>
          <p>{faNumber(data.review_new)} کارت جدید هم هنوز وارد چرخه مرور نشده است.</p>
          <Link className="button primary" href="/flashcards">شروع مرور</Link>
        </section>
      </div>

      <section className="card">
        <div className="meta">پیشنهادهای مطالعه</div>
        <div className="recommendation-list" style={{ marginTop: 12 }}>
          {data.recommendations?.length ? data.recommendations.map((item: any) => (
            <Link className="recommendation-item" href={item.href} key={`${item.type}-${item.href}`}>
              <div><strong>{item.title}</strong><p>{item.reason}</p></div><span>مرور ←</span>
            </Link>
          )) : <p>با چند فعالیت بیشتر، پیشنهادهای شخصی اینجا ظاهر می‌شوند.</p>}
        </div>
      </section>

      <div className="grid-2">
        <section className="card">
          <div className="meta">ادامه اختلالات</div>
          <div className="stack" style={{ marginTop: 14, gap: 14 }}>
            {data.continue_learning.length ? data.continue_learning.map((item: any) => (
              <Link className="progress-item" href={`/disorders/${item.slug}`} key={item.slug}>
                <div className="progress-item-head"><strong>{item.name_fa || item.name_en}</strong><span>{faPercent(item.progress_percent)}</span></div>
                <div className="progress-bar"><span style={{ width: `${Math.min(100, item.progress_percent)}%` }} /></div>
              </Link>
            )) : <p>هنوز اختلالی در Progress ثبت نشده است.</p>}
          </div>
        </section>
        <section className="card">
          <div className="meta">ادامه مفاهیم</div>
          <div className="stack" style={{ marginTop: 14, gap: 14 }}>
            {data.continue_concepts?.length ? data.continue_concepts.map((item: any) => (
              <Link className="progress-item" href={`/concepts/${item.slug}`} key={item.slug}>
                <div className="progress-item-head"><strong>{item.name_fa || item.name_en}</strong><span>{faPercent(item.progress_percent)}</span></div>
                <div className="progress-bar"><span style={{ width: `${Math.min(100, item.progress_percent)}%` }} /></div>
              </Link>
            )) : <p>هنوز مفهومی مطالعه نکرده‌ای.</p>}
          </div>
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="meta">موضوعات نیازمند مرور</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.weak_topics.length ? data.weak_topics.map((item: any) => (
              <Link href={`/disorders/${item.slug}`} className="resource-link" key={item.slug}>
                <strong>{item.name_fa || item.name_en}</strong><span>{faPercent(item.progress_percent)} پیشرفت</span>
              </Link>
            )) : <p>فعلاً موضوع Disorder با پیشرفت پایین ثبت نشده است.</p>}
          </div>
        </section>
        <section className="card">
          <div className="meta">آخرین فعالیت سنجشی</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.recent_quizzes.map((item: any) => <Link href={`/quizzes/${item.slug}`} className="resource-link" key={`q-${item.id}`}><strong>{item.title}</strong><span>{faPercent(item.score)}</span></Link>)}
            {data.recent_cases.map((item: any) => <Link href={`/cases/${item.slug}`} className="resource-link" key={`c-${item.id}`}><strong>{item.title}</strong><span>{faNumber(item.score)} / {faNumber(item.max_score)}</span></Link>)}
            {!data.recent_quizzes.length && !data.recent_cases.length && <p>هنوز Quiz یا Case تکمیل نشده است.</p>}
          </div>
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="meta">آخرین یادداشت‌ها</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.recent_notes.map((item: any) => <Link href={`/disorders/${item.disorder.slug}`} key={`dn-${item.id}`}><strong>{item.disorder.name_fa || item.disorder.name_en}</strong><p className="muted small note-preview">{item.body}</p></Link>)}
            {data.recent_concept_notes?.map((item: any) => <Link href={`/concepts/${item.slug}`} key={`cn-${item.id}`}><strong>{item.name_fa || item.name_en}</strong><p className="muted small note-preview">{item.body}</p></Link>)}
            {data.recent_therapy_notes?.map((item: any) => <Link href={`/therapies/${item.slug}`} key={`tn-${item.id}`}><strong>{item.name_fa || item.name_en}</strong><p className="muted small note-preview">{item.body}</p></Link>)}
            {!data.recent_notes.length && !data.recent_concept_notes?.length && !data.recent_therapy_notes?.length && <p>هنوز یادداشتی ثبت نکرده‌ای.</p>}
          </div>
        </section>
        <section className="card">
          <div className="meta">آخرین ذخیره‌ها</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.recent_saved.map((item: any) => <Link href={`/disorders/${item.disorder.slug}`} className="resource-link" key={`db-${item.id}`}><strong>{item.disorder.name_fa || item.disorder.name_en}</strong><span>اختلال</span></Link>)}
            {data.recent_concept_saved?.map((item: any) => <Link href={`/concepts/${item.slug}`} className="resource-link" key={`cb-${item.id}`}><strong>{item.name_fa || item.name_en}</strong><span>مفهوم</span></Link>)}
            {data.recent_therapy_saved?.map((item: any) => <Link href={`/therapies/${item.slug}`} className="resource-link" key={`tb-${item.id}`}><strong>{item.name_fa || item.name_en}</strong><span>درمان</span></Link>)}
            {!data.recent_saved.length && !data.recent_concept_saved?.length && !data.recent_therapy_saved?.length && <p>هنوز چیزی ذخیره نکرده‌ای.</p>}
          </div>
        </section>
      </div>
    </main>
  );
}
