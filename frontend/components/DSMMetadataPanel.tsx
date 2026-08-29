"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { StructuredValue } from "./DSMRecordView";

export default function DSMMetadataPanel() {
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [metadata, setMetadata] = useState<Record<string, unknown> | null>(null);

  const loadMetadata = async () => {
    if (loaded || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await api<{ key: string; metadata: Record<string, unknown> }>("/dsm/metadata/");
      setMetadata(response.metadata);
      setLoaded(true);
    } catch (reason: any) {
      setError(reason?.message || "دریافت metadata انجام نشد.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <details className="card" onToggle={event => {
      if (event.currentTarget.open) void loadMetadata();
    }}>
      <summary>سایر داده‌های سطح فایل، نمایه‌ها و راهنماهای MASTER</summary>
      <p className="muted small dsm-metadata-note">این بخش فقط هنگام باز شدن از API خوانده می‌شود تا صفحه اصلی سبک بماند. داده‌ها بدون بازنویسی نمایش داده می‌شوند.</p>
      {loading && <p className="muted small dsm-metadata-note">در حال دریافت داده‌های تکمیلی...</p>}
      {error && <p className="error dsm-metadata-note">{error}</p>}
      {metadata && <StructuredValue value={metadata} />}
    </details>
  );
}
