"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type { ReviewQueueItem } from "@/lib/types";

const ratings = [
  ["again", "دوباره", "کمتر از ۱۰ دقیقه"],
  ["hard", "سخت", "فاصله کوتاه"],
  ["good", "خوب", "فاصله استاندارد"],
  ["easy", "آسان", "فاصله بلندتر"],
] as const;

export default function FlashcardReview({ conceptSlug, disorderSlug }: { conceptSlug?: string; disorderSlug?: string }) {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [reviewed, setReviewed] = useState(0);
  const [queueMeta, setQueueMeta] = useState({ due: 0, fresh: 0 });

  const load = useCallback(() => {
    if (!hasToken()) {
      setAuthenticated(false);
      setLoading(false);
      return;
    }
    setAuthenticated(true);
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ limit: "50" });
    if (conceptSlug) params.set("concept", conceptSlug);
    if (disorderSlug) params.set("disorder", disorderSlug);
    api<{ items: ReviewQueueItem[]; due_count: number; new_count: number }>(`/flashcards/review-queue/?${params}`, {}, true)
      .then(data => {
        setItems(data.items);
        setQueueMeta({ due: data.due_count, fresh: data.new_count });
        setRevealed(false);
      })
      .catch((e: any) => setError(e.message || "صف مرور دریافت نشد."))
      .finally(() => setLoading(false));
  }, [conceptSlug, disorderSlug]);

  useEffect(() => load(), [load]);

  async function rate(rating: string) {
    const current = items[0];
    if (!current || busy) return;
    setBusy(true);
    setError("");
    try {
      await api(`/flashcards/${current.flashcard.slug}/review/`, {
        method: "POST",
        body: JSON.stringify({ rating }),
      }, true);
      setItems(rows => rows.slice(1));
      setQueueMeta(meta => current.is_new
        ? { ...meta, fresh: Math.max(0, meta.fresh - 1) }
        : { ...meta, due: Math.max(0, meta.due - 1) }
      );
      setReviewed(value => value + 1);
      setRevealed(false);
    } catch (e: any) {
      setError(e.message || "ثبت مرور انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || busy || !items.length) return;
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable=true]")) return;
      if (!revealed && event.code === "Space") {
        event.preventDefault();
        setRevealed(true);
      } else if (revealed && ["1", "2", "3", "4"].includes(event.key)) {
        void rate(ratings[Number(event.key) - 1][0]);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, items, revealed]);

  if (authenticated === null || loading) return <div className="card"><p className="muted">در حال ساخت صف مرور...</p></div>;
  if (!authenticated) {
    return <div className="card"><h3>مرور شخصی نیاز به حساب دارد</h3><p>زمان‌بندی SRS برای هر کاربر جدا ذخیره می‌شود.</p><Link className="button primary" href="/login">ورود به حساب</Link></div>;
  }
  if (error && !items.length) return <div className="card error-state"><p>{error}</p><button className="button" onClick={load}>تلاش دوباره</button></div>;

  const current = items[0];
  if (!current) {
    return (
      <div className="card review-complete">
        <div className="meta">صف امروز تمام شد</div>
        <h2>{reviewed ? `${faNumber(reviewed)} کارت مرور شد.` : "فعلاً کارت موعدرسیده‌ای باقی نمانده."}</h2>
        <p className="muted">زمان مرور بعدی بر اساس پاسخ‌های ثبت‌شده دوباره محاسبه می‌شود.</p>
        <div className="actions"><button className="button" onClick={load}>بررسی دوباره صف</button><Link className="button" href="/concepts">مرور مفاهیم</Link></div>
      </div>
    );
  }

  const card = current.flashcard;
  return (
    <div className="stack flashcard-review-wrap">
      <div className="review-summary">
        <span>موعدرسیده: {faNumber(queueMeta.due)}</span>
        <span>جدید: {faNumber(queueMeta.fresh)}</span>
        <span>مرور این جلسه: {faNumber(reviewed)}</span>
        <span>باقی‌مانده: {faNumber(items.length)}</span>
      </div>
      <div className="review-session-progress" aria-label={`پیشرفت جلسه: ${faNumber(reviewed)} کارت از ${faNumber(reviewed + items.length)} کارت`}>
        <span style={{ width: `${reviewed / (reviewed + items.length) * 100}%` }} />
      </div>

      <article className={`flashcard-stage ${revealed ? "revealed" : ""}`}>
        <div className="flashcard-meta">
          <span>{current.is_new ? "کارت جدید" : "مرور زمان‌بندی‌شده"}</span>
          <span>{card.concept?.name_fa || card.disorder?.name_fa || "مرور عمومی"}</span>
        </div>
        <div className="flashcard-face">
          <div className="meta">روی کارت</div>
          <h2>{card.front}</h2>
          {card.hint && <p className="muted small">راهنما: {card.hint}</p>}
        </div>
        {revealed ? (
          <div className="flashcard-answer" aria-live="polite">
            <div className="meta">پشت کارت</div>
            <p>{card.back}</p>
          </div>
        ) : (
          <button className="button primary reveal-button" onClick={() => setRevealed(true)}>نمایش پاسخ <small>کلید فاصله</small></button>
        )}
      </article>

      {revealed && (
        <div className="rating-grid" aria-label="کیفیت یادآوری">
          {ratings.map(([value, label, hint]) => (
            <button className="rating-button" key={value} onClick={() => rate(value)} disabled={busy} aria-label={`${label}، کلید ${faNumber(ratings.findIndex(row => row[0] === value) + 1)}`}>
              <strong>{label}</strong><span>{hint}</span><kbd>{faNumber(ratings.findIndex(row => row[0] === value) + 1)}</kbd>
            </button>
          ))}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
