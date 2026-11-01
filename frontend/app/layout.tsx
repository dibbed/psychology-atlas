import type { Metadata } from "next";
import "./globals.css";
import "./redesign.css";
import Nav from "@/components/Nav";
import PublicChrome from "@/components/PublicChrome";

export const metadata: Metadata = {
  title: "اطلس روان‌شناسی",
  description: "پلتفرم تعاملی یادگیری روان‌شناسی برای دانشجویان."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body>
        <PublicChrome><Nav /></PublicChrome>
        <div id="main-content" tabIndex={-1}>{children}</div>
        <PublicChrome><footer className="footer">
          <div className="shell">
            اطلس روان‌شناسی یک پلتفرم آموزشی است و برای تشخیص پزشکی یا درمان طراحی نشده است.
          </div>
        </footer></PublicChrome>
      </body>
    </html>
  );
}
