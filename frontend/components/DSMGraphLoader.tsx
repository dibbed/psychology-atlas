"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DSMGraphData } from "@/lib/types";
import DSMGraphExplorer from "./DSMGraphExplorer";

export default function DSMGraphLoader({ initialNodeId }: { initialNodeId?: string }) {
  const [data, setData] = useState<DSMGraphData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api<DSMGraphData>("/dsm/graph/", { signal: controller.signal })
      .then(setData)
      .catch((reason: any) => {
        if (reason?.name !== "AbortError") setError(reason?.message || "DSM Graph بارگذاری نشد.");
      });
    return () => controller.abort();
  }, []);

  if (error) return <div className="card error-state"><p>{error}</p></div>;
  if (!data) return <div className="card dsm-graph-loading"><div className="meta">DSM MASTER Graph</div><h3>در حال ساخت نمای شبکه از ۴۳۸ گره...</h3><p className="muted">ساختار، عنوان‌های نزدیک و افتراق‌های resolve‌شده از API دریافت می‌شوند.</p></div>;
  return <DSMGraphExplorer data={data} initialNodeId={initialNodeId} />;
}
