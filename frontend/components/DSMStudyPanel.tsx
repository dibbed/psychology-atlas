"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DSMStudyKit } from "@/lib/types";

export default function DSMStudyPanel() {
  const [data, setData] = useState<DSMStudyKit | null>(null);

  useEffect(() => {
    api<DSMStudyKit>("/dsm/study-kit/").then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;
  const glossary = Object.entries(data.glossary).slice(0, 8);

  return (
    <section className="card dsm-study-panel">
      <div className="dsm-study-head">
        <div><div className="meta">DSM MASTER · Study Layer</div><h2>واژه‌نامه و خودآزمایی منبع را وارد مطالعه کن.</h2></div>
        <div className="dsm-study-numbers">
          <div><strong>{data.stats.glossary_terms.toLocaleString("fa-IR")}</strong><span>واژه</span></div>
          <div><strong>{data.stats.self_test_questions.toLocaleString("fa-IR")}</strong><span>سؤال Self-Test</span></div>
          <div><strong>{data.stats.exam_tips.toLocaleString("fa-IR")}</strong><span>نکته امتحانی</span></div>
        </div>
      </div>
      <div className="dsm-glossary-grid">
        {glossary.map(([term, definition]) => (
          <div key={term}><strong>{term.replaceAll("_", " ")}</strong><p>{definition}</p></div>
        ))}
      </div>
      <div className="actions">
        <Link className="button primary" href="/dsm?type=diagnosis">مرور تشخیص‌های MASTER</Link>
        <Link className="button" href="/map?scope=dsm">DSM Graph</Link>
      </div>
    </section>
  );
}
