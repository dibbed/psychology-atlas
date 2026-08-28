"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import type { DailyChallenge } from "@/lib/types";

export default function DailyChallengeCard() {
  const [challenge, setChallenge] = useState<DailyChallenge | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<{ correct: boolean; explanation: string; selected_choice_id?: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const authenticated = hasToken();
    api<DailyChallenge>("/daily-challenge/", {}, authenticated)
      .then(data => {
        setChallenge(data);
        if (data.attempt) {
          setSelected(data.attempt.selected_choice_id);
          setResult({
            correct: data.attempt.correct,
            explanation: data.attempt.explanation,
            selected_choice_id: data.attempt.selected_choice_id,
          });
        }
      })
      .catch((e: any) => setError(e.message || "چالش امروز دریافت نشد."))
      .finally(() => setLoading(false));
  }, []);

  async function submit() {
    if (selected == null || busy || result) return;
    if (!hasToken()) {
      location.href = "/login";
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await api<{ correct: boolean; explanation: string; selected_choice_id: number }>("/daily-challenge/", {
        method: "POST",
        body: JSON.stringify({ choice_id: selected }),
      }, true);
      setResult(data);
    } catch (e: any) {
      setError(e.message || "ثبت پاسخ چالش انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="card"><p className="muted">در حال دریافت چالش امروز...</p></div>;
  if (error && !challenge) return <div className="card error-state"><p>{error}</p></div>;
  if (!challenge) return null;

  return (
    <section className="card daily-challenge-card">
      <div className="daily-head">
        <div><div className="meta">چالش روزانه</div><h2>یک سؤال، هر روز</h2></div>
        {challenge.concept && <Link href={`/concepts/${challenge.concept.slug}`} className="chip">{challenge.concept.name_fa || challenge.concept.name_en}</Link>}
      </div>
      <h3 className="daily-prompt">{challenge.prompt}</h3>
      <div className="daily-choices">
        {challenge.choices.map(choice => (
          <button
            key={choice.id}
            className={`choice ${selected === choice.id ? "selected" : ""} ${result && selected === choice.id ? (result.correct ? "correct-choice" : "wrong-choice") : ""}`}
            onClick={() => !result && setSelected(choice.id)}
            disabled={Boolean(result) || busy}
          >
            {choice.text}
          </button>
        ))}
      </div>
      {result ? (
        <div className={`challenge-feedback ${result.correct ? "success" : "review"}`}>
          <strong>{result.correct ? "پاسخ درست ✓" : "این مفهوم ارزش مرور دارد"}</strong>
          <p>{result.explanation}</p>
        </div>
      ) : (
        <button className="button primary" onClick={submit} disabled={selected == null || busy}>
          {busy ? "در حال ثبت..." : hasToken() ? "ثبت پاسخ امروز" : "ورود و ثبت پاسخ"}
        </button>
      )}
      {error && <p className="error small">{error}</p>}
    </section>
  );
}
