"use client";

import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type { ClinicalCase } from "@/lib/types";

export default function CaseRunner({ item }: { item: ClinicalCase }) {
  const steps = item.steps || [];
  const allQuestions = useMemo(() => steps.flatMap(s => s.questions), [steps]);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [currentStep, setCurrentStep] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const step = steps[currentStep];
  const currentAnswered = step ? step.questions.every(q => answers[q.id]) : false;
  const isLast = currentStep === steps.length - 1;

  async function submit() {
    if (!hasToken()) {
      location.href = "/login";
      return;
    }
    try {
      setBusy(true);
      setError("");
      const data = await api<any>(`/cases/${item.slug}/submit/`, {
        method: "POST",
        body: JSON.stringify({
          answers: Object.entries(answers).map(([question_id, choice_id]) => ({
            question_id: Number(question_id),
            choice_id
          }))
        })
      }, true);
      setResult(data);
    } catch (e: any) {
      setError(e.message || "ارسال پاسخ‌های کیس انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  if (!steps.length) return <div className="card"><p>برای این کیس هنوز مرحله‌ای ثبت نشده است.</p></div>;

  if (result) {
    const fullCredit = result.feedback.filter((f: any) => f.full_credit).length;
    const missed = result.feedback.filter((f: any) => !f.full_credit);
    const percent = result.max_score ? Math.round(result.score * 100 / result.max_score) : 0;

    return (
      <div className="stack">
        <div className="case-result card">
          <div>
            <div className="meta">کیس بالینی تکمیل شد</div>
            <h3 style={{ fontSize: 34 }}>{faNumber(result.score)} از {faNumber(result.max_score)}</h3>
            <p>{faNumber(percent)}٪ امتیاز کل و {faNumber(fullCredit)} پاسخ با امتیاز کامل.</p>
          </div>
          <div className="score-ring">{faNumber(percent)}٪</div>
        </div>

        {missed.length > 0 && (
          <div className="card">
            <div className="meta">موارد نیازمند مرور</div>
            <p style={{ marginTop: 8 }}>در {faNumber(missed.length)} تصمیم، امتیاز کامل نگرفتی. بازخوردهای زیر را مرور کن.</p>
          </div>
        )}

        {result.feedback.map((f: any, index: number) => (
          <div className={`card feedback-card ${f.full_credit ? "success" : "review"}`} key={f.question_id}>
            <div className="feedback-head">
              <strong>تصمیم {faNumber(index + 1)}</strong>
              <span>{faNumber(f.awarded_score)} از {faNumber(f.max_score)} امتیاز</span>
            </div>
            <p style={{ marginTop: 10 }}>{f.feedback}</p>
            <p style={{ marginTop: 8 }}>{f.explanation}</p>
          </div>
        ))}
        <button className="button" onClick={() => { setResult(null); setAnswers({}); setCurrentStep(0); }}>حل دوباره کیس</button>
      </div>
    );
  }

  return (
    <div className="case-runner">
      <div className="case-progress">
        {steps.map((_, index) => (
          <div className={`case-progress-step ${index <= currentStep ? "active" : ""}`} key={index}>
            <span>{faNumber(index + 1)}</span>
          </div>
        ))}
      </div>

      <section className="card case-stage" key={step.id}>
        <div className="meta">مرحله {faNumber(currentStep + 1)} از {faNumber(steps.length)}</div>
        <h2>{step.title}</h2>
        <p className="case-narrative">{step.narrative}</p>

        {step.questions.map(q => (
          <div className="question" key={q.id}>
            <h3>{q.prompt}</h3>
            {q.choices.map(choice => (
              <button
                type="button"
                className={`choice ${answers[q.id] === choice.id ? "selected" : ""}`}
                key={choice.id}
                onClick={() => setAnswers(a => ({ ...a, [q.id]: choice.id }))}
              >
                {choice.text}
              </button>
            ))}
          </div>
        ))}

        {error && <p className="error">{error}</p>}
        <div className="actions" style={{ marginTop: 18 }}>
          {currentStep > 0 && <button className="button" onClick={() => setCurrentStep(x => x - 1)}>مرحله قبل</button>}
          {!isLast ? (
            <button className="button primary" disabled={!currentAnswered} onClick={() => setCurrentStep(x => x + 1)}>
              نمایش مرحله بعد
            </button>
          ) : (
            <button
              className="button primary"
              disabled={!currentAnswered || Object.keys(answers).length !== allQuestions.length || busy}
              onClick={submit}
            >
              {busy ? "در حال ارزیابی..." : "پایان کیس و دریافت بازخورد"}
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
