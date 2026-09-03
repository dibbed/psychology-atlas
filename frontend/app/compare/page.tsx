import Link from "next/link";
import CompareClient from "@/components/CompareClient";
import TherapyCompareClient from "@/components/TherapyCompareClient";

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ add?: string; type?: string }>;
}) {
  const { add, type } = await searchParams;
  const therapyMode = type === "therapy";

  return (
    <main className="shell page stack compare-page-v055">
      <header className="compare-page-head">
        <div>
          <div className="meta">Structured Compare</div>
          <h1 className="section-title" style={{ fontSize: 44 }}>
            {therapyMode ? "رویکردهای درمانی را بدون رتبه‌بندی کنار هم ببین." : "الگوهای اختلال را کنار هم ببین."}
          </h1>
          <p className="section-copy">
            {therapyMode
              ? "مقایسه Therapy فقط از داده‌های ساختاریافته و source-backed استفاده می‌کند؛ Clinical Role و Evidence Basis نمایش داده می‌شوند اما هیچ «بهترین درمان» یا توصیه شخصی تولید نمی‌شود."
              : "مقایسه Disorder فقط از داده‌های ساختاریافته موجود استفاده می‌کند و درصد شباهت ساختگی نمایش نمی‌دهد."}
          </p>
        </div>
        <nav className="compare-domain-switch" aria-label="نوع مقایسه">
          <Link className={`button ${!therapyMode ? "primary" : ""}`} href="/compare">مقایسه اختلالات</Link>
          <Link className={`button ${therapyMode ? "primary" : ""}`} href="/compare?type=therapy">مقایسه درمان‌ها</Link>
        </nav>
      </header>
      {therapyMode ? <TherapyCompareClient initialSlug={add} /> : <CompareClient initialSlug={add} />}
    </main>
  );
}
