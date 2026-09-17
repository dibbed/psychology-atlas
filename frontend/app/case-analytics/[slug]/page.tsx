"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber, faPercent } from "@/lib/fa";
import type {
  CaseAnalyticsCompletedPath,
  CaseAnalyticsDetail,
  CaseAnalyticsPathStep,
} from "@/lib/types";

function percentLabel(value: number | null) {
  return value === null ? "—" : faPercent(value);
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fa-IR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function nodeLabel(step: CaseAnalyticsPathStep) {
  if (step.event_type === "terminal_complete" || step.node_kind === "terminal") return "پایان";
  if (step.event_type === "decision" || step.node_kind === "decision") return "تصمیم";
  return "ادامه";
}

function legacyCount(data: CaseAnalyticsDetail) {
  return data.legacy.rubric_zero_attempts
    + data.legacy.unscored_dimension_decisions
    + data.legacy.completed_attempts_without_reconstructible_path;
}

function redirectToLogin(nextPath: string) {
  location.href = `/login?next=${encodeURIComponent(nextPath)}`;
}

function PathCard({ path, index }: { path: CaseAnalyticsCompletedPath; index: number }) {
  return (
    <article className="analytics-path-card">
      <div className="analytics-path-head">
        <div>
          <span className="meta">مسیر {faNumber(index + 1)} · نسخه {faNumber(path.revision_number)}</span>
          <strong>{faNumber(path.attempt_count)} بار تکمیل شده</strong>
        </div>
        <span className="muted small">آخرین استفاده: {formatDate(path.last_used_at)}</span>
      </div>
      <div className="analytics-path-flow">
        {path.steps.map((step, stepIndex) => (
          <div className="analytics-path-step" key={`${stepIndex}-${step.step_key}-${step.choice_id ?? "none"}`}>
            <span className="analytics-path-index">{faNumber(stepIndex + 1)}</span>
            <div>
              <small>{nodeLabel(step)}</small>
              <strong>{step.step_title || step.step_key}</strong>
              {step.choice_text && <span>انتخاب: {step.choice_text}</span>}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

export default function CaseAnalyticsDetailPage() {
  const routeParams = useParams<{ slug: string }>();
  const slug = routeParams.slug;
  const [data, setData] = useState<CaseAnalyticsDetail | null>(null);
  const [error, setError] = useState("");
  const [noHistory, setNoHistory] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadAnalytics = useCallback(async () => {
    if (!slug) return;
    const nextPath = `/case-analytics/${slug}`;
    if (!hasToken()) {
      redirectToLogin(nextPath);
      return;
    }

    setLoading(true);
    setError("");
    setNoHistory(false);
    try {
      setData(await api<CaseAnalyticsDetail>(`/case-analytics/cases/${slug}/`, {}, true));
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin(nextPath);
        return;
      }
      if (
        reason instanceof ApiError
        && reason.status === 404
        && reason.code === "case_history_not_found"
      ) {
        setData(null);
        setNoHistory(true);
        return;
      }
      setError(reason instanceof Error ? reason.message : "دریافت جزئیات تحلیل انجام نشد.");
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void loadAnalytics();
  }, [loadAnalytics]);

  if (error) {
    return (
      <main className="shell page">
        <section className="card error-state analytics-state-card" role="alert">
          <div className="meta">تحلیل کیس</div>
          <h1>جزئیات تحلیل بارگذاری نشد</h1>
          <p>{error}</p>
          <div className="actions">
            <button className="button primary" type="button" onClick={() => void loadAnalytics()} disabled={loading}>
              {loading ? "در حال تلاش..." : "تلاش دوباره"}
            </button>
            <Link className="button" href="/case-analytics">بازگشت به تحلیل‌ها</Link>
          </div>
        </section>
      </main>
    );
  }

  if (noHistory) {
    return (
      <main className="shell page">
        <section className="card analytics-empty-state">
          <div>
            <div className="meta">سابقه‌ای برای این کیس ثبت نشده</div>
            <h1>بعد از شروع کیس، تحلیل شخصی اینجا ساخته می‌شود.</h1>
            <p>این صفحه فقط تاریخچه متعلق به حساب خودت را نمایش می‌دهد.</p>
          </div>
          <div className="actions">
            <Link className="button primary" href={`/cases/${slug}`}>شروع کیس</Link>
            <Link className="button" href="/case-analytics">تحلیل کیس‌های من</Link>
          </div>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="shell page">
        <section className="analytics-loading" role="status" aria-live="polite" aria-busy="true">
          <span className="sr-only">در حال بارگذاری جزئیات تحلیل کیس...</span>
          <div className="analytics-loading-line wide" aria-hidden="true" />
          <div className="analytics-loading-line" aria-hidden="true" />
          <div className="analytics-loading-grid" aria-hidden="true">
            {Array.from({ length: 4 }).map((_, index) => <span key={index} />)}
          </div>
        </section>
      </main>
    );
  }

  const legacyItems = legacyCount(data);

  return (
    <main className="shell page stack case-analytics-page">
      <header className="analytics-detail-head">
        <div>
          <Link className="analytics-back-link" href="/case-analytics">← همه تحلیل‌های کیس</Link>
          <div className="meta">تحلیل شخصی کیس · {data.case.structure_mode === "branching" ? "شاخه‌ای" : "خطی"}</div>
          <h1>{data.case.current_title}</h1>
          <p className="section-copy">فقط تصمیم‌ها و مسیرهایی که واقعاً در تاریخچه این حساب ثبت شده‌اند در این صفحه دیده می‌شوند.</p>
        </div>
        <div className="actions analytics-head-actions">
          {data.case.is_runnable && (
            <Link className="button primary" href={`/cases/${data.case.slug}`}>باز کردن کیس</Link>
          )}
          <Link className="button" href="/dashboard">داشبورد</Link>
        </div>
      </header>

      <section className="analytics-overview-strip" aria-label="خلاصه این کیس">
        <div className="analytics-kpi primary">
          <span>تلاش‌ها</span>
          <strong>{faNumber(data.attempts.total)}</strong>
          <small>{faNumber(data.attempts.completed)} تکمیل‌شده</small>
        </div>
        <div className="analytics-kpi">
          <span>نرخ تکمیل</span>
          <strong>{percentLabel(data.attempts.completion_rate)}</strong>
          <small>{faNumber(data.attempts.in_progress)} تلاش باز</small>
        </div>
        <div className="analytics-kpi">
          <span>میانگین تکمیل‌شده‌ها</span>
          <strong>{percentLabel(data.attempts.average_completed_score_percent)}</strong>
          <small>{faNumber(data.attempts.scored_completed_attempts)} تلاش دارای امتیاز</small>
        </div>
        <div className="analytics-kpi">
          <span>تصمیم‌های ثبت‌شده</span>
          <strong>{faNumber(data.decision_count)}</strong>
          <small>در تمام تلاش‌های این کیس</small>
        </div>
      </section>

      <section className="analytics-detail-grid">
        <article className="analytics-panel analytics-dimensions-panel">
          <div className="analytics-panel-head">
            <div>
              <div className="meta">ابعاد آموزشی طی‌شده</div>
              <h2>عملکرد در ابعاد آموزشی ثبت‌شده</h2>
            </div>
            <span>{faNumber(data.dimensions.length)} بُعد</span>
          </div>

          {data.dimensions.length ? (
            <div className="analytics-dimension-list">
              {data.dimensions.map(dimension => (
                <div className={`analytics-dimension-row ${dimension.needs_review ? "needs-review" : ""}`} key={`${dimension.revision_number}-${dimension.key}-${dimension.label}`}>
                  <div className="analytics-dimension-head">
                    <div>
                      <strong>{dimension.label}</strong>
                      <span>نسخه {faNumber(dimension.revision_number)} · {faNumber(dimension.attempt_count)} تلاش</span>
                    </div>
                    <b>{percentLabel(dimension.percent)}</b>
                  </div>
                  <div
                    className="analytics-meter"
                    role="progressbar"
                    aria-label={dimension.label}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={dimension.percent ?? undefined}
                    aria-valuetext={percentLabel(dimension.percent)}
                  >
                    <span style={{ width: `${Math.max(0, Math.min(100, dimension.percent ?? 0))}%` }} />
                  </div>
                  <div className="analytics-dimension-meta">
                    <span>{faNumber(dimension.score)} / {faNumber(dimension.max_score)} امتیاز مسیر</span>
                    <span>{faNumber(dimension.decision_count)} تصمیم</span>
                  </div>
                  {dimension.description && <p>{dimension.description}</p>}
                </div>
              ))}
            </div>
          ) : (
            <div className="analytics-inline-empty">برای این تاریخچه بُعد آموزشی قابل تجمیعی ثبت نشده است.</div>
          )}
        </article>

        <article className="analytics-panel analytics-recent-panel">
          <div className="analytics-panel-head">
            <div>
              <div className="meta">آخرین تلاش‌ها</div>
              <h2>تاریخچه تلاش‌ها</h2>
            </div>
            <span>حداکثر {faNumber(20)}</span>
          </div>

          <div className="analytics-attempt-list">
            {data.recent_attempts.map(attempt => (
              <div className="analytics-attempt-row" key={attempt.id}>
                <div className="analytics-attempt-state">
                  <span className={`analytics-status-dot ${attempt.status === "in_progress" ? "active" : "complete"}`}>
                    {attempt.status === "completed" ? "تکمیل‌شده" : "در حال اجرا"}
                  </span>
                  <small>#{faNumber(attempt.id)}</small>
                </div>
                <div className="analytics-attempt-main">
                  <strong>نسخه {faNumber(attempt.revision_number)}</strong>
                  <span>{faNumber(attempt.decision_count)} تصمیم · {faNumber(attempt.event_count)} رویداد</span>
                </div>
                <div className="analytics-attempt-score">
                  <strong>{percentLabel(attempt.score_percent)}</strong>
                  <span>{faNumber(attempt.score)} / {faNumber(attempt.max_score)}</span>
                </div>
                <time>{formatDate(attempt.completed_at || attempt.updated_at)}</time>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="analytics-panel" aria-labelledby="branch-analytics-title">
        <div className="analytics-panel-head">
          <div>
            <div className="meta">تصمیم‌های واقعاً طی‌شده</div>
            <h2 id="branch-analytics-title">الگوی انتخاب در نقاط شاخه‌ای</h2>
          </div>
          <span>{faNumber(data.branches.length)} نقطه تصمیم</span>
        </div>

        {data.branches.length ? (
          <div className="analytics-branch-list">
            {data.branches.map(branch => (
              <article className="analytics-branch-block" key={`${branch.revision_number}-${branch.step_key}-${branch.step_title}`}>
                <div className="analytics-branch-title">
                  <div>
                    <strong>{branch.step_title || branch.step_key}</strong>
                    <span>نسخه {faNumber(branch.revision_number)} · {faNumber(branch.decision_count)} تصمیم ثبت‌شده</span>
                  </div>
                  <code>{branch.step_key}</code>
                </div>
                <div className="analytics-choice-list">
                  {branch.choices.map(choice => (
                    <div className="analytics-choice-row" key={`${choice.choice_id ?? "legacy"}-${choice.choice_text}`}>
                      <div className="analytics-choice-copy">
                        <strong>{choice.choice_text}</strong>
                        <span>{faNumber(choice.count)} بار انتخاب · امتیاز {percentLabel(choice.score_percent)}</span>
                      </div>
                      <div
                        className="analytics-choice-bar"
                        role="progressbar"
                        aria-label={`سهم انتخاب ${choice.choice_text}`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={choice.selection_percent}
                        aria-valuetext={faPercent(choice.selection_percent)}
                      >
                        <span style={{ width: `${Math.max(0, Math.min(100, choice.selection_percent))}%` }} />
                      </div>
                      <b>{faPercent(choice.selection_percent)}</b>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="analytics-inline-empty">برای این کیس هنوز رویداد تصمیم قابل نمایش ثبت نشده است.</div>
        )}
      </section>

      <section className="analytics-panel" aria-labelledby="paths-title">
        <div className="analytics-panel-head">
          <div>
            <div className="meta">مسیرهای تکمیل‌شده</div>
            <h2 id="paths-title">راه‌هایی که واقعاً تا پایان طی شده‌اند</h2>
          </div>
          <span>{faNumber(data.completed_paths.length)} مسیر</span>
        </div>
        {data.completed_paths.length ? (
          <div className="analytics-path-list">
            {data.completed_paths.map((path, index) => <PathCard path={path} index={index} key={`${path.revision_number}-${index}`} />)}
          </div>
        ) : (
          <div className="analytics-inline-empty">هنوز مسیر تکمیل‌شده و قابل بازسازی برای این کیس وجود ندارد.</div>
        )}
      </section>

      {legacyItems > 0 && (
        <aside className="analytics-legacy-note">
          <div>
            <strong>بخشی از تاریخچه قدیمی‌تر است</strong>
            <p>داده قدیمی حذف نشده و به شکل صریح نگه داشته شده است؛ جایی که rubric یا تاریخچه رویداد کافی وجود ندارد، رابط کاربری چیزی را حدس نمی‌زند.</p>
          </div>
          <div className="analytics-legacy-counts">
            <span>rubric v0: <strong>{faNumber(data.legacy.rubric_zero_attempts)}</strong></span>
            <span>تصمیم بدون بُعد: <strong>{faNumber(data.legacy.unscored_dimension_decisions)}</strong></span>
            <span>مسیر غیرقابل بازسازی: <strong>{faNumber(data.legacy.completed_attempts_without_reconstructible_path)}</strong></span>
          </div>
        </aside>
      )}

      <aside className="analytics-disclaimer" aria-label="محدوده تفسیر تحلیل">
        <strong>این تحلیل چه چیزی نیست؟</strong>
        <p>{data.disclaimer}</p>
      </aside>
    </main>
  );
}
