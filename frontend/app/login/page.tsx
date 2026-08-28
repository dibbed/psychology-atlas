"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { API_URL } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const response = await fetch(`${API_URL}/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: email.toLowerCase(), password })
    });
    if (!response.ok) {
      setError("ایمیل یا رمز عبور نادرست است.");
      return;
    }
    const data = await response.json();
    setTokens(data.access, data.refresh);
    location.href = "/dashboard";
  }

  return (
    <main className="shell page">
      <form className="form card" onSubmit={submit}>
        <div><div className="meta">حساب کاربری</div><h1>ورود</h1></div>
        <div className="field"><label>ایمیل</label><input type="email" dir="ltr" required value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label>رمز عبور</label><input type="password" dir="ltr" required value={password} onChange={e => setPassword(e.target.value)} /></div>
        {error && <p className="error">{error}</p>}
        <button className="button primary">ورود به حساب</button>
        <p className="muted small">حساب نداری؟ <Link href="/register">ثبت‌نام کن</Link></p>
      </form>
    </main>
  );
}
