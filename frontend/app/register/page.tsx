"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { API_URL } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const response = await fetch(`${API_URL}/auth/register/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    if (!response.ok) {
      setError("ثبت‌نام انجام نشد. ایمیل و رمز عبور را بررسی کن. رمز عبور باید حداقل ۸ کاراکتر و به‌اندازه کافی امن باشد.");
      return;
    }
    const data = await response.json();
    setTokens(data.access, data.refresh);
    location.href = "/dashboard";
  }

  return (
    <main className="shell page">
      <form className="form card" onSubmit={submit}>
        <div><div className="meta">ساخت حساب</div><h1>اطلس خودت را شروع کن</h1></div>
        <div className="field"><label>ایمیل</label><input type="email" dir="ltr" required value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label>رمز عبور</label><input type="password" dir="ltr" minLength={8} required value={password} onChange={e => setPassword(e.target.value)} /></div>
        {error && <p className="error">{error}</p>}
        <button className="button primary">ساخت حساب</button>
        <p className="muted small">قبلاً ثبت‌نام کرده‌ای؟ <Link href="/login">وارد شو</Link></p>
      </form>
    </main>
  );
}
