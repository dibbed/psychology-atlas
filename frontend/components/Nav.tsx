"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { clearTokens, getRefreshToken, hasToken } from "@/lib/auth";

type NavGroup = "explore" | "learn" | "personal" | "account" | "home";

type NavItem = {
  href: string;
  label: string;
  en: string;
  group: NavGroup;
};

const navItems: NavItem[] = [
  { href: "/search", label: "جست‌وجو", en: "Search", group: "explore" },
  { href: "/disorders", label: "اختلالات", en: "Disorders", group: "explore" },
  { href: "/dsm", label: "DSM MASTER", en: "DSM Reference", group: "explore" },
  { href: "/concepts", label: "مفاهیم", en: "Concepts", group: "explore" },
  { href: "/therapies", label: "درمان‌ها", en: "Therapy Atlas", group: "explore" },
  { href: "/psychologists", label: "روان‌شناسان", en: "Psychologists Atlas", group: "explore" },
  { href: "/theories", label: "نظریه‌ها", en: "Theory Atlas", group: "explore" },
  { href: "/timeline", label: "خط زمانی", en: "Psychology Timeline", group: "explore" },
  { href: "/cognitive-distortions", label: "تحریف‌های شناختی", en: "Cognitive Distortions", group: "explore" },
  { href: "/map", label: "نقشه دانش", en: "Knowledge Graph", group: "explore" },
  { href: "/compare", label: "مقایسه", en: "Compare", group: "explore" },
  { href: "/study", label: "مطالعه", en: "Study Center", group: "learn" },
  { href: "/flashcards", label: "فلش‌کارت", en: "Flashcards", group: "learn" },
  { href: "/quizzes", label: "آزمون‌ها", en: "Quizzes", group: "learn" },
  { href: "/cases", label: "کیس‌ها", en: "Clinical Cases", group: "learn" },
  { href: "/saved", label: "ذخیره‌ها", en: "Saved", group: "personal" },
  { href: "/notes", label: "یادداشت‌ها", en: "Notes", group: "personal" },
  { href: "/case-analytics", label: "تحلیل کیس‌ها", en: "Case Analytics", group: "personal" },
  { href: "/dashboard", label: "داشبورد", en: "Dashboard", group: "personal" },
];

const primaryHrefs = new Set(["/search", "/disorders", "/dsm", "/concepts", "/therapies", "/map", "/study"]);
const primaryItems = navItems.filter(item => primaryHrefs.has(item.href));
const moreItems = navItems.filter(item => !primaryHrefs.has(item.href));

const groupLabels: Record<NavGroup, string> = {
  explore: "کاوش دانش",
  learn: "یادگیری و تمرین",
  personal: "فضای شخصی",
  account: "حساب کاربری",
  home: "خانه",
};

function isActive(pathname: string, href: string) {
  if (href === "/therapies" && pathname.startsWith("/techniques/")) return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function detailKind(pathname: string) {
  if (/^\/disorders\/.+/.test(pathname)) return "صفحه اختلال";
  if (/^\/dsm\/.+/.test(pathname)) return "پروفایل MASTER";
  if (/^\/concepts\/.+/.test(pathname)) return "صفحه مفهوم";
  if (/^\/therapies\/.+/.test(pathname)) return "پروفایل درمان";
  if (/^\/techniques\/.+/.test(pathname)) return "پروفایل تکنیک";
  if (/^\/psychologists\/.+/.test(pathname)) return "پروفایل روان‌شناس";
  if (/^\/theories\/.+/.test(pathname)) return "پروفایل نظریه";
  if (/^\/timeline\/.+/.test(pathname)) return "رویداد تاریخی";
  if (/^\/quizzes\/.+/.test(pathname)) return "آزمون";
  if (/^\/case-analytics\/.+/.test(pathname)) return "تحلیل کیس";
  if (/^\/cases\/.+/.test(pathname)) return "کیس بالینی";
  return "";
}

export default function Nav() {
  const pathname = usePathname();
  const [loggedIn, setLoggedIn] = useState(false);
  const moreRef = useRef<HTMLDetailsElement>(null);

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

  useEffect(() => {
    if (moreRef.current) moreRef.current.open = false;
  }, [pathname]);

  const current = useMemo(() => {
    if (pathname === "/") return { href: "/", label: "خانه", en: "Home", group: "home" as NavGroup };
    if (pathname.startsWith("/login")) return { href: "/login", label: "ورود", en: "Sign in", group: "account" as NavGroup };
    if (pathname.startsWith("/register")) return { href: "/register", label: "ساخت حساب", en: "Create account", group: "account" as NavGroup };
    return navItems
      .filter(item => isActive(pathname, item.href))
      .sort((a, b) => b.href.length - a.href.length)[0]
      ?? { href: "/", label: "اطلس", en: "Psychology Atlas", group: "home" as NavGroup };
  }, [pathname]);

  const contextItems = useMemo(() => {
    if (current.group === "home") return navItems.filter(item => ["/disorders", "/dsm", "/study", "/map"].includes(item.href));
    if (current.group === "account") return [];
    return navItems.filter(item => item.group === current.group).slice(0, 10);
  }, [current.group]);

  const moreActive = moreItems.some(item => isActive(pathname, item.href));
  const pageKind = detailKind(pathname);

  async function signOut() {
    const refresh = getRefreshToken();
    try {
      if (refresh) {
        await api<void>(
          "/auth/logout/",
          { method: "POST", body: JSON.stringify({ refresh }) },
          true,
        );
      }
    } catch {
      // Local credentials are always cleared even if the server token already expired.
    } finally {
      clearTokens();
      location.href = "/";
    }
  }

  return (
    <header className="nav">
      <a className="skip-link" href="#main-content">رفتن به محتوای اصلی</a>
      <div className="shell nav-inner">
        <div className="nav-identity">
          <Link href="/" className="brand">اطلس <span>روان‌شناسی</span></Link>
          <div className="nav-current-compact" aria-hidden="true">
            <span className="nav-current-dot" />
            <span>{current.label}</span>
          </div>
        </div>

        <nav className="nav-links" aria-label="ناوبری اصلی">
          {primaryItems.map(item => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                href={item.href}
                className={`nav-link ${active ? "active" : ""}`}
                aria-current={active ? "page" : undefined}
                key={item.href}
              >
                {item.label}
              </Link>
            );
          })}

          <details className={`nav-more ${moreActive ? "active" : ""}`} ref={moreRef}>
            <summary>
              بیشتر
              <svg aria-hidden="true" viewBox="0 0 16 16" width="14" height="14">
                <path d="M3.5 6 8 10.5 12.5 6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </summary>
            <div className="nav-more-panel">
              <div className="nav-more-group">
                <span>یادگیری و تمرین</span>
                {moreItems.filter(item => item.group === "learn").map(item => (
                  <Link
                    href={item.href}
                    className={isActive(pathname, item.href) ? "active" : ""}
                    aria-current={isActive(pathname, item.href) ? "page" : undefined}
                    key={item.href}
                  >
                    <strong>{item.label}</strong><small>{item.en}</small>
                  </Link>
                ))}
              </div>
              <div className="nav-more-group">
                <span>کاوش تکمیلی و فضای شخصی</span>
                {moreItems.filter(item => item.group !== "learn").map(item => (
                  <Link
                    href={item.href}
                    className={isActive(pathname, item.href) ? "active" : ""}
                    aria-current={isActive(pathname, item.href) ? "page" : undefined}
                    key={item.href}
                  >
                    <strong>{item.label}</strong><small>{item.en}</small>
                  </Link>
                ))}
              </div>
            </div>
          </details>
        </nav>

        <div className="nav-spacer" />
        {loggedIn ? (
          <button className="button ghost nav-auth" onClick={signOut}>
            خروج
          </button>
        ) : (
          <Link className={`button nav-auth ${pathname === "/login" ? "active" : ""}`} href="/login">ورود</Link>
        )}
      </div>

      <div className="nav-context" aria-label="موقعیت فعلی در سایت">
        <div className="shell nav-context-inner">
          <div className="nav-location">
            <span className="nav-location-label">{groupLabels[current.group]}</span>
            <span className="nav-context-divider" aria-hidden="true" />
            <strong>{current.label}</strong>
            <small>{current.en}</small>
            {pageKind && <span className="nav-page-kind">{pageKind}</span>}
          </div>
          {contextItems.length > 0 && (
            <nav className="nav-context-links" aria-label="بخش‌های مرتبط">
              {contextItems.map(item => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    href={item.href}
                    className={active ? "active" : ""}
                    aria-current={active ? "page" : undefined}
                    key={item.href}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          )}
        </div>
      </div>
    </header>
  );
}
