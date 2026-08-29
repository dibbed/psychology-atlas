"use client";

import Link from "next/link";
import { Clock3, LayoutGrid, List, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Category, Disorder } from "@/lib/types";
import {
  clearRecentDisorders,
  getRecentDisorders,
  recentDisordersEvent,
  type RecentDisorder,
} from "@/lib/recentlyViewed";
import DisorderCard from "./DisorderCard";

type ViewMode = "grid" | "compact";

function chapterLabel(category: Category) {
  const match = category.slug.match(/^dsm-chapter-(\d+)$/);
  if (match) return `فصل ${Number(match[1]).toLocaleString("fa-IR")}`;
  return "بخش تکمیلی";
}

export default function SearchDisorders() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [items, setItems] = useState<Disorder[]>([]);
  const [catalogItems, setCatalogItems] = useState<Disorder[]>([]);
  const [recent, setRecent] = useState<RecentDisorder[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Category[]>("/categories/")
      .then(setCategories)
      .catch(() => {});

    const storedView = window.localStorage.getItem("psychology-atlas:disorder-view");
    if (storedView === "compact" || storedView === "grid") setViewMode(storedView);

    const syncRecent = () => setRecent(getRecentDisorders());
    syncRecent();
    window.addEventListener("storage", syncRecent);
    window.addEventListener(recentDisordersEvent, syncRecent);

    const handleShortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey && target?.tagName !== "INPUT" && target?.tagName !== "TEXTAREA") {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleShortcut);

    return () => {
      window.removeEventListener("storage", syncRecent);
      window.removeEventListener(recentDisordersEvent, syncRecent);
      window.removeEventListener("keydown", handleShortcut);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const id = window.setTimeout(() => {
      setLoading(true);
      setError("");
      const params = new URLSearchParams();
      params.set("page_size", "300");
      if (q.trim()) params.set("q", q.trim());
      if (category) params.set("category", category);

      api<{ results: Disorder[] }>(`/disorders/?${params.toString()}`, { signal: controller.signal })
        .then(data => {
          setItems(data.results);
          if (!q.trim() && !category) setCatalogItems(data.results);
        })
        .catch((reason: any) => {
          if (reason?.name !== "AbortError") setError(reason?.message || "دریافت اختلالات انجام نشد.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 180);

    return () => {
      window.clearTimeout(id);
      controller.abort();
    };
  }, [q, category]);

  const totalDisorders = useMemo(
    () => categories.reduce((sum, row) => sum + row.disorder_count, 0),
    [categories],
  );
  const selectedCategory = categories.find(row => row.slug === category) || null;
  const visibleRecent = recent.filter(row => catalogItems.some(item => item.slug === row.slug));
  const hasFilters = Boolean(q.trim() || category);

  function changeView(next: ViewMode) {
    setViewMode(next);
    try {
      window.localStorage.setItem("psychology-atlas:disorder-view", next);
    } catch {
      // View persistence is optional; switching views should still work.
    }
  }

  function resetFilters() {
    setQ("");
    setCategory("");
    searchRef.current?.focus();
  }

  return (
    <section className="disorder-explorer" aria-label="مرورگر اختلالات">
      <aside className="disorder-chapter-rail" aria-label="فصل‌های اختلالات">
        <div className="disorder-rail-head">
          <div>
            <span>DSM chapters</span>
            <strong>مرور فصل‌به‌فصل</strong>
          </div>
          <small>{categories.length.toLocaleString("fa-IR")} بخش</small>
        </div>

        <button
          className={`disorder-chapter-button ${category === "" ? "active" : ""}`}
          onClick={() => setCategory("")}
          aria-pressed={category === ""}
        >
          <span className="disorder-chapter-index">همه</span>
          <span className="disorder-chapter-name"><strong>تمام اختلالات</strong><small>All disorders</small></span>
          <b>{totalDisorders.toLocaleString("fa-IR")}</b>
        </button>

        <div className="disorder-chapter-list">
          {categories.map(row => (
            <button
              className={`disorder-chapter-button ${category === row.slug ? "active" : ""}`}
              onClick={() => setCategory(row.slug)}
              aria-pressed={category === row.slug}
              key={row.slug}
            >
              <span className="disorder-chapter-index">{chapterLabel(row)}</span>
              <span className="disorder-chapter-name">
                <strong>{row.name_fa || row.name_en}</strong>
                <small>{row.name_en}</small>
              </span>
              <b>{row.disorder_count.toLocaleString("fa-IR")}</b>
            </button>
          ))}
        </div>
      </aside>

      <div className="disorder-explorer-main">
        <div className="disorder-explorer-toolbar">
          <div className="disorder-search-box">
            <Search size={18} aria-hidden="true" />
            <input
              ref={searchRef}
              value={q}
              onChange={event => setQ(event.target.value)}
              placeholder="نام فارسی یا انگلیسی، نشانه، افتراق یا موضوع..."
              aria-label="جست‌وجوی اختلالات"
            />
            {q && (
              <button onClick={() => setQ("")} aria-label="پاک کردن جست‌وجو" title="پاک کردن جست‌وجو">
                <X size={16} aria-hidden="true" />
              </button>
            )}
            <kbd>/</kbd>
          </div>

          <select className="filter-select disorder-mobile-category" value={category} onChange={event => setCategory(event.target.value)} aria-label="انتخاب فصل">
            <option value="">همه فصل‌ها · {totalDisorders.toLocaleString("fa-IR")}</option>
            {categories.map(row => (
              <option value={row.slug} key={row.slug}>{row.name_fa || row.name_en} · {row.disorder_count.toLocaleString("fa-IR")}</option>
            ))}
          </select>

          <div className="disorder-view-switch" aria-label="نوع نمایش">
            <button className={viewMode === "grid" ? "active" : ""} onClick={() => changeView("grid")} aria-pressed={viewMode === "grid"} title="نمای کارت">
              <LayoutGrid size={16} aria-hidden="true" /><span>کارت</span>
            </button>
            <button className={viewMode === "compact" ? "active" : ""} onClick={() => changeView("compact")} aria-pressed={viewMode === "compact"} title="نمای فشرده">
              <List size={17} aria-hidden="true" /><span>فشرده</span>
            </button>
          </div>
        </div>

        <div className="disorder-results-summary" aria-live="polite">
          <div>
            <span>{selectedCategory ? chapterLabel(selectedCategory) : "کاتالوگ کامل"}</span>
            <strong>{selectedCategory ? selectedCategory.name_fa || selectedCategory.name_en : "همه اختلالات رسمی"}</strong>
            {selectedCategory?.name_en && <small>{selectedCategory.name_en}</small>}
          </div>
          <div className="disorder-results-number">
            <strong>{loading ? "…" : items.length.toLocaleString("fa-IR")}</strong>
            <span>نتیجه</span>
          </div>
          {hasFilters && <button className="button ghost disorder-reset" onClick={resetFilters}>پاک‌کردن فیلترها</button>}
        </div>

        {!hasFilters && visibleRecent.length > 0 && (
          <section className="recent-disorders" aria-labelledby="recent-disorders-title">
            <div className="recent-disorders-head">
              <div>
                <Clock3 size={16} aria-hidden="true" />
                <div><strong id="recent-disorders-title">اخیراً دیده‌شده</strong><small>ادامه مطالعه از آخرین صفحه‌ها</small></div>
              </div>
              <button onClick={() => { clearRecentDisorders(); setRecent([]); }}>پاک‌کردن</button>
            </div>
            <div className="recent-disorders-row">
              {visibleRecent.map(row => (
                <Link href={`/disorders/${row.slug}`} key={row.slug}>
                  <span>{row.category}</span>
                  <strong>{row.name_fa || row.name_en}</strong>
                  <small>{row.name_en}</small>
                </Link>
              ))}
            </div>
          </section>
        )}

        {error ? (
          <div className="card error-state"><h3>دریافت اطلاعات انجام نشد</h3><p>{error}</p><button className="button" onClick={resetFilters}>بازگشت به کاتالوگ</button></div>
        ) : loading ? (
          <div className="disorder-loading-grid" aria-label="در حال دریافت اختلالات">
            {Array.from({ length: 6 }).map((_, index) => <div className="disorder-loading-card" key={index} />)}
          </div>
        ) : items.length ? (
          viewMode === "grid" ? (
            <div className="disorder-explorer-grid">{items.map(item => <DisorderCard key={item.slug} disorder={item} />)}</div>
          ) : (
            <div className="disorder-compact-list">
              {items.map((item, index) => (
                <Link href={`/disorders/${item.slug}`} className="disorder-compact-row" key={item.slug}>
                  <span className="disorder-compact-index">{(index + 1).toLocaleString("fa-IR")}</span>
                  <div className="disorder-compact-title">
                    <div><strong>{item.name_fa || item.name_en}</strong>{item.data_origin === "dsm_master" && <span>DSM</span>}</div>
                    <small>{item.name_en}</small>
                  </div>
                  <p>{item.short_description}</p>
                  <span className="disorder-compact-category">{item.category}</span>
                </Link>
              ))}
            </div>
          )
        ) : (
          <div className="disorder-empty-state">
            <Search size={24} aria-hidden="true" />
            <h3>نتیجه‌ای پیدا نشد</h3>
            <p>عبارت کوتاه‌تر، نام انگلیسی یا فصل دیگری را امتحان کن.</p>
            <button className="button" onClick={resetFilters}>نمایش همه اختلالات</button>
          </div>
        )}
      </div>
    </section>
  );
}
