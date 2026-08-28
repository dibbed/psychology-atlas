"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";

export default function ConceptProgressTracker({ slug }: { slug: string }) {
  useEffect(() => {
    if (!hasToken()) return;
    api(`/concepts/${slug}/view/`, { method: "POST" }, true).catch(() => {});
  }, [slug]);
  return null;
}
