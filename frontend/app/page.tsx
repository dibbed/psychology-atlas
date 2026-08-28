import Link from "next/link";
import DailyChallengeCard from "@/components/DailyChallengeCard";

export default function Home() {
  return (
    <main>
      <section className="shell hero hero-v3">
        <div>
          <div className="meta">Psychology Atlas · نسخه ۰.۳</div>
          <h1>یادگیری را از «خواندن محتوا» به یک شبکه و چرخه مرور تبدیل کن.</h1>
          <p>
            اختلالات و مفاهیم را به‌صورت یک Knowledge Graph ببین، با فلش‌کارت و Spaced Repetition مرور کن،
            چالش روزانه حل کن و Streak، Heatmap و پیشنهادهای مطالعه را از روی فعالیت واقعی بساز.
          </p>
          <div className="actions" style={{ marginTop: 26 }}>
            <Link className="button primary" href="/study">ورود به مرکز مطالعه</Link>
            <Link className="button" href="/search">جست‌وجوی سراسری</Link>
            <Link className="button" href="/map">باز کردن نقشه دانش</Link>
          </div>
        </div>
        <aside className="hero-aside learning-loop-card">
          <strong style={{ color: "var(--text)" }}>Learning Loop v0.3</strong><br />
          یادگیری ← تمرین ← سنجش ← تشخیص ضعف ← زمان‌بندی مرور ← مرور دوباره
          <br /><br />
          Progress دیگر فقط یک عدد تزئینی نیست؛ View، Quiz، Case، Flashcard و Daily Challenge به فعالیت مطالعاتی متصل شده‌اند.
        </aside>
      </section>

      <section className="shell page stack home-v3-sections">
        <div>
          <h2 className="section-title">سه لایه اصلی نسخه ۰.۳</h2>
          <p className="section-copy">اطلس محتوا، شبکه دانش و موتور مطالعه حالا به هم متصل‌اند.</p>
        </div>
        <div className="grid">
          <Link href="/disorders" className="card feature-card"><div className="meta">Disorders Atlas</div><h3>اختلالات را بفهم</h3><p>۳۰ اختلال با نشانه، افتراق، ارزیابی، درمان، Quiz، Case و Conceptهای مرتبط.</p></Link>
          <Link href="/concepts" className="card feature-card"><div className="meta">Concepts Atlas</div><h3>مفهوم را مستقل یاد بگیر</h3><p>۳۵ مفهوم با تعریف ساده، تعریف دانشگاهی، مثال، اختلالات مرتبط و روابط مفهومی.</p></Link>
          <Link href="/map" className="card feature-card"><div className="meta">Knowledge Graph</div><h3>رابطه‌ها را دنبال کن</h3><p>از Disorder، Concept یا Symptom وارد شبکه شو و edgeهای واقعی ثبت‌شده را مرحله‌به‌مرحله دنبال کن.</p></Link>
          <Link href="/flashcards" className="card feature-card"><div className="meta">SRS</div><h3>در زمان درست مرور کن</h3><p>۴۱ فلش‌کارت با ارزیابی دوباره، سخت، خوب و آسان و فاصله مرور شخصی برای هر کاربر.</p></Link>
          <Link href="/study" className="card feature-card"><div className="meta">Study Engine</div><h3>ضعف را به مرور تبدیل کن</h3><p>Streak، Heatmap، Review Queue، Daily Challenge و پیشنهادهای مبتنی بر فعالیت در یک مرکز واحد.</p></Link>
          <Link href="/search" className="card feature-card"><div className="meta">Search V3</div><h3>کل اطلس را بگرد</h3><p>اختلال، Concept و Symptom را با یک جست‌وجوی سراسری پیدا کن.</p></Link>
        </div>

        <div className="grid-2 home-secondary-grid">
          <DailyChallengeCard />
          <div className="card">
            <div className="meta">مسیر قدیمی هنوز حفظ شده</div>
            <h2>Compare + Quiz + Clinical Cases</h2>
            <p>v0.3 قابلیت‌های v0.2 را جایگزین نکرده؛ آن‌ها را به Study Activity و Knowledge Graph وصل کرده است.</p>
            <div className="actions">
              <Link className="button" href="/compare">مقایسه اختلالات</Link>
              <Link className="button" href="/quizzes">آزمون‌ها</Link>
              <Link className="button" href="/cases">کیس‌های بالینی</Link>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
