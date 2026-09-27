"use client";

import Link from "next/link";
import { ArrowUpLeft, BookOpen, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";

type RecentTopic = { slug: string; name_fa?: string; name_en?: string; progress_percent: number };
type HomeDashboard = { continue_learning: RecentTopic[]; continue_concepts: RecentTopic[]; review_due: number; streak: number };

export default function HomeStudyEntry() {
  const [state, setState] = useState<"guest" | "loading" | "ready" | "error">("loading");
  const [data, setData] = useState<HomeDashboard | null>(null);
  useEffect(() => {
    if (!hasToken()) { setState("guest"); return; }
    api<HomeDashboard>("/dashboard/", {}, true).then(value => {
      setData(value);
      setState("ready");
    }).catch(() => setState("error"));
  }, []);
  const recentDisorder = data?.continue_learning?.[0];
  const recentConcept = data?.continue_concepts?.[0];
  const recent = recentDisorder || recentConcept;
  const href = recentDisorder ? `/disorders/${recentDisorder.slug}` : recentConcept ? `/concepts/${recentConcept.slug}` : "/study";
  return <section className="home-continue" aria-labelledby="home-continue-title">
    <div className="home-continue-top"><div><span className="eyebrow">مسیر شخصی</span><h2 id="home-continue-title">ادامهٔ یادگیری</h2></div><BookOpen size={20} aria-hidden="true" /></div>
    {state === "loading" && <p role="status" className="muted">در حال دریافت مسیر مطالعه…</p>}
    {state === "guest" && <><p>با ورود به حساب، موضوع‌های اخیر و مرورهای موعدرسیده‌ات اینجا دیده می‌شوند.</p><div className="actions"><Link className="button primary" href="/login">ورود به حساب</Link><Link className="button" href="/disorders">کاوش بدون حساب</Link></div></>}
    {state === "error" && <><p>مسیر شخصی اکنون در دسترس نیست.</p><Link href="/study" className="button">رفتن به مرکز مطالعه</Link></>}
    {state === "ready" && data && <div className="home-continue-body">
      <div className="home-continue-feature">
        <span className="home-feature-label">{recent ? "آخرین موضوع مطالعه‌شده" : "شروع مسیر مطالعه"}</span>
        <h3>{recent ? recent.name_fa || recent.name_en : "یک موضوع را انتخاب و مطالعه را آغاز کن"}</h3>
        <p>{recent ? "از همین موضوع ادامه بده یا برای مرورهای امروز به مرکز مطالعه برو." : "از اطلس کاوش کن؛ بعد مرور و تمرین‌ها در مسیر شخصی‌ات ثبت می‌شوند."}</p>
        <Link href={href} className="button primary">{recent ? "ادامهٔ مطالعه" : "شروع مطالعه"} <ArrowUpLeft size={16} aria-hidden="true" /></Link>
      </div>
      <div className="home-continue-meta"><span><RotateCcw size={17} aria-hidden="true" /><strong>{faNumber(data.review_due)}</strong> فلش‌کارت موعدرسیده</span><Link href="/flashcards">باز کردن صف مرور <ArrowUpLeft size={15} aria-hidden="true" /></Link></div>
    </div>}
  </section>;
}
