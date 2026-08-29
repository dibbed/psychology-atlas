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
          <div className="meta">Psychology Atlas v0.3.1 · Disorders Explorer</div>
          <h1 className="section-title" style={{ fontSize: 44 }}>۲۴۱ اختلال را مثل یک کاتالوگ علمی مرور کن.</h1>
          <p className="section-copy">فصل DSM را انتخاب کن، با نام فارسی یا انگلیسی و داده‌های آموزشی عمیق جست‌وجو کن، بین نمای کارت و فهرست فشرده جابه‌جا شو و مطالعه را از اختلالات اخیراً دیده‌شده ادامه بده.</p>
        </div>
        {overview && (
          <div className="disorders-live-count">
            <strong>{overview.counts.disorders.toLocaleString("fa-IR")}</strong>
            <span>صفحه اختلال canonical</span>
            <small>{overview.counts.categories.toLocaleString("fa-IR")} فصل / دسته فعال</small>
          </div>
        )}
      </header>
      <SearchDisorders />
    </main>
  );
}
