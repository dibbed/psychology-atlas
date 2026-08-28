import GlobalSearch from "@/components/GlobalSearch";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  return (
    <main className="shell page stack">
      <div>
        <div className="meta">Search V3</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>در کل اطلس جست‌وجو کن.</h1>
        <p className="section-copy">یک عبارت می‌تواند همزمان میان اختلالات، مفاهیم و نشانه‌های ساختاریافته جست‌وجو شود.</p>
      </div>
      <GlobalSearch initialQuery={q || ""} />
    </main>
  );
}
