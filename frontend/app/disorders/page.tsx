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
          <div className="meta">اطلس اختلالات · DSM MASTER integrated</div>
          <h1 className="section-title" style={{ fontSize: 44 }}>تشخیص‌های رسمی را فصل‌به‌فصل کاوش کن.</h1>
          <p className="section-copy">اختلالات رسمی موجود در DSM MASTER آموزشی به Atlas متصل شده‌اند. هر صفحه نام فارسی و انگلیسی، داده آموزشی Atlas و پروفایل DSM MASTER متناظر را کنار هم نگه می‌دارد.</p>
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
