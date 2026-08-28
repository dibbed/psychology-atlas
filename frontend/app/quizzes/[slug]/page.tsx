import { notFound } from "next/navigation";
import QuizRunner from "@/components/QuizRunner";
import { ApiError, publicFetch } from "@/lib/api";
import type { Quiz } from "@/lib/types";

export default async function QuizPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let quiz: Quiz;
  try {
    quiz = await publicFetch<Quiz>(`/quizzes/${slug}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

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
