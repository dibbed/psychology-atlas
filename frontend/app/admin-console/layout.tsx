import CmsShell from "@/components/cms/CmsShell";
import "./cms.css";
export const metadata = { title: "کنسول مدیریت | اطلس روان‌شناسی" };
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <CmsShell>{children}</CmsShell>;
}
