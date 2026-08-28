"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Category, Disorder } from "@/lib/types";
import DisorderCard from "./DisorderCard";

export default function SearchDisorders() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [items, setItems] = useState<Disorder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Category[]>("/categories/")
      .then(setCategories)
      .catch(() => {});
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const id = setTimeout(() => {
      setLoading(true);
      setError("");
      const params = new URLSearchParams();
      params.set("page_size", "100");
      if (q.trim()) params.set("q", q.trim());
      if (category) params.set("category", category);

      api<{ results: Disorder[] }>(`/disorders/?${params.toString()}`, { signal: controller.signal })
        .then(data => setItems(data.results))
        .catch((e: any) => {
          if (e?.name !== "AbortError") setError(e.message || "دریافت اختلالات انجام نشد.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 220);

    return () => {
      clearTimeout(id);
      controller.abort();
    };
  }, [q, category]);

  return (
    <div className="stack">
      <div className="atlas-filters">
        <input
          className="search"
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="نام اختلال، نشانه یا موضوع را جست‌وجو کن..."
          aria-label="جست‌وجوی اختلالات"
        />
        <select className="filter-select" value={category} onChange={e => setCategory(e.target.value)} aria-label="فیلتر دسته‌بندی">
          <option value="">همه دسته‌ها</option>
          {categories.map(c => <option value={c.slug} key={c.slug}>{c.name_fa || c.name_en} ({c.disorder_count.toLocaleString("fa-IR")})</option>)}
        </select>
      </div>

      {categories.length > 0 && (
        <div className="category-chips">
          <button className={`chip ${category === "" ? "active" : ""}`} onClick={() => setCategory("")}>همه</button>
          {categories.map(c => (
            <button className={`chip ${category === c.slug ? "active" : ""}`} onClick={() => setCategory(c.slug)} key={c.slug}>
              {c.name_fa || c.name_en}
            </button>
          ))}
        </div>
      )}

      {error ? (
        <div className="card error-state"><h3>دریافت اطلاعات انجام نشد</h3><p>{error}</p></div>
      ) : loading ? (
        <p className="muted">در حال جست‌وجو...</p>
      ) : items.length ? (
        <>
          <div className="results-count">{items.length.toLocaleString("fa-IR")} اختلال نمایش داده می‌شود.</div>
          <div className="grid">{items.map(x => <DisorderCard key={x.slug} disorder={x} />)}</div>
        </>
      ) : (
        <div className="card"><h3>نتیجه‌ای پیدا نشد</h3><p>فیلتر دسته‌بندی را تغییر بده یا عبارت کوتاه‌تر و املای دیگری را امتحان کن.</p></div>
      )}
    </div>
  );
}
