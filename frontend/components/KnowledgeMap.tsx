"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { normalizePersianSearch } from "@/lib/text";
import type { KnowledgeGraphData, KnowledgeGraphEdge, KnowledgeGraphNode } from "@/lib/types";
import GraphPathFinder from "./GraphPathFinder";
import { ReviewStatus, SourceVerificationSummary } from "./ScientificMeta";

type MapNeighbor = {
  node: KnowledgeGraphNode;
  edge: KnowledgeGraphEdge;
  direction: "in" | "out";
  key: string;
};

function nodeTypeLabel(type: KnowledgeGraphNode["type"]) {
  if (type === "concept") return "مفهوم";
  if (type === "disorder") return "اختلال";
  if (type === "symptom") return "نشانه";
  if (type === "therapy") return "درمان";
  if (type === "technique") return "تکنیک";
  if (type === "psychologist") return "روان‌شناس";
  if (type === "theory") return "نظریه";
  return "رویداد تاریخی";
}

const edgeLabels: Record<string, string> = {
  related: "مرتبط",
  part_of: "جزئی از",
  subtype_of: "زیرنوع",
  prerequisite: "پیش‌نیاز",
  maintains: "حفظ‌کننده",
  mechanism: "سازوکار",
  influences: "اثرگذار",
  contrasts: "مقایسه / تفاوت",
  commonly_confused_with: "اغلب اشتباه می‌شود با",
  associated_with: "همراه / مرتبط با",
  applied_in: "کاربرد",
  core: "مفهوم محوری",
  associated: "مفهوم مرتبط",
  maintaining: "عامل حفظ‌کننده",
  assessment: "ارزیابی",
  treatment: "درمان / مداخله",
  differential: "افتراقی",
  symptom_core: "نشانه محوری",
  symptom_common: "نشانه رایج",
  symptom_possible: "نشانه ممکن",
  symptom_contextual: "نشانه زمینه‌ای",
  dsm_nearby: "عنوان نزدیک در DSM MASTER",
  concept_symptom_associated: "ارتباط مفهوم با نشانه",
  concept_symptom_manifestation: "بازنمایی مفهوم در لایه نشانه",
  concept_symptom_overlaps_with: "همپوشانی مفهوم و نشانه",
  concept_symptom_contrasts: "تفاوت مفهوم و نشانه",
  therapy_disorder_guideline_recommended: "درمان ↔ اختلال · توصیه راهنما",
  therapy_disorder_commonly_used: "درمان ↔ اختلال · کاربرد رایج",
  therapy_disorder_adjunctive: "درمان ↔ اختلال · کمکی",
  therapy_disorder_alternative: "درمان ↔ اختلال · جایگزین",
  therapy_disorder_context_dependent: "درمان ↔ اختلال · وابسته به زمینه",
  therapy_disorder_not_first_line: "درمان ↔ اختلال · نه خط اول",
  therapy_disorder_research_context: "درمان ↔ اختلال · پژوهشی",
  therapy_concept_targets: "درمان → مفهوم · هدف",
  therapy_concept_uses: "درمان → مفهوم · استفاده",
  therapy_concept_addresses: "درمان → مفهوم · پرداختن",
  therapy_concept_teaches: "درمان → مفهوم · آموزش",
  therapy_concept_mechanism: "درمان → مفهوم · سازوکار",
  therapy_concept_applied_to: "درمان → مفهوم · کاربرد",
  therapy_technique_core: "درمان → تکنیک · محوری",
  therapy_technique_common: "درمان → تکنیک · رایج",
  therapy_technique_optional: "درمان → تکنیک · اختیاری",
  therapy_technique_adapted: "درمان → تکنیک · انطباق‌یافته",
  therapy_technique_component: "درمان → تکنیک · مؤلفه",
  technique_concept_targets: "تکنیک → مفهوم · هدف",
  technique_concept_addresses: "تکنیک → مفهوم · پرداختن",
  technique_concept_teaches: "تکنیک → مفهوم · آموزش",
  technique_concept_mechanism: "تکنیک → مفهوم · سازوکار",
  technique_concept_applied_to: "تکنیک → مفهوم · کاربرد",
};

const v6SemanticLabels: Record<string, string> = {
  originated: "بنیان‌گذاری / صورت‌بندی اولیه",
  proposed: "پیشنهاد کرد",
  co_proposed: "هم‌پیشنهاد کرد",
  developed: "توسعه داد",
  co_developed: "هم‌توسعه داد",
  developed_or_majorly_associated_with: "توسعه / ارتباط تاریخی عمده",
  expanded: "گسترش داد",
  popularized: "رواج داد",
  researched: "پژوهش کرد",
  researched_or_developed: "پژوهش / توسعه",
  applied: "به‌کار برد",
  contributed_to: "مشارکت داشت",
  criticized: "نقد کرد",
  challenged: "به چالش کشید",
  associated_with: "مرتبط با",
  majorly_associated_with: "ارتباط تاریخی عمده",
  collaborated_with: "همکاری کرد",
  influenced: "اثر گذاشت",
  mentored: "راهنمایی / mentorship",
  grounds: "مبنای نظری",
  includes_construct: "شامل سازه",
  informs: "اطلاع‌رسان / جهت‌دهنده",
  supports: "پشتیبانی می‌کند",
  complements: "مکمل",
  challenges: "به چالش می‌کشد",
  challenged_by: "به چالش کشیده‌شده توسط",
  reformulated_as: "بازصورت‌بندی‌شده به",
  supports_interpretation_of: "پشتیبان تفسیر",
  extends: "گسترش می‌دهد",
  refines: "دقیق‌تر می‌کند",
  related: "مرتبط",
  involves_person: "شامل شخص",
  marks_theory_milestone: "نقطه عطف نظریه",
  marks_therapy_milestone: "نقطه عطف درمان",
  marks_technique_evidence_milestone: "نقطه عطف شواهد تکنیک",
  subject: "موضوع",
  author: "نویسنده",
  developer: "توسعه‌دهنده",
  publication: "انتشار",
  institutional: "نهادی",
  context: "زمینه تاریخی",
};

const v6RelationPrefixes: [string, string][] = [
  ["psychologist_theory_", "روان‌شناس → نظریه"],
  ["psychologist_concept_", "روان‌شناس → مفهوم"],
  ["psychologist_therapy_", "روان‌شناس → درمان"],
  ["psychologist_psychologist_", "شخص → شخص"],
  ["theory_concept_", "نظریه → مفهوم"],
  ["theory_therapy_", "نظریه → درمان"],
  ["theory_technique_", "نظریه → تکنیک"],
  ["theory_theory_", "نظریه → نظریه"],
  ["timeline_psychologist_", "رویداد → روان‌شناس"],
  ["timeline_theory_", "رویداد → نظریه"],
  ["timeline_therapy_", "رویداد → درمان"],
  ["timeline_technique_", "رویداد → تکنیک"],
  ["timeline_concept_", "رویداد → مفهوم"],
];

function relationLabel(kind: string) {
  if (edgeLabels[kind]) return edgeLabels[kind];
  for (const [prefix, label] of v6RelationPrefixes) {
    if (!kind.startsWith(prefix)) continue;
    const semantic = kind.slice(prefix.length);
    return `${label} · ${v6SemanticLabels[semantic] || semantic.replaceAll("_", " ")}`;
  }
  return kind.replaceAll("_", " ");
}

export default function KnowledgeMap({ data, initialNodeId }: { data: KnowledgeGraphData; initialNodeId?: string }) {
  const preferred = data.nodes.find(node => node.id === initialNodeId)
    || data.nodes.find(node => node.id === "concept:cognitive-distortions")
    || data.nodes.find(node => node.type === "concept")
    || data.nodes[0];

  const [selectedId, setSelectedId] = useState(preferred?.id || "");
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | "concept" | "disorder" | "symptom" | "therapy" | "technique" | "psychologist" | "theory" | "timeline">("all");
  const [domain, setDomain] = useState("");
  const [subtype, setSubtype] = useState("");
  const [theoryDomain, setTheoryDomain] = useState("");
  const [timelineCategory, setTimelineCategory] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [minDegree, setMinDegree] = useState(0);
  const [edgeKind, setEdgeKind] = useState("all");
  const [history, setHistory] = useState<string[]>(preferred ? [preferred.id] : []);

  const nodeById = useMemo(() => new Map(data.nodes.map(node => [node.id, node])), [data.nodes]);
  const selected = nodeById.get(selectedId) || preferred;

  const neighbors = useMemo<MapNeighbor[]>(() => {
    if (!selected) return [];
    const rows = data.edges.reduce<MapNeighbor[]>((items, edge, index) => {
      if (edge.source === selected.id) {
        const node = nodeById.get(edge.target);
        if (node) items.push({ node, edge, direction: "out", key: `${index}-${node.id}-out` });
      } else if (edge.target === selected.id) {
        const node = nodeById.get(edge.source);
        if (node) items.push({ node, edge, direction: "in", key: `${index}-${node.id}-in` });
      }
      return items;
    }, []);
    return rows.sort((a, b) => b.node.degree - a.node.degree || a.node.label.localeCompare(b.node.label, "fa"));
  }, [data.edges, nodeById, selected]);

  const relationKinds = useMemo(() => {
    const counts = new Map<string, number>();
    neighbors.forEach(row => counts.set(row.edge.kind, (counts.get(row.edge.kind) || 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [neighbors]);

  const visibleNeighbors = useMemo(
    () => edgeKind === "all" ? neighbors : neighbors.filter(row => row.edge.kind === edgeKind),
    [neighbors, edgeKind]
  );

  const filteredNodes = useMemo(() => {
    const q = normalizePersianSearch(query.trim());
    return data.nodes
      .filter(node => {
        if (type !== "all" && node.type !== type) return false;
        if (domain && (node.type !== "concept" || node.domain !== domain)) return false;
        if (subtype && (node.type !== "concept" || node.subtype !== subtype)) return false;
        if (theoryDomain && (node.type !== "theory" || node.domain !== theoryDomain)) return false;
        if (timelineCategory && (node.type !== "timeline" || node.category !== timelineCategory)) return false;
        if (reviewStatus && node.review_status !== reviewStatus) return false;
        if (node.degree < minDegree) return false;
        const haystack = `${node.label} ${node.name_en} ${node.slug} ${node.group} ${node.summary} ${node.role || ""} ${node.nationality || ""} ${node.modern_status || ""} ${node.date_text || ""}`;
        return !q || normalizePersianSearch(haystack).includes(q);
      })
      .sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label, "fa"));
  }, [data.nodes, query, type, domain, subtype, theoryDomain, timelineCategory, reviewStatus, minDegree]);

  const conceptDomains = useMemo(() => {
    const rows = new Map<string, string>();
    data.nodes.filter(node => node.type === "concept" && node.domain).forEach(node => rows.set(node.domain!, node.domain_label || node.domain!));
    return [...rows.entries()].sort((a, b) => a[1].localeCompare(b[1], "fa"));
  }, [data.nodes]);

  const theoryDomains = useMemo(() => {
    const rows = new Set<string>();
    data.nodes.filter(node => node.type === "theory" && node.domain).forEach(node => rows.add(node.domain!));
    return [...rows].sort((a, b) => a.localeCompare(b));
  }, [data.nodes]);

  const timelineCategories = useMemo(() => {
    const rows = new Set<string>();
    data.nodes.filter(node => node.type === "timeline" && node.category).forEach(node => rows.add(node.category!));
    return [...rows].sort((a, b) => a.localeCompare(b));
  }, [data.nodes]);

  const topConnected = useMemo(
    () => [...data.nodes].sort((a, b) => b.degree - a.degree).slice(0, 6),
    [data.nodes]
  );

  const neighborTypeCounts = useMemo(() => ({
    concept: neighbors.filter(row => row.node.type === "concept").length,
    disorder: neighbors.filter(row => row.node.type === "disorder").length,
    symptom: neighbors.filter(row => row.node.type === "symptom").length,
    therapy: neighbors.filter(row => row.node.type === "therapy").length,
    technique: neighbors.filter(row => row.node.type === "technique").length,
    psychologist: neighbors.filter(row => row.node.type === "psychologist").length,
    theory: neighbors.filter(row => row.node.type === "theory").length,
    timeline: neighbors.filter(row => row.node.type === "timeline").length,
  }), [neighbors]);

  function selectNode(id: string) {
    if (!nodeById.has(id)) return;
    setSelectedId(id);
    setEdgeKind("all");
    setHistory(rows => {
      if (rows[rows.length - 1] === id) return rows;
      return [...rows, id].slice(-7);
    });
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("node", id);
      window.history.replaceState({}, "", `${url.pathname}${url.search}`);
    }
  }

  if (!selected) return <div className="card">نقشه هنوز داده‌ای ندارد.</div>;

  return (
    <div className="knowledge-explorer stack">
      <section className="graph-overview" aria-label="آمار شبکه">
        <div><strong>{data.meta.node_count.toLocaleString("fa-IR")}</strong><span>گره</span></div>
        <div><strong>{data.meta.edge_count.toLocaleString("fa-IR")}</strong><span>رابطه</span></div>
        <div><strong>{data.meta.node_types.concept.toLocaleString("fa-IR")}</strong><span>مفهوم</span></div>
        <div><strong>{data.meta.node_types.disorder.toLocaleString("fa-IR")}</strong><span>اختلال</span></div>
        <div><strong>{data.meta.node_types.symptom.toLocaleString("fa-IR")}</strong><span>نشانه</span></div>
        <div><strong>{data.meta.node_types.therapy.toLocaleString("fa-IR")}</strong><span>درمان</span></div>
        <div><strong>{data.meta.node_types.technique.toLocaleString("fa-IR")}</strong><span>تکنیک</span></div>
        <div><strong>{data.meta.node_types.psychologist.toLocaleString("fa-IR")}</strong><span>روان‌شناس</span></div>
        <div><strong>{data.meta.node_types.theory.toLocaleString("fa-IR")}</strong><span>نظریه</span></div>
        <div><strong>{data.meta.node_types.timeline.toLocaleString("fa-IR")}</strong><span>رویداد</span></div>
      </section>

      <GraphPathFinder nodes={data.nodes} initialFrom={selected?.id} />

      <div className="knowledge-map-layout knowledge-map-layout-v2">
        <aside className="card map-browser map-browser-v2">
          <div>
            <div className="meta">مرور گره‌ها</div>
            <h3>از هر نقطه وارد شبکه شو</h3>
          </div>
          <input
            className="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="نام، slug یا توضیح..."
            aria-label="جست‌وجوی گره‌های نقشه"
          />
          <div className="category-chips compact-chips">
            {(["all", "concept", "disorder", "symptom", "therapy", "technique", "psychologist", "theory", "timeline"] as const).map(value => (
              <button
                className={`chip ${type === value ? "active" : ""}`}
                onClick={() => {
                  setType(value);
                  if (value !== "concept") { setDomain(""); setSubtype(""); }
                  if (value !== "theory") setTheoryDomain("");
                  if (value !== "timeline") setTimelineCategory("");
                }}
                key={value}
              >
                {value === "all" ? "همه" : nodeTypeLabel(value)}
              </button>
            ))}
          </div>
          <div className="map-advanced-filters">
            <select className="filter-select" value={domain} onChange={event => { setDomain(event.target.value); if (event.target.value) setType("concept"); }} aria-label="حوزه مفهومی">
              <option value="">همه حوزه‌های Concept</option>
              {conceptDomains.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
            <select className="filter-select" value={subtype} onChange={event => { setSubtype(event.target.value); if (event.target.value) setType("concept"); }} aria-label="زیرنوع Concept">
              <option value="">همه زیرنوع‌ها</option>
              <option value="cognitive_distortion">تحریف شناختی</option>
              <option value="general">مفهوم عمومی</option>
            </select>
            <select className="filter-select" value={theoryDomain} onChange={event => { setTheoryDomain(event.target.value); if (event.target.value) setType("theory"); }} aria-label="دامنه نظریه">
              <option value="">همه domainهای Theory</option>
              {theoryDomains.map(value => <option value={value} key={value}>{value.replaceAll("_", " ")}</option>)}
            </select>
            <select className="filter-select" value={timelineCategory} onChange={event => { setTimelineCategory(event.target.value); if (event.target.value) setType("timeline"); }} aria-label="دسته Timeline">
              <option value="">همه دسته‌های Timeline</option>
              {timelineCategories.map(value => <option value={value} key={value}>{value.replaceAll("_", " ")}</option>)}
            </select>
            <select className="filter-select" value={reviewStatus} onChange={event => setReviewStatus(event.target.value)} aria-label="وضعیت بازبینی علمی گره">
              <option value="">همه وضعیت‌های review</option>
              <option value="source_checked">دارای منبع؛ بازبینی نهایی نشده</option>
              <option value="reviewed">بازبینی علمی ثبت‌شده</option>
              <option value="unreviewed">بازبینی‌نشده</option>
            </select>
            <label className="degree-filter">
              <span>حداقل اتصال: {minDegree.toLocaleString("fa-IR")}</span>
              <input type="range" min="0" max="10" value={minDegree} onChange={event => setMinDegree(Number(event.target.value))} />
            </label>
          </div>
          <div className="map-list-summary">
            <span>{filteredNodes.length.toLocaleString("fa-IR")} نتیجه</span>
            <span>مرتب‌شده بر اساس اتصال</span>
          </div>
          <div className="map-node-list map-node-list-v2">
            {filteredNodes.map(node => (
              <button className={`map-list-node ${selected.id === node.id ? "active" : ""}`} onClick={() => selectNode(node.id)} key={node.id}>
                <div><span>{node.label}</span><small>{node.name_en}</small></div>
                <b>{node.degree.toLocaleString("fa-IR")}</b>
              </button>
            ))}
          </div>
          <div className="map-hotspots">
            <div className="map-list-summary"><strong>گره‌های پراتصال</strong><span>Degree واقعی</span></div>
            {topConnected.map(node => (
              <button onClick={() => selectNode(node.id)} key={node.id}>
                <span>{node.label}</span><b>{node.degree.toLocaleString("fa-IR")}</b>
              </button>
            ))}
          </div>
        </aside>

        <section className="map-workspace stack">
          <div className="graph-path card">
            <span className="meta">مسیر کاوش</span>
            <div>
              {history.map((id, index) => {
                const node = nodeById.get(id);
                if (!node) return null;
                return (
                  <button className={id === selected.id ? "active" : ""} onClick={() => selectNode(id)} key={`${id}-${index}`}>
                    {node.label}
                  </button>
                );
              })}
            </div>
          </div>

          <section className="map-stage card map-stage-v2">
            <div className="map-stage-head map-stage-head-v2">
              <div className="node-heading">
                <span className={`node-type-dot ${selected.type}`} />
                <div>
                  <div className="meta">{nodeTypeLabel(selected.type)} · {selected.group}</div>
                  <h2>{selected.label}</h2>
                  <div className="latin-title">{selected.name_en}</div>
                </div>
              </div>
              <div className="actions">
                {selected.dsm_master_id && <Link className="button" href={`/dsm/${selected.dsm_master_id}`}>DSM MASTER</Link>}
                <Link className="button" href={selected.href}>صفحه کامل</Link>
              </div>
            </div>

            <div className="node-profile-grid">
              <div className={`map-core map-core-v2 ${selected.type}`}>
                <span>{nodeTypeLabel(selected.type)}</span>
                <strong>{selected.label}</strong>
                <small>{selected.slug}</small>
              </div>
              <div className="node-profile-copy">
                <p>{selected.summary || "برای این گره هنوز توضیح کوتاه ثبت نشده است."}</p>
                {(selected.type === "psychologist" || selected.type === "theory" || selected.type === "timeline") && (
                  <div className="v065-node-context">
                    {selected.type === "psychologist" && (selected.birth_year || selected.death_year) && (
                      <span>{selected.birth_year?.toLocaleString("fa-IR") || "؟"} — {selected.death_year?.toLocaleString("fa-IR") || "نامشخص"}</span>
                    )}
                    {selected.type === "psychologist" && selected.nationality && <span>{selected.nationality}</span>}
                    {selected.type === "theory" && selected.period_text && <span>{selected.period_text.replaceAll("_", " ")}</span>}
                    {selected.type === "theory" && selected.modern_status && <span>{selected.modern_status.replaceAll("_", " ")}</span>}
                    {selected.type === "timeline" && <span>{selected.date_text || selected.year_start?.toLocaleString("fa-IR") || "تاریخ نامشخص"}</span>}
                    {selected.type === "timeline" && selected.date_precision && <span>{selected.date_precision.replaceAll("_", " ")}</span>}
                    {selected.review_status && <ReviewStatus status={selected.review_status} compact />}
                  </div>
                )}
                {selected.dsm_master_id && (
                  <div className="map-dsm-context">
                    <span>DSM MASTER · {selected.dsm_master_id}</span>
                    <strong>{selected.dsm_chapter_name_fa || "رکورد رسمی متصل"}</strong>
                    {selected.dsm_chapter_number && <small>فصل {selected.dsm_chapter_number.toLocaleString("fa-IR")}</small>}
                  </div>
                )}
                <div className="node-facts">
                  <div><strong>{selected.degree.toLocaleString("fa-IR")}</strong><span>اتصال مستقیم</span></div>
                  <div><strong>{neighborTypeCounts.concept.toLocaleString("fa-IR")}</strong><span>Concept</span></div>
                  <div><strong>{neighborTypeCounts.disorder.toLocaleString("fa-IR")}</strong><span>Disorder</span></div>
                  <div><strong>{neighborTypeCounts.symptom.toLocaleString("fa-IR")}</strong><span>Symptom</span></div>
                  <div><strong>{neighborTypeCounts.therapy.toLocaleString("fa-IR")}</strong><span>Therapy</span></div>
                  <div><strong>{neighborTypeCounts.technique.toLocaleString("fa-IR")}</strong><span>Technique</span></div>
                  <div><strong>{neighborTypeCounts.psychologist.toLocaleString("fa-IR")}</strong><span>Psychologist</span></div>
                  <div><strong>{neighborTypeCounts.theory.toLocaleString("fa-IR")}</strong><span>Theory</span></div>
                  <div><strong>{neighborTypeCounts.timeline.toLocaleString("fa-IR")}</strong><span>Timeline</span></div>
                </div>
              </div>
            </div>

            <div className="relation-toolbar">
              <div><strong>رابطه‌های مستقیم</strong><span>{visibleNeighbors.length.toLocaleString("fa-IR")} مورد نمایش داده می‌شود</span></div>
              <div className="relation-filter-row">
                <button className={`chip ${edgeKind === "all" ? "active" : ""}`} onClick={() => setEdgeKind("all")}>همه {neighbors.length.toLocaleString("fa-IR")}</button>
                {relationKinds.map(([kind, count]) => (
                  <button className={`chip ${edgeKind === kind ? "active" : ""}`} onClick={() => setEdgeKind(kind)} key={kind}>
                    {relationLabel(kind)} {count.toLocaleString("fa-IR")}
                  </button>
                ))}
              </div>
            </div>

            <div className="map-neighbors map-neighbors-v2">
              {visibleNeighbors.map(({ node, edge, direction, key }) => (
                <button className={`map-neighbor map-neighbor-v2 ${node.type}`} onClick={() => selectNode(node.id)} key={key}>
                  <div className="neighbor-topline">
                    <span className="edge-label">{direction === "in" ? "ورودی" : "خروجی"} · {relationLabel(edge.kind)}</span>
                    <b>{node.degree.toLocaleString("fa-IR")}</b>
                  </div>
                  <strong>{node.label}</strong>
                  <small>{nodeTypeLabel(node.type)} · {node.group}</small>
                  {edge.explanation && <p>{edge.explanation}</p>}
                  {!!edge.sources?.length && (
                    <div className="map-edge-source-stack">
                      <small className="map-edge-sources">منبع: {edge.sources.map(source => source.organization || source.title).join(" · ")}</small>
                      <SourceVerificationSummary sources={edge.sources} />
                    </div>
                  )}
                </button>
              ))}
              {!visibleNeighbors.length && <div className="empty-relation">برای این فیلتر رابطه‌ای ثبت نشده است.</div>}
            </div>
          </section>
        </section>
      </div>
    </div>
  );
}
