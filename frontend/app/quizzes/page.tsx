import Link from "next/link";
import { publicFetch } from "@/lib/api";
import type { Quiz } from "@/lib/types";

export default async function QuizzesPage() {
  const data = await publicFetch<{ results: Quiz[] }>("/quizzes/");
  return (
    <main className="shell page stack">
      <header>
        <div className="eyebrow">تمرین بازیابی</div>
        <h1 className="section-title">آزمون‌ها</h1>
        <p className="section-copy">آزمون‌ها برای تمرین بازیابی و افتراق مفاهیم طراحی شده‌اند. امتیازها در حساب کاربری ثبت می‌شوند.</p>
      </header>
      <div className="grid">
        {data.results.map(q => (
          <Link href={`/quizzes/${q.slug}`} className="card" key={q.slug}>
            <div className="meta">{q.question_count?.toLocaleString("fa-IR") || "-"} سؤال</div>
            <h3>{q.title}</h3>
            <p>{q.description}</p>
            {q.disorder && <div className="muted small" style={{ marginTop: 12 }}>موضوع محوری: {q.disorder.name_fa || q.disorder.name_en}</div>}
          </Link>
        ))}
      </div>
    </main>
  );
}
