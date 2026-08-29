"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { KnowledgeGraphData } from "@/lib/types";
import KnowledgeMap from "./KnowledgeMap";

export default function KnowledgeMapLoader({ initialNodeId }: { initialNodeId?: string }) {
  const [data, setData] = useState<KnowledgeGraphData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api<KnowledgeGraphData>("/concept-map/", { signal: controller.signal })
      .then(setData)
      .catch((reason: any) => {
        if (reason?.name !== "AbortError") setError(reason?.message || "نقشه دانش بارگذاری نشد.");
      });
    return () => controller.abort();
  }, []);

  if (error) return <div className="card error-state"><p>{error}</p></div>;
  if (!data) return <div className="card"><div className="meta">Atlas Knowledge Graph</div><h3>در حال دریافت گره‌ها و رابطه‌های واقعی...</h3><p className="muted">Concept، Disorder، Symptom و روابط DSM-backed از API بارگذاری می‌شوند.</p></div>;
  return <KnowledgeMap data={data} initialNodeId={initialNodeId} />;
}
