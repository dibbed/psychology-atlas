"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import DailyChallengeCard from "./DailyChallengeCard";
import DSMStudyPanel from "./DSMStudyPanel";
import StudyHeatmap from "./StudyHeatmap";
import StudyRecommendationsV2 from "./StudyRecommendationsV2";

type Overview = {
  streak: number;
  heatmap: { date: string; count: number }[];
  review: { due: number; new: number; reviewed: number };
  concepts: { studied: number; mastered: number };
  daily_challenge_completed: boolean;
  distortion_practice: { attempts: number; correct: number; accuracy: number };
};

export default function StudyCenter() {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const signedIn = hasToken();
    setAuthenticated(signedIn);
    if (!signedIn) {
      setLoading(false);
      return;
    }
    api<Overview>("/study/overview/", {}, true)
      .then(setData)
      .catch((e: any) => setError(e.message || "مرکز مطالعه بارگذاری نشد."))
      .finally(() => setLoading(false));
  }, []);

  if (authenticated === null || loading) return <div className="card"><p className="muted">در حال آماده‌کردن مرکز مطالعه...</p></div>;
  if (!authenticated) {
    return (
      <div className="stack">
        <DailyChallengeCard />
        <DSMStudyPanel />
        <div className="card"><h3>برای ساخت برنامه مرور شخصی وارد شو</h3><p>Streak، Heatmap، Review Queue و پیشنهادها به فعالیت حساب کاربری وابسته‌اند.</p><Link href="/login" className="button primary">ورود به حساب</Link></div>
      </div>
    );
  }
  if (error || !data) return <div className="card error-state"><p>{error || "اطلاعات مطالعه آماده نیست."}</p></div>;

  return (
    <div className="stack">
      <div className="study-stats">
        <div className="study-stat"><span>🔥</span><strong>{faNumber(data.streak)}</strong><small>روز Streak</small></div>
        <div className="study-stat"><span>🃏</span><strong>{faNumber(data.review.due)}</strong><small>مرور موعدرسیده</small></div>
        <div className="study-stat"><span>🧠</span><strong>{faNumber(data.concepts.studied)}</strong><small>مفهوم مطالعه‌شده</small></div>
        <div className="study-stat"><span>✓</span><strong>{faNumber(data.concepts.mastered)}</strong><small>مفهوم تسلط‌یافته</small></div>
      </div>

      <section className="card study-planning-entry">
        <div>
          <div className="meta">برنامه‌ریزی مطالعه</div>
          <h2>هدف و ظرفیت مطالعه را مشخص کن</h2>
          <p className="muted">برای هدف مطالعه‌ات موضوع‌ها و ظرفیت هفتگی را مشخص کن، سپس زمان‌بندی بلوک‌های مطالعه را در همان برنامه بساز و بازبینی کن.</p>
        </div>
        <div className="actions">
          <Link className="button primary" href="/study/plans">برنامه‌های من</Link>
          <Link className="button" href="/study/plans/new">برنامه جدید</Link>
        </div>
      </section>

      <div className="grid-2">
        <section className="card">
          <div className="meta">۴۲ روز اخیر</div>
          <h2>Study Heatmap</h2>
          <p className="muted small">شدت هر خانه تعداد فعالیت‌های ثبت‌شده در آن روز را نشان می‌دهد.</p>
          <StudyHeatmap days={data.heatmap} />
        </section>
        <section className="card review-queue-card">
          <div className="meta">صف مرور</div>
          <h2>{faNumber(data.review.due)} کارت موعدرسیده</h2>
          <p>{faNumber(data.review.new)} کارت هنوز برای اولین بار دیده نشده و {faNumber(data.review.reviewed)} کارت حداقل یک مرور ثبت‌شده دارد.</p>
          <Link className="button primary" href="/flashcards">شروع مرور هوشمند</Link>
        </section>
      </div>

      <DailyChallengeCard />

      <section className="card distortion-study-card">
        <div>
          <div className="meta">Cognitive Distortion Practice</div>
          <h2>تمرین تشخیص الگوهای شناختی</h2>
          <p className="muted">تا الان {faNumber(data.distortion_practice.attempts)} پاسخ ثبت کرده‌ای و دقت این بخش {faNumber(data.distortion_practice.accuracy)}٪ است. نتیجه تمرین‌ها در StudyActivity و Concept Progress ثبت می‌شود.</p>
        </div>
        <div className="actions">
          <Link className="button primary" href="/cognitive-distortions#practice">ادامه تمرین</Link>
          <Link className="button" href="/cognitive-distortions">مرور تحریف‌ها</Link>
        </div>
      </section>

      <DSMStudyPanel />

      <StudyRecommendationsV2 dueCards={data.review.due} />
    </div>
  );
}
