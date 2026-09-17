"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { API_URL } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}/auth/login/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: email.trim().toLowerCase(), password })
      });
      if (!response.ok) {
        setError("ایمیل یا رمز عبور نادرست است.");
        return;
      }
      const data = await response.json();
      setTokens(data.access, data.refresh);
      const requestedNext = new URLSearchParams(location.search).get("next");
      const caseMatch = requestedNext?.match(/^\/cases\/([A-Za-z0-9_-]+)\/?$/);
      if (caseMatch) {
        location.href = `/cases/${encodeURIComponent(caseMatch[1])}`;
        return;
      }
      const analyticsMatch = requestedNext?.match(/^\/case-analytics(?:\/([A-Za-z0-9_-]+))?\/?$/);
      if (analyticsMatch) {
        location.href = analyticsMatch[1]
          ? `/case-analytics/${encodeURIComponent(analyticsMatch[1])}`
          : "/case-analytics";
        return;
      }
      location.href = "/dashboard";
    } catch {
      setError("ارتباط با سرور برقرار نشد. اتصال Backend را بررسی کن و دوباره تلاش کن.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell page">
      <form className="form card" onSubmit={submit}>
        <div><div className="meta">حساب کاربری</div><h1>ورود</h1></div>
        <div className="field"><label>ایمیل</label><input type="email" dir="ltr" required value={email} onChange={e => setEmail(e.target.value)} disabled={busy} /></div>
        <div className="field"><label>رمز عبور</label><input type="password" dir="ltr" required value={password} onChange={e => setPassword(e.target.value)} disabled={busy} /></div>
        {error && <p className="error">{error}</p>}
        <button className="button primary" disabled={busy}>{busy ? "در حال ورود..." : "ورود به حساب"}</button>
        <p className="muted small">حساب نداری؟ <Link href="/register">ثبت‌نام کن</Link></p>
      </form>
    </main>
  );
}
