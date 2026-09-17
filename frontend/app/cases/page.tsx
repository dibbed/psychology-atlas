import Link from "next/link";
import { publicFetch } from "@/lib/api";
import type { ClinicalCase } from "@/lib/types";

function difficultyLabel(value: string) {
  if (value === "introductory") return "مقدماتی";
  if (value === "intermediate") return "متوسط";
  if (value === "advanced") return "پیشرفته";
  return value;
}

export default async function CasesPage() {
  const data = await publicFetch<{ results: ClinicalCase[] }>("/cases/");
  return (
    <main className="shell page stack">
      <div className="analytics-page-head">
        <div>
          <div className="meta">کیس‌های بالینی</div>
          <h1 className="section-title" style={{ fontSize: 44 }}>اطلاعات را مرحله‌به‌مرحله بررسی کن.</h1>
          <p className="section-copy">در هر کیس، مرحله بعد فقط پس از تصمیم‌گیری درباره مرحله فعلی نمایش داده می‌شود. این تمرین آموزشی است و شبیه‌ساز تشخیص بیمار واقعی نیست.</p>
        </div>
        <Link className="button" href="/case-analytics">تحلیل کیس‌های من</Link>
      </div>
      <div className="grid">
        {data.results.map(c => (
          <Link href={`/cases/${c.slug}`} className="card" key={c.slug}>
            <div className="meta">سطح {difficultyLabel(c.difficulty)} · {c.step_count?.toLocaleString("fa-IR") || "-"} مرحله</div>
            <h3>{c.title}</h3>
            <p>{c.patient_summary}</p>
            {c.primary_disorder && <div className="muted small" style={{ marginTop: 12 }}>موضوع محوری: {c.primary_disorder.name_fa || c.primary_disorder.name_en}</div>}
          </Link>
        ))}
      </div>
    </main>
  );
}
