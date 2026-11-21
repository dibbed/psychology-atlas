"use client";

import { SourceImpact as Impact, SourceMapping, SourceUsage } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";
import { sourceValue } from "./SourceComparison";

export function sourceUsages(impact: Impact): SourceUsage[] {
  return [...impact.canonical, ...impact.review, ...impact.archives].filter(row => !!row.key);
}

export default function SourceImpact({ impact, mapping, onMapping, targets = [], disabled }: {
  impact: Impact; mapping?: SourceMapping[]; onMapping?: (value: SourceMapping[]) => void;
  targets?: { id: number; title: string }[]; disabled?: boolean;
}) {
  const groups = [["canonical", "مصرف‌کنندگان اصلی"], ["review", "شواهد و تصمیم‌های بررسی"], ["archives", "مراجع تاریخی و آرشیو"], ["successors", "جانشینی‌ها"]] as const;
  const update = (key: string, choice: string) => {
    if (!onMapping) return;
    const retained = (mapping || []).filter(item => item.key !== key);
    onMapping(choice === "" ? retained : [...retained, choice === "retain" ? { key, action: "retain" } : { key, action: "move", target_id: Number(choice) }]);
  };
  return <section className="stack" aria-label="اثر تغییر منبع و وابستگی‌ها">
    <h2>مصرف‌کنندگان و حفاظت‌ها</h2>
    {impact.protection.length > 0 && <div className="cms-notice stack"><h3>حفاظت فعال؛ تغییر مستقیم مجاز نیست</h3><ul>{impact.protection.map((item, index) => <li key={index} dir="auto">{sourceValue(item)}</li>)}</ul><p>برای اصلاح یا پس‌گرفتن منبع محافظت‌شده، جانشین ثبت کنید؛ ادعا باید در دامنهٔ خودش بازبینی شود.</p></div>}
    {groups.map(([key, title]) => {
      if (key === "successors") return <section className="card stack" key={key}><h3>{title}</h3><p>تعداد دقیق در سرور: {faNumber(impact.counts.successors)} · نمایش: {faNumber(impact.successors.length)} · نمایش‌داده‌نشده: {faNumber(Math.max(0, impact.counts.successors - impact.successors.length))}</p>{impact.successors.map(row => <p key={row.id}>منبع <a className="cms-link" href={`/admin-console/sources/${row.source_id}`}>{faNumber(row.source_id)}</a> ← جانشین <a className="cms-link" href={`/admin-console/sources/${row.successor_id}`}>{faNumber(row.successor_id)}</a> · <a className="cms-link" href={`/admin-console/sources/plans/${row.plan_id}`}>طرح جانشینی</a></p>)}</section>;
      const rows = impact[key]; const total = impact.counts[key]; const omitted = Math.max(0, total - rows.length);
      return <section className="card stack" key={key}><h3>{title}</h3>
        <p role="status">تعداد دقیق در سرور: {faNumber(total)} · نمایش: {faNumber(rows.length)} · نمایش‌داده‌نشده: {faNumber(omitted)}</p>
        {omitted > 0 && <p className="cms-notice">این نمای اثر کامل نیست؛ اعمال نگاشت تا دریافت همهٔ مصرف‌کنندگان مسدود است.</p>}
        {rows.length > 0 && <div className="cms-table-wrap" tabIndex={0} role="region" aria-label={`${title}؛ قابل پیمایش افقی`}><table className="cms-table"><thead><tr><th scope="col">مرجع</th><th scope="col">مالک / شاهد / locator</th><th scope="col">حفاظت و قابلیت انتقال</th>{onMapping && <th scope="col">نگاشت صریح</th>}</tr></thead>
          <tbody>{rows.map((row, index) => { const choice = mapping?.find(item => item.key === row.key); return <tr key={row.key || index}>
            <th scope="row"><bdi>{row.model} · {row.id}</bdi><p className="cms-id"><bdi>{row.key || row.path}</bdi></p></th>
            <td>{row.owners?.map((owner, n) => <p key={n}><bdi>{owner.model} · {owner.id} · {owner.review_status || "بدون وضعیت بررسی"}</bdi></p>)}{row.locator && <p dir="auto">نشانی شاهد: {row.locator}</p>}{row.fields?.length ? <p>فیلدها: <bdi>{row.fields.join("، ")}</bdi></p> : null}{row.evidence?.map((evidence, n) => <p key={n} dir="auto">شاهد: {evidence.locator} · فیلدها: {evidence.fields.join("، ")}</p>)}{row.paths?.map((path, n) => <p className="cms-id" key={n}><bdi>{path}</bdi></p>)}{row.claim && <p className="cms-prose" dir="auto">{sourceValue(row.claim)}</p>}</td>
            <td>{row.protected ? "محافظت‌شده" : row.mutable ? "انتقال فقط با اعتبارسنجی سرور" : "تاریخی؛ فقط حفظ / رسیدگی دستی"}</td>
            {onMapping && <td><label>نگاشت <bdi>{row.key}</bdi><select value={choice?.action === "retain" ? "retain" : choice?.target_id || ""} disabled={disabled || !row.key || omitted > 0} onChange={event => update(row.key, event.target.value)}><option value="">انتخاب صریح لازم است</option><option value="retain">حفظ مرجع فعلی / رسیدگی دستی</option>{row.mutable && !row.protected && targets.map(target => <option key={target.id} value={target.id}>انتقال به {target.title} ({target.id})</option>)}</select></label></td>}
          </tr>; })}</tbody></table></div>}
      </section>;
    })}
  </section>;
}
