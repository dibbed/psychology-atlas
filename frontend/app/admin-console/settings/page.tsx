"use client";
import {useEffect,useState} from "react";
import {cms,CmsError} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type ReviewPolicySnapshot={
  scope:"core";mode:"solo_owner"|"two_person";version:number;
  history:{count:number;page:number;page_size:number;results:unknown[]};
};
const modeName:Record<ReviewPolicySnapshot["mode"],string>={
  solo_owner:"بازبینی با مسئولیت مالک",two_person:"الزام مشارکت دو نفر"
};
export default function SettingsCatalog(){
  const {can}=useCms();
  const allowed=can("cms_owner");
  const [snapshot,setSnapshot]=useState<ReviewPolicySnapshot>();
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(false);
  const [reload,setReload]=useState(0);
  useEffect(()=>{
    if(!allowed)return;
    let active=true;setLoading(true);setError("");setSnapshot(undefined);
    void cms<ReviewPolicySnapshot>("/reviews/policy/?page=1")
      .then(result=>{if(active)setSnapshot(result.data);})
      .catch(e=>{if(active)setError(e instanceof CmsError?e.message:"تنظیم واقعی دریافت نشد.");})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[allowed,reload]);
  if(!allowed)return <CmsState empty="کاتالوگ تنظیمات مدیریت فقط برای مالک CMS قابل‌مشاهده است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title"><p className="eyebrow">P19 | Actual Settings Catalog</p>
      <h1>تنظیمات دارای مصرف‌کنندهٔ واقعی</h1>
      <p className="muted">در این کاتالوگ فقط تنظیم‌هایی نمایش داده می‌شوند که مدل ذخیره‌سازی، مصرف‌کننده و مسیر کنترل‌شدهٔ واقعی دارند. کلید دلخواه، تغییر مستقیم SQL یا مقدار پیش‌فرض ساختگی وجود ندارد.</p>
    </div>
    <button type="button" className="button secondary" disabled={loading}
      onClick={()=>setReload(n=>n+1)}>{loading?"در حال دریافت…":"بازخوانی وضعیت واقعی"}</button>
    {error&&<p role="alert">{error}</p>}
    {loading&&!snapshot&&<CmsState loading/>}
    {snapshot&&<section className="card stack" aria-label="تنظیم نسخه‌دار سیاست بازبینی">
      <h2>سیاست بازبینی پیشنهادهای محتوای مرجع</h2>
      <p>حوزهٔ مصرف‌کننده: <strong>Core Review</strong>، مسیر واقعی <code dir="ltr">ReviewPolicy.mode</code></p>
      <p>مقدار ثبت‌شده: <strong>{modeName[snapshot.mode]}</strong></p>
      <p>نسخهٔ فعلی: <strong>{snapshot.version.toLocaleString("fa-IR")}</strong>؛
        تغییرهای ثبت‌شده: {snapshot.history.count.toLocaleString("fa-IR")}</p>
      <p className="muted">این تنظیم واقعاً در بررسی تازگی و تعارض وظایف Review استفاده می‌شود. تغییر سیاست می‌تواند اعتبار تصمیم‌های قبلی را نیازمند بازبینی مجدد کند، اما خودش هیچ محتوایی را منتشر نمی‌کند.</p>
      <a className="button secondary" href="/admin-console/reviews/policy">دیدن تاریخچه و ویرایش کنترل‌شده با MFA</a>
      <p className="muted">ویرایش از مسیر موجود با کنترل نسخه، دلیل معتبر و MFA انجام می‌شود. بازگشت به مقدار قبلی نیز در صورت مجازبودن تنها با ثبت نسخهٔ تازه ممکن است؛ سابقه پاک نمی‌شود. این صفحه امکان اجرای خودکار بازگشت، تأیید علمی یا تغییر حقوق انتشار ندارد.</p>
    </section>}
    <section className="card stack">
      <h2>تنظیمات دیگر</h2>
      <p className="muted">برای سایر حوزه‌ها هنوز تنظیم نسخه‌دار با مصرف‌کننده و اثر Preview و Rollback کامل تأیید نشده است؛ بنابراین تنظیم ساختگی در کاتالوگ نمایش داده نمی‌شود. این وضعیت به معنی آمادگی کامل P19 نیست.</p>
    </section>
  </div>;
}
