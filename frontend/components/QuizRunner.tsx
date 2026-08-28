"use client";

import { useState } from "react";
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
            <strong>{f.correct ? "پاسخ درست ✓" : "این سؤال را دوباره مرور کن"}</strong>
            <p style={{ marginTop: 8 }}>{f.explanation}</p>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div>
      {questions.map((q, index) => (
        <section className="question" key={q.id}>
          <div className="meta">سؤال {faNumber(index + 1)} از {faNumber(questions.length)}</div>
          <h3>{q.prompt}</h3>
          {q.choices.map(choice => (
            <button
              type="button"
              className={`choice ${answers[q.id] === choice.id ? "selected" : ""}`}
              key={choice.id}
              onClick={() => setAnswers(a => ({ ...a, [q.id]: choice.id }))}
              disabled={busy}
            >
              {choice.text}
            </button>
          ))}
        </section>
      ))}
      {error && <p className="error">{error}</p>}
      <button className="button primary" disabled={Object.keys(answers).length !== questions.length || busy} onClick={submit}>
        {busy ? "در حال ثبت نتیجه..." : "پایان آزمون و مشاهده نتیجه"}
      </button>
    </div>
  );
}
