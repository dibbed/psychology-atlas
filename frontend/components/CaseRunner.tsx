"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type { CaseAttemptEvent, CaseAttemptState, ClinicalCase } from "@/lib/types";

function eventLabel(event: CaseAttemptEvent) {
  if (event.event_type === "decision") return "تصمیم";
  if (event.event_type === "advance") return "ادامه مسیر";
  return "پایان مسیر";
}

function nodeLabel(kind: "decision" | "information" | "terminal") {
  if (kind === "decision") return "مرحله تصمیم";
  if (kind === "information") return "مرحله اطلاعاتی";
  return "مرحله پایانی";
}

export default function CaseRunner({ item }: { item: ClinicalCase }) {
  const [attempt, setAttempt] = useState<CaseAttemptState | null>(null);
  const [selectedChoice, setSelectedChoice] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [authRequired, setAuthRequired] = useState(false);
  const [resumeNotice, setResumeNotice] = useState(false);
  const stageHeadingRef = useRef<HTMLHeadingElement>(null);

  function requireAuthentication(reason: unknown) {
    if (!(reason instanceof ApiError) || reason.status !== 401) return false;
    setAttempt(null);
    setSelectedChoice(null);
    setError("");
    setAuthRequired(true);
    setResumeNotice(false);
    return true;
  }

  async function startOrResume() {
    if (!hasToken()) {
      setAttempt(null);
      setAuthRequired(true);
      setLoading(false);
      return;
    }
    setAuthRequired(false);
    setLoading(true);
    setError("");
    try {
      const data = await api<CaseAttemptState>(`/cases/${item.slug}/attempts/`, {
        method: "POST",
        body: JSON.stringify({})
      }, true);
      setAttempt(data);
      setResumeNotice(Boolean(data.resumed));
      setSelectedChoice(null);
    } catch (e) {
      if (!requireAuthentication(e)) {
        setError(e instanceof Error ? e.message : "شروع یا ادامه کیس انجام نشد.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function refreshAttempt(attemptId: number) {
    const fresh = await api<CaseAttemptState>(`/case-attempts/${attemptId}/`, {}, true);
    setAttempt(fresh);
    setSelectedChoice(null);
    return fresh;
  }

  useEffect(() => {
    void startOrResume();
    // item.slug is the stable identity for this runner; startOrResume intentionally runs once per case.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.slug]);

  useEffect(() => {
    if (!attempt?.current_step) return;
    setSelectedChoice(null);
    requestAnimationFrame(() => stageHeadingRef.current?.focus());
  }, [attempt?.current_step?.id, attempt?.state_version]);

  async function advance() {
    if (!attempt?.current_step || busy) return;
    const step = attempt.current_step;
    if (step.node_kind === "decision" && selectedChoice === null) return;

    setBusy(true);
    setError("");
    try {
      const next = await api<CaseAttemptState>(`/case-attempts/${attempt.id}/decisions/`, {
        method: "POST",
        body: JSON.stringify({
          step_id: step.id,
          choice_id: step.node_kind === "decision" ? selectedChoice : null,
          state_version: attempt.state_version
        })
      }, true);
      setAttempt(next);
      setSelectedChoice(null);
      setResumeNotice(false);
    } catch (e) {
      if (requireAuthentication(e)) return;
      const message = e instanceof Error ? e.message : "ثبت مرحله کیس انجام نشد.";
      setError(message);
      if (e instanceof ApiError && e.status === 400) {
        try {
          await refreshAttempt(attempt.id);
        } catch (refreshError) {
          requireAuthentication(refreshError);
        }
      }
    } finally {
      setBusy(false);
    }
  }

  async function restart() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<CaseAttemptState>(`/cases/${item.slug}/attempts/`, {
        method: "POST",
        body: JSON.stringify({})
      }, true);
      setAttempt(next);
      setSelectedChoice(null);
      setResumeNotice(Boolean(next.resumed));
    } catch (e) {
      if (!requireAuthentication(e)) {
        setError(e instanceof Error ? e.message : "شروع دوباره کیس انجام نشد.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="card case-state-card" role="status" aria-live="polite">
        <div className="meta">کیس بالینی</div>
        <h2>در حال آماده‌سازی مسیر آموزشی...</h2>
        <p className="muted">اگر قبلاً این کیس را نیمه‌کاره گذاشته باشی، مسیر ثبت‌شده از سرور بازیابی می‌شود.</p>
      </div>
    );
  }

  if (authRequired) {
    return (
      <div className="card case-state-card">
        <div className="meta">ذخیره مسیر و ادامه بعدی</div>
        <h2>برای شروع کیس وارد حساب شو</h2>
        <p className="muted">مسیر تصمیم‌ها، مرحله جاری و امکان ادامه بعد از بستن صفحه به حساب کاربری متصل است.</p>
        <div className="actions" style={{ marginTop: 18 }}>
          <button className="button primary" type="button" onClick={() => { location.href = `/login?next=${encodeURIComponent(`/cases/${item.slug}`)}`; }}>
            ورود و شروع کیس
          </button>
        </div>
      </div>
    );
  }

  if (!attempt) {
    return (
      <div className="card case-state-card" role="alert">
        <h2>بارگذاری کیس انجام نشد</h2>
        {error && <p className="error">{error}</p>}
        <button className="button primary" type="button" onClick={() => void startOrResume()}>
          تلاش دوباره
        </button>
      </div>
    );
  }

  const percent = attempt.max_score ? Math.round(attempt.score * 100 / attempt.max_score) : 0;
  const completed = attempt.status === "completed";
  const step = attempt.current_step;
  const currentQuestion = step?.node_kind === "decision" ? step.questions[0] : undefined;

  return (
    <div className="case-runner">
      <section className="case-attempt-bar" aria-label="وضعیت کیس">
        <div>
          <span className="meta">
            نسخه کیس {faNumber(attempt.case.revision_number)}
            {attempt.case.rubric_version > 0 ? ` · rubric ${faNumber(attempt.case.rubric_version)}` : ""}
          </span>
          <strong>{completed ? "مسیر تکمیل‌شده" : `گام جاری ${faNumber(attempt.history.length + 1)}`}</strong>
        </div>
        <div className="case-attempt-stats">
          <span>تصمیم‌های ثبت‌شده <strong>{faNumber(attempt.history.filter(event => event.event_type === "decision").length)}</strong></span>
          {attempt.dimension_feedback.available && (
            <span>ابعاد ثبت‌شده <strong>{faNumber(attempt.dimension_feedback.dimensions.length)}</strong></span>
          )}
          <span>امتیاز مسیر <strong>{faNumber(attempt.score)} / {faNumber(attempt.max_score)}</strong></span>
        </div>
      </section>

      {resumeNotice && !completed && (
        <div className="case-resume-notice" role="status">
          این تلاش از آخرین مرحله ثبت‌شده ادامه پیدا کرده است. تصمیم‌های قبلی قابل تغییر نیستند.
        </div>
      )}

      {item.revision_number !== null && attempt.case.revision_number !== item.revision_number && (
        <div className="case-resume-notice" role="status">
          <strong>این تلاش روی نسخه {faNumber(attempt.case.revision_number)} کیس ادامه پیدا می‌کند.</strong>
          <span> محتوای مسیر و هدف آموزشی از همان نسخه ثبت‌شده حفظ شده است.</span>
          {attempt.case.educational_objective && <p className="muted small">{attempt.case.educational_objective}</p>}
        </div>
      )}

      {attempt.history.length > 0 && (
        <section className="case-history" aria-labelledby="case-history-title">
          <div className="section-heading-row">
            <div>
              <div className="meta">مسیر ثبت‌شده</div>
              <h2 id="case-history-title">تاریخچه تصمیم‌ها و مراحل طی‌شده</h2>
            </div>
            <span className="muted small">فقط مسیر واقعی این تلاش نمایش داده می‌شود.</span>
          </div>

          <div className="case-history-list">
            {attempt.history.map((event, index) => (
              <article className="card case-history-item" key={event.id}>
                <div className="case-history-head">
                  <div>
                    <span className="case-history-index">{faNumber(index + 1)}</span>
                    <strong>{event.snapshot.step_title || `مرحله ${faNumber(index + 1)}`}</strong>
                  </div>
                  <span className="meta">{eventLabel(event)}</span>
                </div>
                {event.snapshot.question_prompt && <p className="case-history-question">{event.snapshot.question_prompt}</p>}
                {event.snapshot.scoring_dimension && (
                  <div className="case-dimension-tag">
                    بُعد آموزشی: <strong>{event.snapshot.scoring_dimension.label}</strong>
                  </div>
                )}
                {event.snapshot.choice_text && (
                  <div className="case-history-choice">انتخاب ثبت‌شده: <strong>{event.snapshot.choice_text}</strong></div>
                )}
                {event.snapshot.choice_feedback && <p className="case-history-feedback">{event.snapshot.choice_feedback}</p>}
                {event.snapshot.question_explanation && <p className="muted small">{event.snapshot.question_explanation}</p>}
                {event.event_type === "decision" && (
                  <div className="case-history-score">
                    امتیاز این تصمیم: {faNumber(event.awarded_score)} از {faNumber(event.max_score)}
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      {completed ? (
        <section className="stack" aria-live="polite">
          <div className="case-result card">
            <div>
              <div className="meta">این مسیر آموزشی تکمیل شد</div>
              <h2 style={{ fontSize: 34 }}>{faNumber(attempt.score)} از {faNumber(attempt.max_score)}</h2>
              <p>
                امتیاز این تلاش {faNumber(percent)}٪ است. این امتیاز فقط عملکرد در همین سناریوی آموزشی را خلاصه می‌کند و معیار صلاحیت بالینی نیست.
              </p>
            </div>
            <div className="score-ring" aria-label={`امتیاز ${percent} درصد`}>{faNumber(percent)}٪</div>
          </div>
          {attempt.dimension_feedback.available && (
            <section className="card case-dimension-summary" aria-labelledby="case-dimension-summary-title">
              <div className="section-heading-row">
                <div>
                  <div className="meta">rubric چندبعدی همین مسیر</div>
                  <h2 id="case-dimension-summary-title">خلاصه ابعاد آموزشی</h2>
                </div>
                <span className="muted small">فقط تصمیم‌های واقعاً طی‌شده محاسبه شده‌اند.</span>
              </div>
              <p className="muted">{attempt.dimension_feedback.message}</p>
              <div className="case-dimension-grid">
                {attempt.dimension_feedback.dimensions.map(dimension => (
                  <article className={`case-dimension-card ${dimension.needs_review ? "needs-review" : ""}`} key={dimension.key}>
                    <div className="case-dimension-card-head">
                      <strong>{dimension.label}</strong>
                      <span>{faNumber(dimension.score)} / {faNumber(dimension.max_score)}</span>
                    </div>
                    {dimension.percent !== null && (
                      <div className="case-dimension-percent" aria-label={`${dimension.label}: ${dimension.percent} درصد از امتیاز مسیر`}>
                        {faNumber(dimension.percent)}٪
                      </div>
                    )}
                    {dimension.description && <p className="muted small">{dimension.description}</p>}
                    <p className="case-dimension-feedback">{dimension.feedback}</p>
                    <span className="muted small">تصمیم‌های این بُعد: {faNumber(dimension.decision_count)}</span>
                  </article>
                ))}
              </div>
              <p className="case-dimension-disclaimer">{attempt.dimension_feedback.disclaimer}</p>
            </section>
          )}
          {error && <p className="error" role="alert">{error}</p>}
          <div className="actions">
            <button className="button primary" type="button" onClick={() => void restart()} disabled={busy}>
              {busy ? "در حال شروع..." : "حل دوباره کیس"}
            </button>
            <Link className="button" href={`/case-analytics/${item.slug}`}>دیدن تحلیل این کیس</Link>
          </div>
        </section>
      ) : step ? (
        <section className="card case-stage case-stage-stateful" aria-labelledby="case-current-step-title">
          <div className="case-stage-heading">
            <div>
              <div className="meta">{nodeLabel(step.node_kind)} · state {faNumber(attempt.state_version)}</div>
              <h2 id="case-current-step-title" ref={stageHeadingRef} tabIndex={-1}>{step.title}</h2>
            </div>
            <span className="case-node-key">{step.stable_key}</span>
          </div>
          <p className="case-narrative">{step.narrative}</p>

          {step.node_kind === "decision" && currentQuestion && (
            <div className="question case-current-question">
              <h3>{currentQuestion.prompt}</h3>
              <div className="case-choice-list" role="group" aria-label={currentQuestion.prompt}>
                {currentQuestion.choices.map(choice => (
                  <button
                    type="button"
                    className={`choice ${selectedChoice === choice.id ? "selected" : ""}`}
                    key={choice.id}
                    aria-pressed={selectedChoice === choice.id}
                    onClick={() => setSelectedChoice(choice.id)}
                    disabled={busy}
                  >
                    {choice.text}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step.node_kind === "information" && (
            <div className="case-node-hint">
              این مرحله انتخابی ندارد. با ادامه، backend transition معتبر بعدی را تعیین می‌کند.
            </div>
          )}

          {step.node_kind === "terminal" && (
            <div className="case-node-hint">
              به انتهای مسیر فعلی رسیده‌ای. پایان را ثبت کن تا خلاصه همین تلاش نمایش داده شود.
            </div>
          )}

          {error && <p className="error" role="alert">{error}</p>}
          <div className="actions" style={{ marginTop: 18 }}>
            <button
              className="button primary"
              type="button"
              disabled={busy || (step.node_kind === "decision" && selectedChoice === null)}
              onClick={() => void advance()}
            >
              {busy
                ? "در حال ثبت..."
                : step.node_kind === "decision"
                  ? "ثبت تصمیم و ادامه مسیر"
                  : step.node_kind === "terminal"
                    ? "ثبت پایان این مسیر"
                    : "ادامه مسیر"}
            </button>
          </div>
        </section>
      ) : (
        <div className="card" role="alert">
          <p className="error">attempt در حال اجرا مرحله جاری معتبری ندارد. صفحه را دوباره بارگذاری کن.</p>
        </div>
      )}
    </div>
  );
}
