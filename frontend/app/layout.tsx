import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "اطلس روان‌شناسی",
  description: "پلتفرم تعاملی یادگیری روان‌شناسی برای دانشجویان."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body>
        <Nav />
        {children}
        <footer className="footer">
          <div className="shell">
            اطلس روان‌شناسی یک پلتفرم آموزشی است و برای تشخیص پزشکی یا درمان طراحی نشده است.
          </div>
        </footer>
      </body>
    </html>
  );
}
