import QuizRunner from "@/components/QuizRunner";
import { publicFetch } from "@/lib/api";
import type { Quiz } from "@/lib/types";

export default async function QuizPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const quiz = await publicFetch<Quiz>(`/quizzes/${slug}/`);
  return (
    <main className="shell page">
      <div className="detail-header">
        <div className="meta">آزمون</div>
        <h1 style={{ fontSize: 48, margin: "8px 0" }}>{quiz.title}</h1>
        <p className="section-copy">{quiz.description}</p>
      </div>
      <QuizRunner quiz={quiz} />
    </main>
  );
}
