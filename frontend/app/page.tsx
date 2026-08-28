import Link from "next/link";

export default function Home() {
  return (
    <main>
      <section className="shell hero">
        <div>
          <div className="meta">نسخه آموزشی ۰.۲</div>
          <h1>روان‌شناسی را به‌صورت یک سیستم یاد بگیر، نه مجموعه‌ای از مقاله‌های جدا.</h1>
          <p>
            ۳۰ اختلال را مرور کن، تفاوت الگوهای نزدیک را ببین، کیس‌های مرحله‌ای حل کن،
            با آزمون‌های آموزشی تمرین کن، یادداشت شخصی بنویس و پیشرفت مطالعه را از روی فعالیت واقعی دنبال کن.
          </p>
          <div className="actions" style={{ marginTop: 26 }}>
            <Link className="button primary" href="/disorders">ورود به اطلس اختلالات</Link>
            <Link className="button" href="/cases">حل یک کیس بالینی</Link>
          </div>
        </div>
        <aside className="hero-aside">
          <strong style={{ color: "var(--text)" }}>چرخه یادگیری</strong><br />
          کاوش ← مقایسه ← آزمون ← استدلال ← یادداشت ← مرور
          <br /><br />
          هدف اطلس این است که ارتباط میان نشانه‌ها، اختلالات و تصمیم‌های آموزشی را قابل مشاهده کند، نه اینکه فقط متن طولانی نمایش دهد.
        </aside>
      </section>

      <section className="shell page stack">
        <div>
          <h2 className="section-title">سطوح اصلی یادگیری</h2>
          <p className="section-copy">هر بخش برای یک نوع سؤال مطالعاتی طراحی شده است.</p>
        </div>
        <div className="grid">
          <Link href="/disorders" className="card"><div className="meta">اطلس</div><h3>درک کن</h3><p>۳۰ اختلال در هفت دسته را با نشانه‌ها، ارزیابی، درمان، سیر و منابع مرور کن.</p></Link>
          <Link href="/compare" className="card"><div className="meta">مقایسه</div><h3>تفاوت‌ها را پیدا کن</h3><p>۲ تا ۴ اختلال را کنار هم بگذار و ابعاد واقعی ثبت‌شده را مقایسه کن.</p></Link>
          <Link href="/cases" className="card"><div className="meta">کیس بالینی</div><h3>استدلال کن</h3><p>شش کیس مرحله‌ای را بدون دیدن زودهنگام اطلاعات مراحل بعد پیش ببر.</p></Link>
          <Link href="/quizzes" className="card"><div className="meta">آزمون</div><h3>یادآوری کن</h3><p>پنج آزمون هشت‌سؤالی را حل کن و برای هر پاسخ توضیح آموزشی دریافت کن.</p></Link>
          <Link href="/notes" className="card"><div className="meta">یادداشت</div><h3>برای خودت بنویس</h3><p>برای هر اختلال یادداشت خصوصی بساز و آخرین نکته‌ها را در داشبورد ببین.</p></Link>
          <Link href="/dashboard" className="card"><div className="meta">داشبورد</div><h3>ادامه بده</h3><p>میانگین آزمون، کیس، موضوعات ضعیف، روزهای فعالیت و پیشرفت هر موضوع را ببین.</p></Link>
        </div>
      </section>
    </main>
  );
}
