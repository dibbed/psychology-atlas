"use client";
import { useState } from "react";
import { cms, CmsError } from "@/lib/cms";
import { DomainValue } from "@/lib/cmsDomains";
import { CmsState, useCms } from "@/components/cms/CmsShell";
import { DomainValueView, ReferenceSelector } from "@/components/cms/DomainFields";

type PublicTherapy = Record<string, DomainValue>;
type CompareResponse = {items: PublicTherapy[]; scope: string; publication_available: false; note: string};
const fields = [
  ["name_fa", "نام فارسی"], ["name_en", "نام انگلیسی"], ["summary", "خلاصه"],
  ["academic_definition", "تعریف علمی"], ["core_principles", "اصول"],
  ["typical_structure", "ساختار معمول"], ["appropriate_contexts", "زمینه‌ها"],
  ["limitations", "محدودیت‌ها"], ["safety_notes", "نکات ایمنی"],
  ["evidence_note", "توضیح شواهد"], ["disorder_links", "روابط اختلال و نقش بالینی"],
  ["technique_links", "روابط تکنیک‌ها"], ["concept_links", "روابط مفاهیم"],
  ["source_links", "منابع"]
] as const;

export default function TherapyPublicComparePreview() {
  const {can} = useCms();
  const [left, setLeft] = useState<number | null>(null);
  const [right, setRight] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>();
  const [comparison, setComparison] = useState<CompareResponse>();
  const allowed = can("cms_therapy_view") && can("cms_therapy_preview");
  async function compare() {
    if (!allowed || !left || !right || left === right || loading) return;
    setComparison(undefined); setError(undefined); setLoading(true);
    try {
      const {data} = await cms<CompareResponse>(`/content/therapy/public-compare-preview/?${new URLSearchParams({left:String(left),right:String(right)})}`);
      setComparison(data);
    } catch (e) {setError(e);} finally {setLoading(false);}
  }
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")}/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console/content">→ محتوای مرجع</a>
    <h1>مقایسهٔ واقعی درمان‌های منتشرشده</h1>
    <p className="cms-notice">این نمای مدیریت از همان projection و محدودیت‌های API عمومی استفاده می‌کند. پیش‌نویس‌ها و reviewهای P08 هرگز در این جدول به‌عنوان محتوای منتشرشده ظاهر نمی‌شوند. مقایسه، رتبه‌بندی اثربخشی یا تجویز درمان نیست.</p>
    <section className="card stack">
      <ReferenceSelector kind="therapy" label="درمان سمت راست" value={right} onChange={value=>{setRight(value);setComparison(undefined);}}/>
      <ReferenceSelector kind="therapy" label="درمان سمت چپ" value={left} onChange={value=>{setLeft(value);setComparison(undefined);}}/>
      <button className="button primary" disabled={!left || !right || left===right || loading} onClick={()=>void compare()}>مقایسهٔ projection عمومی</button>
      {left && right && left===right && <p role="alert">دو درمان متفاوت را انتخاب کنید.</p>}
      {error != null && <CmsState error={error} retry={()=>void compare()}/>}
      {loading && <CmsState loading/>}
      {comparison && <p className="cms-notice" role="status">{comparison.note} هیچ publication یا write انجام نشد.</p>}
    </section>
    {comparison && <div className="cms-table-wrap" role="region" aria-label="مقایسهٔ دو رویکرد درمانی" tabIndex={0}>
      <table className="cms-table"><caption>نمای فقط خواندنی نسخهٔ canonical و عمومی</caption>
        <thead><tr><th scope="col">فیلد</th>{comparison.items.map((item,index)=><th scope="col" key={index}><bdi>{String(item.name_fa || item.name_en || index+1)}</bdi></th>)}</tr></thead>
        <tbody>{fields.map(([key,label])=><tr key={key}><th scope="row">{label}</th>{comparison.items.map((item,i)=><td key={i}><DomainValueView value={item[key]}/></td>)}</tr>)}</tbody>
      </table>
    </div>}
    <p className="muted">برای بررسی تفاوت proposal با canonical، از تب پیش‌نمایش رکورد درمان استفاده کنید. فعال‌سازی عمومی فقط در P16 مجاز خواهد بود.</p>
  </div>;
}
