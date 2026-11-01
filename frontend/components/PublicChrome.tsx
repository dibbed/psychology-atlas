"use client";
import { usePathname } from "next/navigation";
export default function PublicChrome({ children }: { children: React.ReactNode }) {
  return usePathname().startsWith("/admin-console") ? null : children;
}
