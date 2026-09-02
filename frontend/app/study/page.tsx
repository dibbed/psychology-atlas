import StudyCenter from "@/components/StudyCenter";

export default function StudyPage() {
  return (
    <main className="shell page stack">
      <div>
        <div className="meta">Study Engine</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>مطالعه را به یک چرخه قابل‌اندازه‌گیری تبدیل کن.</h1>
        <p className="section-copy">مرورهای موعدرسیده، Streak، Heatmap، چالش روزانه و پیشنهادهای مطالعه در یک مرکز واحد جمع شده‌اند.</p>
      </div>
      <StudyCenter />
    </main>
  );
}
