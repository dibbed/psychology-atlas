"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { DistortionPracticeQueue, DistortionPracticeResult } from "@/lib/types";

const difficultyLabels: Record<string, string> = {
  basic: "پایه",
  intermediate: "میانی",
  advanced: "پیشرفته",
};

export default function DistortionPractice({ totalAvailable }: { totalAvailable: number }) {
  const [difficulty, setDifficulty] = useState("");
  const [queue, setQueue] = useState<DistortionPracticeQueue | null>(null);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<DistortionPracticeResult | null>(null);
  const [score, setScore] = useState(0);
  const [answered, setAnswered] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestIdRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setQueue(null);
    setError("");
    const qs = difficulty ? `?limit=20&difficulty=${difficulty}` : "?limit=20";
    api<DistortionPracticeQueue>(`/cognitive-distortions/practice/${qs}`, { signal: controller.signal })
      .then(data => {
        if (requestId !== requestIdRef.current) return;
        setQueue(data);
        setIndex(0);
        setSelected(null);
        setResult(null);
        setScore(0);
        setAnswered(0);
      })
      .catch((reason: any) => {
        if (requestId !== requestIdRef.current || reason?.name === "AbortError") return;
        setError(reason?.message || "تمرین‌ها دریافت نشدند.");
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setLoading(false);
      });
    return () => controller.abort();
  }, [difficulty]);

  const item = queue?.items[index];
  const completed = Boolean(queue && queue.items.length > 0 && index >= queue.items.length);
  const accuracy = answered ? Math.round((score / answered) * 100) : 0;

  const progress = useMemo(() => {
    if (!queue?.items.length) return 0;
    return Math.min(100, Math.round((answered / queue.items.length) * 100));
  }, [queue, answered]);

  async function submit() {
    if (!item || selected == null || busy || result) return;
    setBusy(true);
    setError("");
    try {
      const data = await api<DistortionPracticeResult>(
        `/cognitive-distortions/practice/${item.slug}/submit/`,
        { method: "POST", body: JSON.stringify({ choice_id: selected }) },
        true,
      );
      setResult(data);
      setAnswered(value => value + 1);
      if (data.correct) setScore(value => value + 1);
    } catch (reason: any) {
      setError(reason?.message || "ثبت پاسخ انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  function next() {
    if (!queue) return;
    setSelected(null);
    setResult(null);
    setError("");
    setIndex(value => value + 1);
  }

  function restart() {
    setIndex(0);
    setSelected(null);
    setResult(null);
    setScore(0);
    setAnswered(0);
    setError("");
  }

  return (
    <section className="distortion-practice stack" id="practice">
      <div className="distortion-practice-head">
        <div>
          <div className="meta">Recognition Practice</div>
          <h2>تحریف را از روی الگوی استدلال تشخیص بده.</h2>
          <p className="section-copy">پاسخ صحیح سمت سرور نگه داشته می‌شود و فقط بعد از submit همراه با توضیح آموزشی نمایش داده می‌شود.</p>
        </div>
        <div className="practice-filter">
          <label htmlFor="practice-difficulty">سطح تمرین</label>
          <select id="practice-difficulty" className="filter-select" value={difficulty} onChange={event => setDifficulty(event.target.value)}>
            <option value="">همه سطوح</option>
            <option value="basic">پایه</option>
            <option value="intermediate">میانی</option>
            <option value="advanced">پیشرفته</option>
          </select>
        </div>
      </div>

      <div className="practice-overview card">
        <div><strong>{totalAvailable.toLocaleString("fa-IR")}</strong><span>تمرین در بانک</span></div>
        <div><strong>{answered.toLocaleString("fa-IR")}</strong><span>پاسخ داده‌شده</span></div>
        <div><strong>{score.toLocaleString("fa-IR")}</strong><span>پاسخ درست</span></div>
        <div><strong>{accuracy.toLocaleString("fa-IR")}٪</strong><span>دقت این جلسه</span></div>
      </div>
      <div className="practice-progress" aria-label="پیشرفت جلسه"><span style={{ width: `${progress}%` }} /></div>

      {loading && <div className="card"><p className="muted">در حال دریافت تمرین‌ها...</p></div>}
      {!loading && error && !item && <div className="card error-state"><p>{error}</p></div>}
      {!loading && !error && queue && queue.items.length === 0 && (
        <div className="card empty-relation">برای این سطح تمرینی فعال و معتبر پیدا نشد.</div>
      )}
      {!loading && !completed && item && (
        <article className="card practice-card">
          <div className="practice-card-topline">
            <span className="meta">سؤال {(index + 1).toLocaleString("fa-IR")} از {queue?.items.length.toLocaleString("fa-IR")}</span>
            <span className={`difficulty-badge ${item.difficulty}`}>{difficultyLabels[item.difficulty]}</span>
          </div>
          <h3>{item.prompt}</h3>
          <div className="practice-choices" role="radiogroup" aria-label="گزینه‌های پاسخ">
            {item.choices.map(choice => {
              const chosen = selected === choice.id;
              const correct = result?.correct_choice_id === choice.id;
              const wrongChosen = Boolean(result && chosen && !result.correct);
              return (
                <button
                  className={`practice-choice ${chosen ? "selected" : ""} ${correct ? "correct" : ""} ${wrongChosen ? "wrong" : ""}`}
                  key={choice.id}
                  onClick={() => !result && setSelected(choice.id)}
                  disabled={Boolean(result)}
                  role="radio"
                  aria-checked={chosen}
                >
                  <strong>{choice.text}</strong>
                  <small>{choice.concept.name_en}</small>
                </button>
              );
            })}
          </div>
          {error && <div className="error-state"><p>{error}</p>{error.includes("وارد حساب") && <Link className="button" href="/login">ورود</Link>}</div>}
          {!result ? (
            <button className="button primary practice-submit" onClick={submit} disabled={selected == null || busy}>
              {busy ? "در حال ارزیابی..." : "ثبت پاسخ"}
            </button>
          ) : (
            <div className={`practice-feedback ${result.correct ? "correct" : "wrong"}`}>
              <div className="meta">{result.correct ? "پاسخ درست" : "نیاز به بازبینی"}</div>
              <h4>{result.correct_concept.name_fa || result.correct_concept.name_en}</h4>
              <p>{result.explanation}</p>
              <div className="actions">
                <Link className="button" href={`/concepts/${result.correct_concept.slug}`}>مرور مفهوم</Link>
                <button className="button primary" onClick={next}>{index + 1 === queue?.items.length ? "دیدن نتیجه جلسه" : "سؤال بعد"}</button>
              </div>
            </div>
          )}
        </article>
      )}

      {completed && (
        <div className="card practice-complete">
          <div className="meta">Session Complete</div>
          <h3>این دور تمرین تمام شد.</h3>
          <p>دقت جلسه: <strong>{accuracy.toLocaleString("fa-IR")}٪</strong> از {answered.toLocaleString("fa-IR")} پاسخ.</p>
          <div className="actions">
            <button className="button primary" onClick={restart}>شروع دوباره</button>
            <Link className="button" href="/flashcards">مرور فلش‌کارت‌ها</Link>
            <Link className="button" href="/map?node=concept:cognitive-distortions">دیدن در Graph</Link>
          </div>
        </div>
      )}
    </section>
  );
}
