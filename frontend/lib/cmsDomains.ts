import { cms, CmsError, CmsRecord, CmsRevision } from './cms';

export type DomainValue = string | number | boolean | null | DomainValue[] | { [key: string]: DomainValue };
export type DomainPayload = Record<string, DomainValue>;
export type DomainField = {
  name: string; label?: string; type: string; required: boolean; choices?: { value: string; label: string }[];
  max_length?: number | null; related_kind?: string | null; create_only?: boolean; readonly_reason?: string;
  allow_null?: boolean; allow_blank?: boolean;
  structure?: {root: 'array' | 'object' | 'number-or-object'; max_items: number; max_depth: number; max_nodes: number; max_text_length: number; max_bytes: number; value_types: string[]};
};
export type DomainSchema = { kind: string; domain: string; label: string; fields: DomainField[]; evidence_fields?: string[] };
export type DomainRecord = Omit<CmsRecord, 'payload'> & { payload: DomainPayload; field_values?: DomainPayload; domain?: string; intent?: 'edit' | 'archive'; immutable_fields?: DomainPayload };
export type DomainRevision = Omit<CmsRevision, 'payload'> & { payload: DomainPayload; intent?: 'edit' | 'archive' };
export type DomainOption = { id: number; label: string; version: string | number };
export type ContentCheckResult = { record: DomainRecord; valid: true; publication_available: false; blockers: string[]; preview?: {kind: string; domain: string; candidate: DomainPayload; publication_available: false} };
export type DsmCorpus = { id: number; title: string; version_name: string; source_sha256: string };
export type DsmTreeRow = { id: number; master_id: string; name_en: string; name_fa: string; parent_id: number | null; linked_disorder_id: number | null; display_type: string; children_count: number };
export type DsmCompareRow = { master_id: string; status: 'added' | 'removed' | 'changed' | 'unchanged'; changed_fields: string[]; left_id: number | null; right_id: number | null; name_en: string; name_fa: string };
export type DsmGraph = {corpus: DsmCorpus; focus_id: number; scope: 'same_corpus_neighborhood'; truncated: boolean; nodes: Omit<DsmTreeRow, 'children_count'>[]; edges: {source_id: number; target_id: number; relationship_type: string}[]; notice: string; publication_available: false};
export type DsmStudy = {record_id: number; corpus_id: number; master_id: string; name_en: string; name_fa: string; summary: string; sections: {key: string; value: DomainValue}[]; notice: string; publication_available: false};
export type DuplicateTier = 'identity_conflict' | 'probable_duplicate' | 'lexical_only';
export type DuplicateEvidence = {type: 'identity' | 'name' | 'alias' | 'token'; field?: string; fields?: string[]; value?: string; values?: string[]; similarity?: number};
export type DuplicateCandidate = {id: number; state_id: string | null; label: string; tier: DuplicateTier; score: number; evidence: DuplicateEvidence[]; is_active: boolean; identity: {field: string; value: string | null}};
export type DuplicateResult = {kind: string; domain: string; state_id: string; canonical_pk: number | null; subject: {label: string; identity: {field: string; value: string | null}} | null; candidates: DuplicateCandidate[]; count: number; truncated: boolean; tiers: Record<DuplicateTier, number>; merge_available: false; canonical_write: 0; reason?: string; notice: string};
export type ArchiveRelation = {model: string; field: string; label: string; count: number; on_delete: string; impact: string; domain: string};
export type ArchiveImpact = {kind: string; domain: string; state_id: string; canonical_pk: number | null; relations: ArchiveRelation[]; totals: {relations: number; checked_relations: number; rows: number; by_impact: Record<string, number>}; impact_digest: string; content_state?: {version: number; publication: string; revision_status: string | null; intent: string | null; legacy_origin: boolean; revisions: number}; canonical_write: 0; raw_archive_changed: false; search_graph: string; reason?: string; notice: string};
export const duplicateTierLabels: Record<DuplicateTier, string> = {identity_conflict: 'تعارض هویت', probable_duplicate: 'تکرار احتمالی', lexical_only: 'فقط شباهت متنی'};
export const duplicateKinds = new Set(['category', 'disorder', 'symptom', 'concept', 'dsm-corpus', 'dsm-record']);
export const impactLabels: Record<string, string> = {cascade: 'وابستگی حذف‌شونده', protect: 'وابستگی محافظت‌شده', detach: 'قطع پیوند', link: 'پیوند', orphan_risk: 'ریسک یتیم‌ماندن', other: 'سایر'};

export function fieldWritable(field: DomainField, creating: boolean) {
  return field.type !== 'readonly' && (field.create_only ? creating : !field.readonly_reason);
}
export function draftPayload(schema: Pick<DomainSchema, 'fields'>, form: DomainPayload, creating: boolean) {
  return Object.fromEntries(schema.fields.filter(field => fieldWritable(field, creating) && field.name in form).map(field => [field.name, form[field.name]]));
}
export function recordFields(record: Pick<DomainRecord, 'payload' | 'field_values'>) {
  return record.field_values ?? record.payload;
}
export function revisionPatch(schema: DomainSchema, previous: DomainPayload, form: DomainPayload) {
  return Object.fromEntries(Object.entries(draftPayload(schema, form, false)).filter(([name, value]) => JSON.stringify(value) !== JSON.stringify(previous[name])));
}
export function rebaseChoices(schema: DomainSchema, previous: DomainPayload, mine: DomainPayload, current: DomainPayload) {
  const choices: Record<string, 'mine' | 'current'> = {};
  for (const field of schema.fields.filter(field => fieldWritable(field, false))) {
    const name = field.name, oldValue = JSON.stringify(previous[name]), myValue = JSON.stringify(mine[name]), currentValue = JSON.stringify(current[name]);
    if (myValue === oldValue) choices[name] = 'current';
    else if (currentValue === oldValue || myValue === currentValue) choices[name] = 'mine';
  }
  return choices;
}
export function domainTitle(payload: DomainPayload) {
  for (const name of ['name_fa', 'name_en', 'title_fa', 'title_en', 'title', 'text', 'master_id', 'key']) if (typeof payload[name] === 'string' && payload[name]) return String(payload[name]);
  return 'پیشنهاد پیوند یا محتوای بدون نام';
}
export function domainHeaders(etag: string | null | undefined) {
  if (!etag || !/^"[^"\r\n]+"$/.test(etag)) throw new CmsError(428, 'PRECONDITION_REQUIRED', 'نسخهٔ معتبر سرور موجود نیست؛ ابتدا نسخهٔ سرور را دریافت کنید.');
  return { 'If-Match': etag };
}
export function domainWriteBlocked(error: unknown) {
  const failure = error as { status?: number; code?: string } | undefined;
  return failure?.code === 'UNKNOWN_OUTCOME' || failure?.status === 409 || failure?.status === 412 || (failure?.status ?? 0) >= 500;
}
export function contentPath(kind: string, id?: string) {
  return `/content/${encodeURIComponent(kind)}/${id ? `${encodeURIComponent(id)}/` : ''}`;
}
export async function domainAction<T>(kind: string, id: string, action: 'validate' | 'preview' | 'archive', etag: string | null | undefined, userId: number) {
  return cms<T>(`${contentPath(kind, id)}${action}/`, { method: 'POST', headers: domainHeaders(etag), body: '{}' }, userId);
}
