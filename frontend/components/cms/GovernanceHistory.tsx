"use client";

import { CmsPage, cmsDate } from "@/lib/cms";
import { GovernancePagination } from "./GovernanceForms";
import { CmsState } from "./CmsShell";
import { faNumber } from "@/lib/fa";
import { governanceLabels } from "@/lib/cmsGovernance";

export type GovernanceEvent = {
  revision: number; version: number; created_at: string; action: string; status: string; actor_ref: string; assignee_ref: string; reason: string;
  payload: Record<string, unknown>; payload_digest: string; resource_digest: string; dependency_digest: string; policy_version: number; policy_mode: string;
  decisions: { id: number; outcome: string; reason: string; self_review: boolean; actor_ref: string; assignee_ref: string; revision_hash: string; dependency_digest: string; supersedes: number | null }[];
};
const actions: Record<string, string> = { create: "ثبت پیشنهاد", update: "اصلاح پیشنهاد", assign: "تخصیص بازبین", decide: "تصمیم بررسی", revoke: "لغو حقوق", reopen: "بازگشایی" };

export default function GovernanceHistory({ data, error, retry, onPage, children }: {
  data?: CmsPage<GovernanceEvent>; error?: unknown; retry: () => void; onPage: (page: number) => void;
  children?: (event: GovernanceEvent) => React.ReactNode;
}) {
  if (error) return <CmsState error={error} retry={retry} />;
  if (!data) return <CmsState loading />;
  return <section className="card stack"><h2>تاریخچهٔ ثبت‌شده در سرور</h2>
    {!data.results.length && <CmsState empty="هنوز تصمیم یا عملیاتی ثبت نشده است." />}
    {data.results.map(event => <article className="cms-history-entry stack" key={event.revision}>
      <h3>{actions[event.action] || event.action} · نسخهٔ {faNumber(event.version)}</h3>
      <p><time dateTime={event.created_at}>{cmsDate(event.created_at)}</time> · <bdi>{event.actor_ref}</bdi></p>
      <p className="cms-prose" dir="auto">دلیل: {governanceLabels[event.reason] || event.reason || "ثبت نشده"}</p>
      <p>سیاست نسخهٔ {faNumber(event.policy_version)} · {event.policy_mode === "two_person" ? "دو نفره" : "مالک تنها"} · بازبین: <bdi>{event.assignee_ref || "تخصیص داده نشده"}</bdi></p>
      {event.decisions.map(decision => <div className="cms-notice stack" key={decision.id}><p>نتیجه: <bdi>{({ approve: "تأیید", reject: "نیازمند اصلاح", assigned: "تخصیص", revoked: "لغوشده", reopened: "بازگشایی" } as Record<string, string>)[decision.outcome] || decision.outcome}</bdi> · دلیل: <bdi>{governanceLabels[decision.reason] || decision.reason}</bdi></p><p>خودبازبینی پذیرفته‌شده: {decision.self_review ? "بله" : "خیر"} · تصمیم قبلی: {decision.supersedes == null ? "ندارد" : faNumber(decision.supersedes)}</p><p className="cms-id">اثر نسخهٔ تصمیم: <bdi>{decision.revision_hash}</bdi> · اثر شواهد: <bdi>{decision.dependency_digest}</bdi></p></div>)}
      {children?.(event)}
    </article>)}
    <GovernancePagination data={data} onPage={onPage} />
  </section>;
}
