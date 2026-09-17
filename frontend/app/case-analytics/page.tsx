"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber, faPercent } from "@/lib/fa";
import type { CaseAnalyticsOverview } from "@/lib/types";

const ANALYTICS_PATH = "/case-analytics";

function percentLabel(value: number | null) {
  return value === null ? "—" : faPercent(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("fa-IR", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function redirectToLogin(nextPath: string) {
  location.href = `/login?next=${encodeURIComponent(nextPath)}`;
}

export default function CaseAnalyticsPage() {
  const [data, setData] = useState<CaseAnalyticsOverview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadAnalytics = useCallback(async () => {
    if (!hasToken()) {
      redirectToLogin(ANALYTICS_PATH);
      return;
    }

    setLoading(true);
    setError("");
    try {
      setData(await api<CaseAnalyticsOverview>("/case-analytics/overview/", {}, true));
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin(ANALYTICS_PATH);
        return;
      }
      setError(reason instanceof Error ? reason.message : "دریافت تحلیل کیس‌ها انجام نشد.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAnalytics();
  }, [loadAnalytics]);

  if (error) {
    return (
      <main className="shell page">
        <section className="card error-state analytics-state-card" role="alert">
          <div className="meta">تحلیل شخصی کیس‌ها</div>
          <h1>تحلیل کیس‌ها بارگذاری نشد</h1>
          <p>{error}</p>
          <div className="actions">
            <button className="button primary" type="button" onClick={() => void loadAnalytics()} disabled={loading}>
              {loading ? "در حال تلاش..." : "تلاش دوباره"}
            </button>
            <Link className="button" href="/cases">بازگشت به کیس‌ها</Link>
          </div>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="shell page">
        <section className="analytics-loading" role="status" aria-live="polite" aria-busy="true">
          <span className="sr-only">در حال بارگذاری تحلیل شخصی کیس‌ها...</span>
          <div className="analytics-loading-line wide" aria-hidden="true" />
          <div className="analytics-loading-line" aria-hidden="true" />
          <div className="analytics-loading-grid" aria-hidden="true">
            {Array.from({ length: 4 }).map((_, index) => <span key={index} />)}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell page stack case-analytics-page">
      <header className="analytics-page-head">
        <div>
          <div className="meta">تحلیل شخصی کیس‌های آموزشی</div>
          <h1 className="section-title analytics-title">الگوی تمرین‌های کیس خودت را ببین.</h1>
          <p className="section-copy">
            این صفحه فقط از تلاش‌ها و تصمیم‌های ثبت‌شده حساب تو ساخته شده است. هیچ مقایسه‌ای با کاربران دیگر انجام نمی‌شود.
          </p>
        </div>
        <div className="actions analytics-head-actions">
          <Link className="button primary" href="/cases">تمرین یک کیس</Link>
          <Link className="button" href="/dashboard">داشبورد مطالعه</Link>
        </div>
      </header>

      <section className="analytics-overview-strip" aria-label="خلاصه فعالیت کیس‌ها">
        <div className="analytics-kpi primary">
          <span>تلاش‌ها</span>
          <strong>{faNumber(data.attempts.total)}</strong>
          <small>{faNumber(data.attempts.completed)} تکمیل‌شده</small>
        </div>
        <div className="analytics-kpi">
          <span>نرخ تکمیل</span>
          <strong>{percentLabel(data.attempts.completion_rate)}</strong>
          <small>{faNumber(data.attempts.in_progress)} تلاش در حال اجرا</small>
        </div>
        <div className="analytics-kpi">
          <span>میانگین تلاش‌های تکمیل‌شده</span>
          <strong>{percentLabel(data.attempts.average_completed_score_percent)}</strong>
          <small>{faNumber(data.attempts.scored_completed_attempts)} تلاش دارای امتیاز</small>
        </div>
        <div className="analytics-kpi">
          <span>کیس و تصمیم</span>
          <strong>{faNumber(data.cases_started)} / {faNumber(data.decision_count)}</strong>
          <small>کیس شروع‌شده / تصمیم ثبت‌شده</small>
        </div>
      </section>

      {data.cases.length === 0 ? (
        <section className="card analytics-empty-state">
          <div>
            <div className="meta">هنوز داده‌ای ثبت نشده</div>
            <h2>اولین کیس را شروع کن تا تحلیل شخصی ساخته شود.</h2>
            <p>بعد از ثبت تصمیم‌ها، همین‌جا نرخ تکمیل، مسیرها و ابعاد آموزشی طی‌شده را می‌بینی.</p>
          </div>
          <Link className="button primary" href="/cases">رفتن به کیس‌ها</Link>
        </section>
      ) : (
        <section className="analytics-case-section" aria-labelledby="analytics-cases-title">
          <div className="section-heading-row analytics-section-head">
            <div>
              <div className="meta">کیس‌های شروع‌شده</div>
              <h2 id="analytics-cases-title">نمای کلی هر کیس</h2>
            </div>
            <span className="muted small">مرتب‌شده بر اساس آخرین فعالیت</span>
          </div>

          <div className="analytics-case-list">
            {data.cases.map(item => (
              <Link className="analytics-case-row" href={`/case-analytics/${item.slug}`} key={item.case_id}>
                <div className="analytics-case-main">
                  <div className="analytics-case-heading">
                    <div>
                      <strong>{item.current_title}</strong>
                      <span>آخرین نسخه تمرین‌شده: {faNumber(item.latest_attempt_revision_number)}</span>
                    </div>
                    <span className={`analytics-status-dot ${item.in_progress_attempts > 0 ? "active" : ""}`}>
                      {item.in_progress_attempts > 0 ? "در حال اجرا" : "بدون تلاش باز"}
                    </span>
                  </div>
                  <div
                    className="analytics-case-progress"
                    role="progressbar"
                    aria-label="نرخ تکمیل"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={item.completion_rate ?? undefined}
                    aria-valuetext={percentLabel(item.completion_rate)}
                  >
                    <span style={{ width: `${Math.max(0, Math.min(100, item.completion_rate ?? 0))}%` }} />
                  </div>
                </div>

                <div className="analytics-case-metrics">
                  <div><strong>{faNumber(item.attempts)}</strong><span>تلاش</span></div>
                  <div><strong>{percentLabel(item.completion_rate)}</strong><span>تکمیل</span></div>
                  <div><strong>{percentLabel(item.average_completed_score_percent)}</strong><span>میانگین</span></div>
                  <div><strong>{faNumber(item.decision_count)}</strong><span>تصمیم</span></div>
                </div>

                <div className="analytics-case-tail">
                  <span>{formatDate(item.last_activity_at)}</span>
                  <strong>جزئیات تحلیل ←</strong>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      <aside className="analytics-disclaimer" aria-label="محدوده تفسیر تحلیل">
        <strong>محدوده تفسیر</strong>
        <p>{data.disclaimer}</p>
      </aside>
    </main>
  );
}
