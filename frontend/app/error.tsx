"use client";

import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="shell page">
      <div className="card error-state">
        <div className="meta">خطای صفحه</div>
        <h1>این بخش درست بارگذاری نشد.</h1>
        <p>{error.message || "ارتباط با سرویس یا بارگذاری اطلاعات با مشکل روبه‌رو شد."}</p>
        <div className="actions" style={{ marginTop: 18 }}>
          <button className="button primary" onClick={reset}>تلاش دوباره</button>
          <button className="button" onClick={() => { location.href = "/"; }}>بازگشت به صفحه اصلی</button>
        </div>
      </div>
    </main>
  );
}
