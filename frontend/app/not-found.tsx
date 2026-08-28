import Link from "next/link";

export default function NotFound() {
  return (
    <main className="shell page">
      <div className="card error-state">
        <div className="meta">۴۰۴</div>
        <h1>این صفحه پیدا نشد</h1>
        <p>ممکن است آدرس اشتباه باشد یا محتوای موردنظر دیگر در اطلس فعال نباشد.</p>
        <div className="actions" style={{ marginTop: 18 }}>
          <Link className="button primary" href="/disorders">رفتن به اطلس اختلالات</Link>
          <Link className="button" href="/">صفحه اصلی</Link>
        </div>
      </div>
    </main>
  );
}
