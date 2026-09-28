import StudyCenter from "@/components/StudyCenter";

export default function StudyPage() {
  return (
    <main className="shell page stack study-command-page">
      <header>
        <div className="eyebrow">مرکز مطالعه</div>
        <h1 className="section-title">امروز از کجا ادامه می‌دهی؟</h1>
        <p className="section-copy">برنامه، مرورهای موعدرسیده و پیشنهادهای مبتنی بر فعالیت خودت را در یک جا ببین.</p>
      </header>
      <StudyCenter />
    </main>
  );
}
