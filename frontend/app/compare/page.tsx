import CompareClient from "@/components/CompareClient";

export default async function ComparePage({ searchParams }: { searchParams: Promise<{ add?: string }> }) {
  const { add } = await searchParams;

  return (
    <main className="shell page stack">
      <div>
        <div className="meta">مقایسه اختلالات</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>الگوهای شبیه را کنار هم ببین.</h1>
        <p className="section-copy">مقایسه فقط از داده‌های ساختاریافته موجود استفاده می‌کند و درصد شباهت ساختگی نمایش نمی‌دهد.</p>
      </div>
      <CompareClient initialSlug={add} />
    </main>
  );
}
