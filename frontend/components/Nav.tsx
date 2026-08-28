"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { clearTokens, hasToken } from "@/lib/auth";

export default function Nav() {
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    const sync = () => setLoggedIn(hasToken());
    sync();
    window.addEventListener("auth-change", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("auth-change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return (
    <header className="nav">
      <div className="shell nav-inner">
        <Link href="/" className="brand">اطلس <span>روان‌شناسی</span></Link>
        <nav className="nav-links" aria-label="ناوبری اصلی">
          <Link href="/search">جست‌وجو</Link>
          <Link href="/disorders">اختلالات</Link>
          <Link href="/concepts">مفاهیم</Link>
          <Link href="/map">نقشه دانش</Link>
          <Link href="/compare">مقایسه</Link>
          <Link href="/flashcards">فلش‌کارت</Link>
          <Link href="/quizzes">آزمون‌ها</Link>
          <Link href="/cases">کیس‌ها</Link>
          <Link href="/study">مطالعه</Link>
          <Link href="/saved">ذخیره‌ها</Link>
          <Link href="/notes">یادداشت‌ها</Link>
          <Link href="/dashboard">داشبورد</Link>
        </nav>
        <div className="nav-spacer" />
        {loggedIn ? (
          <button className="button ghost" onClick={() => { clearTokens(); location.href = "/"; }}>
            خروج
          </button>
        ) : (
          <Link className="button" href="/login">ورود</Link>
        )}
      </div>
    </header>
  );
}
