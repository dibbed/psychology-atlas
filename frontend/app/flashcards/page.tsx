import FlashcardReview from "@/components/FlashcardReview";

export default async function FlashcardsPage({ searchParams }: { searchParams: Promise<{ concept?: string; disorder?: string }> }) {
  const { concept, disorder } = await searchParams;
  return (
    <main className="shell page stack">
      <div>
        <div className="meta">Spaced Repetition</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>مرور را بر اساس زمان یادگیری تنظیم کن، نه حدس.</h1>
        <p className="section-copy">بعد از دیدن پاسخ، کیفیت یادآوری را ثبت کن. صف مرور بعدی با فاصله زمانی متناسب با پاسخ تو ساخته می‌شود.</p>
      </div>
      <FlashcardReview conceptSlug={concept} disorderSlug={disorder} />
    </main>
  );
}
