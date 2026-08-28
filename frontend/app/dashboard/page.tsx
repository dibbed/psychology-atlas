"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { clearTokens, hasToken } from "@/lib/auth";
import { faNumber, faPercent } from "@/lib/fa";

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
          <h2>داشبورد بارگذاری نشد</h2>
          <p>{error}</p>
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
      <div>
        <div className="meta">داشبورد دانشجو</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>مسیر مطالعه‌ات را از روی فعالیت واقعی ببین.</h1>
        <p className="section-copy">پیشرفت بر اساس مشاهده موضوع، آزمون و کیس ثبت می‌شود؛ این درصد معیار تشخیصی یا نمره دانشگاهی نیست.</p>
      </div>

      <div className="stats stats-6">
        <div className="stat"><strong>{faNumber(data.topics_studied)}</strong><span>موضوع مطالعه‌شده</span></div>
        <div className="stat"><strong>{faPercent(data.quiz_accuracy)}</strong><span>میانگین آزمون</span></div>
        <div className="stat"><strong>{faPercent(data.case_accuracy)}</strong><span>میانگین کیس</span></div>
        <div className="stat"><strong>{faNumber(data.saved_topics)}</strong><span>ذخیره‌شده</span></div>
        <div className="stat"><strong>{faNumber(data.notes_count)}</strong><span>یادداشت</span></div>
        <div className="stat"><strong>{faNumber(data.study_days)}</strong><span>روز فعالیت ثبت‌شده</span></div>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="meta">ادامه یادگیری</div>
          <div className="stack" style={{ marginTop: 14, gap: 14 }}>
            {data.continue_learning.length ? data.continue_learning.map((x: any) => (
              <Link className="progress-item" href={`/disorders/${x.slug}`} key={x.slug}>
                <div className="progress-item-head"><strong>{x.name_fa || x.name_en}</strong><span>{faPercent(x.progress_percent)}</span></div>
                <div className="progress-bar"><span style={{ width: `${Math.min(100, x.progress_percent)}%` }} /></div>
              </Link>
            )) : <p>هنوز فعالیت مطالعاتی ثبت نشده است.</p>}
          </div>
        </section>

        <section className="card">
          <div className="meta">موضوعات نیازمند مرور</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.weak_topics.length ? data.weak_topics.map((x: any) => (
              <Link href={`/disorders/${x.slug}`} className="resource-link" key={x.slug}>
                <strong>{x.name_fa || x.name_en}</strong><span>{faPercent(x.progress_percent)} پیشرفت</span>
              </Link>
            )) : <p>فعلاً موضوعی با پیشرفت پایین در فعالیت‌های ثبت‌شده نداری.</p>}
          </div>
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="meta">آخرین آزمون‌ها</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.recent_quizzes.length ? data.recent_quizzes.map((x: any) => (
              <Link href={`/quizzes/${x.slug}`} className="resource-link" key={x.id}>
                <strong>{x.title}</strong><span>{faPercent(x.score)}</span>
              </Link>
            )) : <p>هنوز آزمونی تکمیل نکرده‌ای.</p>}
          </div>
        </section>

        <section className="card">
          <div className="meta">آخرین کیس‌ها</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.recent_cases.length ? data.recent_cases.map((x: any) => (
              <Link href={`/cases/${x.slug}`} className="resource-link" key={x.id}>
                <strong>{x.title}</strong><span>{faNumber(x.score)} / {faNumber(x.max_score)}</span>
              </Link>
            )) : <p>هنوز کیسی تکمیل نکرده‌ای.</p>}
          </div>
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="meta">آخرین یادداشت‌ها</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.recent_notes.length ? data.recent_notes.map((x: any) => (
              <Link href={`/disorders/${x.disorder.slug}`} key={x.id}>
                <strong>{x.disorder.name_fa || x.disorder.name_en}</strong>
                <p className="muted small note-preview">{x.body}</p>
              </Link>
            )) : <p>هنوز یادداشتی ثبت نکرده‌ای.</p>}
          </div>
        </section>

        <section className="card">
          <div className="meta">آخرین ذخیره‌ها</div>
          <div className="stack" style={{ marginTop: 14, gap: 12 }}>
            {data.recent_saved.length ? data.recent_saved.map((x: any) => (
              <Link href={`/disorders/${x.disorder.slug}`} className="resource-link" key={x.id}>
                <strong>{x.disorder.name_fa || x.disorder.name_en}</strong>
                <span>{x.disorder.category}</span>
              </Link>
            )) : <p>هنوز موضوعی ذخیره نکرده‌ای.</p>}
          </div>
        </section>
      </div>
    </main>
  );
}
