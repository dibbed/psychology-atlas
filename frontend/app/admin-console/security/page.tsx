"use client";
import AccountAccess from "@/components/cms/AccountAccess";
import {usePrivateCms} from "@/components/cms/CmsJobsShared";

export default function OwnSecurity(){
  const {me}=usePrivateCms();
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console">خانهٔ مدیریت</a>
    <h1>امنیت حساب من</h1><p>نشست‌ها، کدهای بازیابی و MFA فقط برای حساب فعلی مدیریت می‌شوند.</p>
    <AccountAccess userId={me.user.id}/>
  </div>;
}
