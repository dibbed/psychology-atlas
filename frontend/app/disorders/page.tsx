import SearchDisorders from "@/components/SearchDisorders";
import { publicFetch } from "@/lib/api";
import type { AtlasOverview } from "@/lib/types";

export default async function DisordersPage() {
  let overview: AtlasOverview | null = null;
  try {
    overview = await publicFetch<AtlasOverview>("/atlas-overview/");
  } catch {
    overview = null;
  }

  return (
    <main className="shell page stack">
      <header className="disorders-page-head">
        <div>
          <div className="eyebrow">اطلس بالینی</div>
          <h1 className="section-title">اختلالات را فصل‌به‌فصل کاوش کن.</h1>
          <p className="section-copy">با جست‌وجو یا انتخاب فصل، مدخل‌ها را پیدا کن و از هر اختلال به نشانه‌ها، مفاهیم و منابع مرتبط برس.</p>
        </div>
        {overview && (
          <div className="disorders-live-count">
            <strong>{overview.counts.disorders.toLocaleString("fa-IR")}</strong>
            <span>اختلال فعال</span>
            <small>{overview.counts.categories.toLocaleString("fa-IR")} فصل / دسته فعال</small>
          </div>
        )}
      </header>
      <SearchDisorders />
    </main>
  );
}
