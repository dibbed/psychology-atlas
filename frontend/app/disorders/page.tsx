import SearchDisorders from "@/components/SearchDisorders";

export default function DisordersPage() {
  return (
    <main className="shell page stack">
      <div>
        <div className="meta">اطلس اختلالات</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>الگوها را بررسی کن، نه فقط تعریف‌های جدا از هم.</h1>
        <p className="section-copy">در داده‌های ساختاریافته نسخه اولیه جست‌وجو کن و صفحه هر اختلال را برای مطالعه نشانه‌ها، ویژگی‌های بالینی، تشخیص افتراقی، ارزیابی و منابع باز کن.</p>
      </div>
      <SearchDisorders />
    </main>
  );
}
