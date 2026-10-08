"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { KnowledgeGraphData } from "@/lib/types";
import KnowledgeMap from "./KnowledgeMap";

export default function KnowledgeMapLoader({ initialNodeId }: { initialNodeId?: string }) {
  const [data, setData] = useState<KnowledgeGraphData | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setData(null);
    api<KnowledgeGraphData>("/concept-map/", { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch((reason: any) => {
        if (!controller.signal.aborted && reason?.name !== "AbortError") setError(reason?.message || "نقشه دانش بارگذاری نشد.");
      });
    return () => controller.abort();
  }, [retry]);

  if (error) return <div className="card error-state" role="alert"><p>{error}</p><button type="button" className="button" onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button></div>;
  if (!data) return <div className="card" role="status"><h3>در حال دریافت گره‌ها و رابطه‌های ثبت‌شده…</h3><p className="muted">گره‌های اطلس، ساختارهای مغز و ابزارهای ارزیابی از سرویس بارگذاری می‌شوند.</p></div>;
  return <KnowledgeMap data={data} initialNodeId={initialNodeId} />;
}
