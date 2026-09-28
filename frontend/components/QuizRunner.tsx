"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber, faPercent } from "@/lib/fa";
import type { Quiz } from "@/lib/types";

type QuizResult = {
  score: number;
  correct_count: number;
  total_questions: number;
  feedback: { question_id: number; correct: boolean; explanation: string }[];
};

export default function QuizRunner({ quiz }: { quiz: Quiz }) {
  const questions = quiz.questions || [];
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (busy || result || event.altKey || event.ctrlKey || event.metaKey) return;
      if ((event.target as HTMLElement).closest("input, textarea, select, [contenteditable=true]")) return;
      const index = Number(event.key) - 1;
      const question = questions[currentIndex];
      if (question && Number.isInteger(index) && index >= 0 && index < question.choices.length) {
        setAnswers(rows => ({ ...rows, [question.id]: question.choices[index].id }));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, currentIndex, questions, result]);

  async function submit() {
    if (busy) return;
    if (!hasToken()) {
      location.href = "/login";
      return;
    }
    setError("");
    setBusy(true);
    try {
      const payload = {
        answers: Object.entries(answers).map(([question_id, choice_id]) => ({
          question_id: Number(question_id),
          choice_id
        }))
      };
      setResult(await api<QuizResult>(`/quizzes/${quiz.slug}/submit/`, {
        method: "POST",
        body: JSON.stringify(payload)
      }, true));
    } catch (e: any) {
      setError(e.message || "ثبت پاسخ‌های آزمون انجام نشد. دوباره تلاش کن.");
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="stack">
        <div className="card">
          <div className="meta">آزمون تکمیل شد</div>
          <h3 style={{ fontSize: 34 }}>{faPercent(result.score)}</h3>
          <p>{faNumber(result.correct_count)} پاسخ از {faNumber(result.total_questions)} سؤال درست بود.</p>
        </div>
        {result.feedback.map(f => (
          <div className="card" key={f.question_id}>
            <strong>{questions.find(q => q.id === f.question_id)?.prompt}</strong>
            <p>{f.correct ? "پاسخ درست ✓" : "این سؤال را دوباره مرور کن"}</p>
            <p style={{ marginTop: 8 }}>{f.explanation}</p>
          </div>
        ))}
      </div>
    );
  }

  const question = questions[currentIndex];
  if (!question) return <div className="card">برای این آزمون هنوز سؤالی ثبت نشده است.</div>;
  return <div className="quiz-session">
    <div className="quiz-session-head"><div><span className="eyebrow">آزمون آموزشی</span><strong>سؤال {faNumber(currentIndex + 1)} از {faNumber(questions.length)}</strong></div><span>{faNumber(Object.keys(answers).length)} پاسخ ثبت‌شده</span></div>
    <div className="quiz-progress" aria-label={`سؤال ${faNumber(currentIndex + 1)} از ${faNumber(questions.length)}`}><span style={{ width: `${(currentIndex + 1) / questions.length * 100}%` }} /></div>
    <section className="question quiz-current-question" aria-labelledby="quiz-question-title" key={question.id}>
      <div className="meta">سؤال {faNumber(currentIndex + 1)}</div>
      <h2 id="quiz-question-title">{question.prompt}</h2>
      <div className="quiz-choices">{question.choices.map((choice, index) => <button type="button" className={`choice ${answers[question.id] === choice.id ? "selected" : ""}`} aria-pressed={answers[question.id] === choice.id} key={choice.id} onClick={() => setAnswers(rows => ({ ...rows, [question.id]: choice.id }))} disabled={busy}><span className="quiz-choice-index">{faNumber(index + 1)}</span>{choice.text}</button>)}</div>
    </section>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="quiz-session-actions"><button className="button" type="button" disabled={currentIndex === 0 || busy} onClick={() => setCurrentIndex(index => index - 1)}>سؤال قبل</button>{currentIndex < questions.length - 1 ? <button className="button primary" type="button" disabled={answers[question.id] == null || busy} onClick={() => setCurrentIndex(index => index + 1)}>سؤال بعد</button> : <button className="button primary" type="button" disabled={Object.keys(answers).length !== questions.length || busy} onClick={submit}>{busy ? "در حال ثبت نتیجه…" : "پایان آزمون و دیدن توضیح‌ها"}</button>}</div>
    <p className="muted small">برای انتخاب پاسخ می‌توانی از کلیدهای عددی استفاده کنی. تا ثبت نهایی، امکان بازگشت به سؤال‌های قبل وجود دارد.</p>
  </div>;
}
