"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber, faPercent } from "@/lib/fa";
import type { Quiz } from "@/lib/types";

export default function QuizRunner({ quiz }: { quiz: Quiz }) {
  const questions = quiz.questions || [];
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  async function submit() {
    if (!hasToken()) {
      location.href = "/login";
      return;
    }
    setError("");
    try {
      const payload = {
        answers: Object.entries(answers).map(([question_id, choice_id]) => ({
          question_id: Number(question_id),
          choice_id
        }))
      };
      setResult(await api(`/quizzes/${quiz.slug}/submit/`, {
        method: "POST",
        body: JSON.stringify(payload)
      }, true));
    } catch {
      setError("ثبت پاسخ‌های آزمون انجام نشد. دوباره تلاش کن.");
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
        {result.feedback.map((f: any) => (
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
              className={`choice ${answers[q.id] === choice.id ? "selected" : ""}`}
              key={choice.id}
              onClick={() => setAnswers(a => ({ ...a, [q.id]: choice.id }))}
            >
              {choice.text}
            </button>
          ))}
        </section>
      ))}
      {error && <p className="error">{error}</p>}
      <button className="button primary" disabled={Object.keys(answers).length !== questions.length} onClick={submit}>
        پایان آزمون و مشاهده نتیجه
      </button>
    </div>
  );
}
