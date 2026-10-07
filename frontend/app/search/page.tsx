import GlobalSearch from "@/components/GlobalSearch";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  return (
    <main className="shell page stack">
      <div>
        <div className="meta">جست‌وجوی اطلس</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>در کل اطلس جست‌وجو کن.</h1>
        <p className="section-copy">یک عبارت را همزمان میان ساختارهای مغز، ابزارهای ارزیابی، اختلالات، مفاهیم، درمان‌ها، تکنیک‌ها، روان‌شناسان، نظریه‌ها، رویدادهای تاریخی، نشانه‌ها و مرجع DSM جست‌وجو کن.</p>
      </div>
      <GlobalSearch initialQuery={q || ""} />
    </main>
  );
}
