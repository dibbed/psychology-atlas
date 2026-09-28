"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenText, ChevronDown, GraduationCap, LayoutDashboard, Menu, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { clearTokens, getRefreshToken, hasToken } from "@/lib/auth";

type NavItem = { href: string; label: string };
const atlasGroups: { title: string; items: NavItem[] }[] = [
  { title: "محتوای اطلس", items: [
    { href: "/disorders", label: "اختلالات" }, { href: "/concepts", label: "مفاهیم" },
    { href: "/therapies", label: "درمان‌ها" }, { href: "/dsm", label: "مرجع DSM" },
  ] },
  { title: "ارتباط‌ها و تاریخ", items: [
    { href: "/map", label: "نقشه دانش" }, { href: "/psychologists", label: "روان‌شناسان" },
    { href: "/theories", label: "نظریه‌ها" }, { href: "/timeline", label: "خط زمانی" },
    { href: "/compare", label: "مقایسه" }, { href: "/cognitive-distortions", label: "تحریف‌های شناختی" },
  ] },
];
const studyItems: NavItem[] = [
  { href: "/study", label: "مرکز مطالعه" }, { href: "/study/plans", label: "برنامه‌ها" },
  { href: "/flashcards", label: "فلش‌کارت‌ها" }, { href: "/quizzes", label: "آزمون‌ها" },
  { href: "/cases", label: "کیس‌های بالینی" },
];
const personalItems: NavItem[] = [
  { href: "/dashboard", label: "داشبورد" }, { href: "/saved", label: "ذخیره‌شده‌ها" },
  { href: "/notes", label: "یادداشت‌ها" }, { href: "/case-analytics", label: "تحلیل کیس‌ها" },
];
const allItems = [...atlasGroups.flatMap(group => group.items), ...studyItems, ...personalItems];
function active(path: string, href: string) {
  return path === href || path.startsWith(`${href}/`) || (href === "/therapies" && path.startsWith("/techniques/"));
}
function NavList({ items, pathname }: { items: NavItem[]; pathname: string }) {
  return <>{items.map(item => <Link key={item.href} href={item.href} aria-current={active(pathname, item.href) ? "page" : undefined} className={active(pathname, item.href) ? "active" : ""}>{item.label}</Link>)}</>;
}

export default function Nav() {
  const pathname = usePathname();
  const [loggedIn, setLoggedIn] = useState(false);
  const atlasRef = useRef<HTMLDetailsElement>(null);
  const mobileRef = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const sync = () => setLoggedIn(hasToken());
    sync();
    window.addEventListener("auth-change", sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener("auth-change", sync); window.removeEventListener("storage", sync); };
  }, []);
  useEffect(() => {
    [atlasRef, mobileRef].forEach(ref => { if (ref.current) ref.current.open = false; });
  }, [pathname]);

  const current = [...allItems].sort((a, b) => b.href.length - a.href.length).find(item => active(pathname, item.href));
  const inAtlas = atlasGroups.some(group => group.items.some(item => active(pathname, item.href)));
  const inStudy = studyItems.some(item => active(pathname, item.href));
  const inPersonal = personalItems.some(item => active(pathname, item.href));
  const related = inAtlas ? atlasGroups.flatMap(group => group.items) : inStudy ? studyItems : inPersonal ? personalItems : [];
  async function signOut() {
    const refresh = getRefreshToken();
    try {
      if (refresh) await api<void>("/auth/logout/", { method: "POST", body: JSON.stringify({ refresh }) }, true);
    } catch {
      // Expired server credentials must not keep the local session visible.
    } finally {
      clearTokens();
      location.href = "/";
    }
  }

  return <header className="nav site-nav">
    <a className="skip-link" href="#main-content">رفتن به محتوای اصلی</a>
    <div className="shell site-nav-main">
      <Link href="/" className="brand site-brand" aria-label="اطلس روان‌شناسی، خانه"><span className="site-brand-symbol" aria-hidden="true">✳</span><span>اطلس <em>روان‌شناسی</em></span></Link>
      <nav className="site-primary" aria-label="ناوبری اصلی">
        <Link href="/" className={pathname === "/" ? "active" : ""} aria-current={pathname === "/" ? "page" : undefined}>خانه</Link>
        <details ref={atlasRef} className={`site-menu ${inAtlas ? "active" : ""}`}>
          <summary>اطلس <ChevronDown size={14} aria-hidden="true" /></summary>
          <div className="site-menu-panel site-atlas-menu">{atlasGroups.map(group => <div key={group.title}><span className="site-menu-label">{group.title}</span><NavList items={group.items} pathname={pathname} /></div>)}</div>
        </details>
        <Link href="/study" className={inStudy ? "active" : ""} aria-current={pathname === "/study" ? "page" : undefined}>مطالعه</Link>
        <Link href="/dashboard" className={inPersonal ? "active" : ""} aria-current={pathname === "/dashboard" ? "page" : undefined}>فضای من</Link>
      </nav>
      <Link href="/search" className="site-search-link" aria-label="جست‌وجو در اطلس"><Search size={17} aria-hidden="true" /><span>جست‌وجو در اطلس</span></Link>
      <div className="site-nav-actions">
        {loggedIn ? <button className="button ghost" type="button" onClick={signOut}>خروج</button> : <Link className="button" href="/login">ورود</Link>}
      </div>
      <details ref={mobileRef} className="site-mobile-menu">
        <summary aria-label="باز کردن فهرست بخش‌ها"><Menu size={23} aria-hidden="true" /></summary>
        <nav className="site-mobile-panel" aria-label="ناوبری موبایل">
          <div className="site-mobile-quick"><Link href="/">خانه</Link><Link href="/search">جست‌وجو</Link><Link href="/study">مطالعه</Link><Link href="/dashboard">فضای من</Link></div>
          {atlasGroups.map(group => <section key={group.title}><h2>{group.title}</h2><NavList items={group.items} pathname={pathname} /></section>)}
          <section><h2>یادگیری و تمرین</h2><NavList items={studyItems} pathname={pathname} /></section>
          <section><h2>کتابخانهٔ من</h2><NavList items={personalItems} pathname={pathname} /></section>
          <section><h2>حساب کاربری</h2>{loggedIn ? <button className="site-mobile-signout" type="button" onClick={signOut}>خروج از حساب</button> : <Link href="/login">ورود به حساب</Link>}</section>
        </nav>
      </details>
    </div>
    <div className="site-subnav"><div className="shell site-subnav-inner">
      <div className="site-location"><span>{inAtlas ? <BookOpenText size={15} /> : inStudy ? <GraduationCap size={15} /> : <LayoutDashboard size={15} />}</span><span>{inAtlas ? "اطلس" : inStudy ? "مطالعه" : inPersonal ? "فضای من" : "خانه"}</span>{current && <><span aria-hidden="true">/</span><strong>{current.label}</strong></>}</div>
      {related.length > 0 && <nav className="site-related" aria-label="بخش‌های مرتبط"><NavList items={related} pathname={pathname} /></nav>}
    </div></div>
  </header>;
}
