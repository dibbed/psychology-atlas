import FlashcardReview from "@/components/FlashcardReview";

export default async function FlashcardsPage({ searchParams }: { searchParams: Promise<{ concept?: string; disorder?: string }> }) {
  const { concept, disorder } = await searchParams;
  return (
    <main className="shell page stack">
      <header>
        <div className="eyebrow">مرور فاصله‌دار</div>
        <h1 className="section-title">فلش‌کارت‌های امروز</h1>
        <p className="section-copy">بعد از دیدن پاسخ، کیفیت یادآوری را ثبت کن. صف مرور بعدی با فاصله زمانی متناسب با پاسخ تو ساخته می‌شود.</p>
      </header>
      <FlashcardReview conceptSlug={concept} disorderSlug={disorder} />
    </main>
  );
}
