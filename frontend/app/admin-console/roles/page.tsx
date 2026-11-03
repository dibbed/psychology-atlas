"use client";
import RoleGroups from "@/components/cms/RoleGroups";
import {CmsState} from "@/components/cms/CmsShell";
import {usePrivateCms} from "@/components/cms/CmsJobsShared";

export default function Roles(){
  const {can}=usePrivateCms();
  if(!can("cms_roles_view"))return <CmsState empty="برای مدیریت گروه‌های نقش، مجوز مستقل نقش‌ها لازم است."/>;
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console">خانهٔ مدیریت</a>
    <h1>نقش‌ها و دسترسی</h1><RoleGroups/>
    {can("cms_user_view")&&<a className="cms-link" href="/admin-console/accounts">عضویت گروه و دسترسی مستقیم حساب‌ها</a>}
  </div>;
}
