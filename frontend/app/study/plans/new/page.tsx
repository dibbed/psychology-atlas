"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import type { StudyPlan, UserStudySettings } from "@/lib/types";

const PAGE_PATH = "/study/plans/new";

function dateInputInTimezone(timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone,
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

function redirectToLogin() {
  location.href = `/login?next=${encodeURIComponent(PAGE_PATH)}`;
}

export default function NewStudyPlanPage() {
  const [name, setName] = useState("");
  const [planKind, setPlanKind] = useState<StudyPlan["plan_kind"]>("general");
  const [startDate, setStartDate] = useState("");
  const [studyTimezone, setStudyTimezone] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) {
      redirectToLogin();
      return;
    }

    let active = true;
    void api<UserStudySettings>("/study/settings/", {}, true)
      .then((settings) => {
        if (!active) return;
        setStudyTimezone(settings.study_timezone);
        setStartDate(dateInputInTimezone(settings.study_timezone));
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 401) {
          redirectToLogin();
          return;
        }
        setError(reason instanceof Error ? reason.message : "تنظیمات زمان مطالعه دریافت نشد.");
      });
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hasToken()) {
      redirectToLogin();
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const plan = await api<StudyPlan>(
        "/study/plans/",
        {
          method: "POST",
          body: JSON.stringify({
            name,
            plan_kind: planKind,
            start_date: startDate,
            target_date: planKind === "exam" ? targetDate || null : null,
            notes,
          }),
        },
        true,
      );
      location.href = `/study/plans/${plan.id}`;
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin();
        return;
      }
      setError(reason instanceof Error ? reason.message : "ساخت برنامه انجام نشد.");
      setSubmitting(false);
    }
  }

  return (
    <main className="shell page stack study-plan-page">
      <header className="study-plan-head">
        <div>
          <Link className="study-plan-back" href="/study/plans">← برنامه‌های مطالعه</Link>
          <div className="meta">برنامه جدید</div>
          <h1 className="section-title">اول هدف را تعریف کن.</h1>
          <p className="section-copy">
            بعد از ساخت پیش‌نویس، موضوع‌ها و ظرفیت هر روز را در صفحه برنامه تنظیم می‌کنی.
          </p>
        </div>
      </header>

      <form className="card study-plan-form" onSubmit={submit}>
        <div className="study-form-grid">
          <label className="study-form-field span-2">
            <span>نام برنامه</span>
            <input
              value={name}
              maxLength={180}
              required
              onChange={(event) => setName(event.target.value)}
              placeholder="مثلاً امتحان آسیب‌شناسی یا مرور نظریه‌های شخصیت"
              autoFocus
            />
          </label>

          <label className="study-form-field">
            <span>نوع برنامه</span>
            <select value={planKind} onChange={(event) => setPlanKind(event.target.value as StudyPlan["plan_kind"])}>
              <option value="general">مطالعه عمومی</option>
              <option value="exam">آمادگی برای امتحان</option>
            </select>
          </label>

          <label className="study-form-field">
            <span>تاریخ شروع</span>
            {studyTimezone && <small className="muted">بر اساس {studyTimezone}</small>}
            <input
              type="date"
              value={startDate}
              required
              onChange={(event) => setStartDate(event.target.value)}
            />
          </label>

          {planKind === "exam" && (
            <label className="study-form-field">
              <span>تاریخ امتحان / هدف</span>
              <input
                type="date"
                value={targetDate}
                min={startDate}
                required
                onChange={(event) => setTargetDate(event.target.value)}
              />
            </label>
          )}

          <label className="study-form-field span-2">
            <span>یادداشت اختیاری</span>
            <textarea
              value={notes}
              maxLength={12000}
              rows={5}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="مثلاً فصل‌های امتحان، محدودیت زمانی یا توضیحی که بعداً لازم داری"
            />
          </label>
        </div>

        {error && <div className="study-plan-inline-error" role="alert">{error}</div>}

        <div className="study-plan-form-foot">
          <p>
            ساخت برنامه فقط یک پیش‌نویس ایجاد می‌کند. هیچ فعالیت مطالعه‌ای با این مرحله به‌طور خودکار تکمیل یا زمان‌بندی نمی‌شود.
          </p>
          <div className="actions">
            <Link className="button" href="/study/plans">انصراف</Link>
            <button className="button primary" type="submit" disabled={submitting || !startDate}>
              {submitting ? "در حال ساخت..." : "ساخت پیش‌نویس"}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}
