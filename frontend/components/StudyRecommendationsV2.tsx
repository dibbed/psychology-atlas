"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { StudyPlan, StudyPlanListResponse, StudyRecommendationV2, StudyRecommendationsV2Response } from "@/lib/types";

type FeedbackValue = "helpful" | "not_helpful" | "dismissed";
type StudyContext = {
  plans: StudyPlan[] | null;
  studyDays: number | null;
  quizzesCompleted: number | null;
  casesCompleted: number | null;
};

const categoryLabels: Record<string, string> = {
  overdue_block: "زمان‌بندی مطالعه",
  plan_schedule_stale: "برنامه مطالعه",
  plan_generate: "برنامه مطالعه",
  plan_capacity: "برنامه مطالعه",
  srs_review: "فلش‌کارت",
  srs_start: "فلش‌کارت",
  case_resume: "تمرین مورد",
  quiz_retry: "آزمون",
  distortion_practice: "تمرین مفهوم",
  concept_review: "مرور مفهوم",
  disorder_review: "مرور مدخل",
  graph_explore: "مطالعه اطلس",
};

function factualReason(item: StudyRecommendationV2) {
  if (item.type === "plan_capacity") return item.reasons.join(" ");
  if (item.type === "plan_schedule_stale") return "خلاصهٔ معتبر و جاری برای آخرین نسخهٔ زمان‌بندی در دسترس نیست.";
  if (["srs_review", "srs_start", "quiz_retry", "overdue_block", "plan_generate"].includes(item.type)) {
    return item.description;
  }
  return item.reasons[0] || item.description;
}

function contextHints(context: StudyContext, dueCards: number) {
  const hints: { text: string; href: string; label: string }[] = [];
  if (context.studyDays === 0) {
    hints.push({ text: "هنوز فعالیت مطالعه‌ای در حساب ثبت نشده است. می‌توانی با یک مرور یا آزمون شروع کنی.", href: "/flashcards", label: "رفتن به فلش‌کارت‌ها" });
  }
  if (context.plans) {
    const plans = context.plans;
    const active = plans.filter((plan) => plan.status === "active");
    if (plans.length === 0) {
      hints.push({ text: "هنوز برنامهٔ مطالعه‌ای نساخته‌ای. هدف و ظرفیت هفتگی‌ات را مشخص کن.", href: "/study/plans/new", label: "ساخت برنامه" });
    } else if (plans.every((plan) => plan.status === "draft")) {
      hints.push({ text: "برنامه‌هایت هنوز پیش‌نویس هستند. برای دریافت پیشنهادهای مرتبط، یکی را بازبینی و فعال کن.", href: "/study/plans", label: "دیدن پیش‌نویس‌ها" });
    } else if (active.length === 0) {
      hints.push({ text: "در حال حاضر برنامهٔ فعالی نداری. وضعیت برنامه‌هایت را در بخش برنامه‌های من بررسی کن.", href: "/study/plans", label: "برنامه‌های من" });
    } else {
      const unscheduled = active.find((plan) => plan.generation_version === 0 ||
        ("scheduled_blocks" in plan.last_generation_summary && plan.last_generation_summary.scheduled_blocks === 0));
      if (unscheduled) {
        hints.push({ text: "این برنامه هنوز بلوک زمان‌بندی‌شده‌ای ندارد. می‌توانی زمان‌بندی آن را در خود برنامه بسازی یا بازبینی کنی.", href: `/study/plans/${unscheduled.id}`, label: "بازکردن برنامه" });
      }
    }
  }
  if (dueCards === 0) {
    hints.push({ text: "فعلاً فلش‌کارت موعدرسیده‌ای نداری. صف مرور را برای کارت‌های جدید یا مرور آزاد ببین.", href: "/flashcards", label: "صف فلش‌کارت" });
  }
  if (context.quizzesCompleted === 0) {
    hints.push({ text: "هنوز آزمون تکمیل‌شده‌ای ثبت نکرده‌ای. آزمون‌های موجود را ببین.", href: "/quizzes", label: "دیدن آزمون‌ها" });
  }
  if (context.casesCompleted === 0) {
    hints.push({ text: "هنوز تمرین مورد تکمیل‌شده‌ای ثبت نکرده‌ای. موردهای موجود را ببین.", href: "/cases", label: "دیدن موردها" });
  }
  return hints;
}

export default function StudyRecommendationsV2({ dueCards, initialData, onRefresh }: { dueCards: number; initialData?: StudyRecommendationsV2Response; onRefresh?: () => Promise<StudyRecommendationsV2Response> }) {
  const [recommendations, setRecommendations] = useState<StudyRecommendationsV2Response | null>(initialData ?? null);
  const [context, setContext] = useState<StudyContext>({ plans: null, studyDays: null, quizzesCompleted: null, casesCompleted: null });
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState("");
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const retryEvent = useRef<{ key: string; value: FeedbackValue; id: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRecommendations(onRefresh ? await onRefresh() : await api<StudyRecommendationsV2Response>("/study/recommendations/?limit=8", {}, true));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "پیشنهادهای مطالعه بارگذاری نشد.");
    } finally {
      setLoading(false);
    }
  }, [onRefresh]);

  useEffect(() => {
    if (!initialData) void load();
  }, [initialData, load]);

  useEffect(() => {
    void Promise.allSettled([
      api<StudyPlanListResponse>("/study/plans/", {}, true),
      api<{ study_days: number; quizzes_completed: number; cases_completed: number }>("/dashboard/", {}, true),
    ]).then(([plans, dashboard]) => {
      setContext({
        plans: plans.status === "fulfilled" ? plans.value.plans : null,
        studyDays: dashboard.status === "fulfilled" ? dashboard.value.study_days : null,
        quizzesCompleted: dashboard.status === "fulfilled" ? dashboard.value.quizzes_completed : null,
        casesCompleted: dashboard.status === "fulfilled" ? dashboard.value.cases_completed : null,
      });
    });
  }, []);

  useEffect(() => {
    if (initialData) setRecommendations(initialData);
  }, [initialData]);

  async function sendFeedback(item: StudyRecommendationV2, value: FeedbackValue) {
    if (pendingKey) return;
    const id = retryEvent.current?.key === item.key && retryEvent.current.value === value
      ? retryEvent.current.id : crypto.randomUUID();
    retryEvent.current = { key: item.key, value, id };
    setPendingKey(item.key);
    setError("");
    try {
      const response = await api<{ feedback: StudyRecommendationV2["feedback"] }>(
        `/study/recommendations/${item.key}/feedback/`,
        { method: "POST", body: JSON.stringify({ value, client_event_id: id }) },
        true,
      );
      retryEvent.current = null;
      setRecommendations((current) => current && ({
        ...current,
        items: value === "dismissed"
          ? current.items.filter((candidate) => candidate.key !== item.key)
          : current.items.map((candidate) => candidate.key === item.key ? { ...candidate, feedback: response.feedback } : candidate),
        suppressed_count: current.suppressed_count + (value === "dismissed" ? 1 : 0),
      }));
      if (onRefresh || value === "dismissed") {
        try {
          setRecommendations(onRefresh ? await onRefresh() : await api<StudyRecommendationsV2Response>("/study/recommendations/?limit=8", {}, true));
        } catch {
          setError("بازخورد ثبت شد، اما فهرست به‌روز نشد. برای تازه‌سازی دوباره تلاش کن.");
        }
      }
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "ثبت بازخورد انجام نشد. دوباره تلاش کن.");
    } finally {
      setPendingKey(null);
    }
  }

  const hints = contextHints(context, dueCards);
  return (
    <section className="card study-recommendations" aria-labelledby="study-recommendations-title" dir="rtl">
      <div className="study-recommendations-head">
        <div>
          <div className="meta">پیشنهادهای مطالعه</div>
          <h2 id="study-recommendations-title">قدم بعدی در مطالعه</h2>
          <p className="muted small">پیشنهادها بر پایهٔ محتوای در دسترس و وضعیت فعلی مطالعه‌ات هستند و با تغییر آن‌ها تازه می‌شوند.</p>
        </div>
        <Link className="button" href="/study/plans">برنامه‌های من</Link>
      </div>
      {loading && !recommendations ? <p className="muted" role="status">در حال دریافت پیشنهادها...</p> : null}
      {error && <div className="study-plan-inline-error" role="alert">{error} <button className="study-inline-action" type="button" onClick={() => void load()}>تلاش دوباره</button></div>}
      {recommendations && recommendations.items.length > 0 && (
        <div className="recommendation-list">
          {recommendations.items.map((item) => (
            <article className="recommendation-item study-recommendation-item" key={item.key}>
              <div className="study-recommendation-copy">
                <span className="study-recommendation-category">{categoryLabels[item.type] || "پیشنهاد مطالعه"}</span>
                <h3>{item.title}</h3>
                <p><strong>چرا این رو می‌بینم؟</strong> {factualReason(item)}</p>
                <div className="study-recommendation-actions">
                  <Link className="button primary" href={item.action.href}>{item.action.label}</Link>
                  <button type="button" className="button ghost" disabled={pendingKey !== null || item.feedback.value === "helpful"} onClick={() => void sendFeedback(item, "helpful")} aria-label={`مفید بود: ${item.title}`} aria-pressed={item.feedback.value === "helpful"}>مفید بود</button>
                  <button type="button" className="button ghost" disabled={pendingKey !== null || item.feedback.value === "not_helpful"} onClick={() => void sendFeedback(item, "not_helpful")} aria-label={`مفید نبود: ${item.title}`} aria-pressed={item.feedback.value === "not_helpful"}>مفید نبود</button>
                  <button type="button" className="button ghost" disabled={pendingKey !== null} onClick={() => void sendFeedback(item, "dismissed")} aria-label={`فعلاً نمایش نده: ${item.title}`}>فعلاً نمایش نده</button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
      {recommendations && recommendations.items.length === 0 && (
        <div className="study-recommendations-empty">
          <strong>{recommendations.suppressed_count > 0 ? "پیشنهادهای فعلی را فعلاً کنار گذاشته‌ای." : "فعلاً پیشنهاد تازه‌ای در دسترس نیست."}</strong>
          <p>{recommendations.suppressed_count > 0 ? "با تغییر برنامه یا فعالیت مطالعه، پیشنهادهای تازه ممکن است ظاهر شوند. پیشنهادهای کنارگذاشته‌شده هم پس از پایان مهلتشان دوباره بررسی می‌شوند." : "می‌توانی از برنامه‌ها، مرور فلش‌کارت یا تمرین‌های موجود ادامه بدهی."}</p>
        </div>
      )}
      {recommendations && hints.length > 0 && (
        <div className="study-recommendations-next">
          <h3>راه‌های دیگر برای ادامه</h3>
          <ul>{hints.map((hint) => <li key={`${hint.href}-${hint.text}`}><span>{hint.text}</span><Link href={hint.href}>{hint.label}</Link></li>)}</ul>
        </div>
      )}
      {recommendations?.truncated_sources && <p className="muted small">فقط بخشی از منابع اخیر برای این فهرست بررسی شده‌اند.</p>}
    </section>
  );
}
