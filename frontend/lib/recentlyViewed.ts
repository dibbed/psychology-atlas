import type { Disorder } from "@/lib/types";

const STORAGE_KEY = "psychology-atlas:recent-disorders:v1";
const EVENT_NAME = "atlas-recent-disorders-change";
const MAX_ITEMS = 6;

export type RecentDisorder = Pick<
  Disorder,
  "slug" | "name_en" | "name_fa" | "category" | "category_slug" | "data_origin"
> & { viewed_at: string };

export function getRecentDisorders(): RecentDisorder[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(item => item && typeof item.slug === "string").slice(0, MAX_ITEMS);
  } catch {
    return [];
  }
}

export function rememberDisorder(disorder: Disorder) {
  if (typeof window === "undefined") return;
  const item: RecentDisorder = {
    slug: disorder.slug,
    name_en: disorder.name_en,
    name_fa: disorder.name_fa,
    category: disorder.category,
    category_slug: disorder.category_slug,
    data_origin: disorder.data_origin,
    viewed_at: new Date().toISOString(),
  };
  const next = [item, ...getRecentDisorders().filter(row => row.slug !== disorder.slug)].slice(0, MAX_ITEMS);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent(EVENT_NAME));
  } catch {
    // Private browsing or storage restrictions should never block a Disorder page.
  }
}

export function clearRecentDisorders() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
    window.dispatchEvent(new CustomEvent(EVENT_NAME));
  } catch {
    // Treat recent history as an optional progressive enhancement.
  }
}

export const recentDisordersEvent = EVENT_NAME;
