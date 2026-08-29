"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { normalizePersianSearch } from "@/lib/text";
import type { KnowledgeGraphData, KnowledgeGraphEdge, KnowledgeGraphNode } from "@/lib/types";

type MapNeighbor = {
  node: KnowledgeGraphNode;
  edge: KnowledgeGraphEdge;
  direction: "in" | "out";
  key: string;
};

function nodeTypeLabel(type: KnowledgeGraphNode["type"]) {
  if (type === "concept") return "مفهوم";
  if (type === "disorder") return "اختلال";
  return "نشانه";
}

const edgeLabels: Record<string, string> = {
  related: "مرتبط",
  part_of: "جزئی از",
  maintains: "حفظ‌کننده",
  influences: "اثرگذار",
  contrasts: "مقایسه / تفاوت",
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
};

function relationLabel(kind: string) {
  return edgeLabels[kind] || kind.replaceAll("_", " ");
}

export default function KnowledgeMap({ data, initialNodeId }: { data: KnowledgeGraphData; initialNodeId?: string }) {
  const preferred = data.nodes.find(node => node.id === initialNodeId)
    || data.nodes.find(node => node.id === "concept:cognitive-distortions")
    || data.nodes.find(node => node.type === "concept")
    || data.nodes[0];

  const [selectedId, setSelectedId] = useState(preferred?.id || "");
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | "concept" | "disorder" | "symptom">("all");
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
      .filter(node => (type === "all" || node.type === type) && (
        !q || normalizePersianSearch(`${node.label} ${node.name_en} ${node.slug} ${node.group} ${node.summary}`).includes(q)
      ))
      .sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label, "fa"));
  }, [data.nodes, query, type]);

  const topConnected = useMemo(
    () => [...data.nodes].sort((a, b) => b.degree - a.degree).slice(0, 6),
    [data.nodes]
  );

  const neighborTypeCounts = useMemo(() => ({
    concept: neighbors.filter(row => row.node.type === "concept").length,
    disorder: neighbors.filter(row => row.node.type === "disorder").length,
    symptom: neighbors.filter(row => row.node.type === "symptom").length,
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
      </section>

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
            {(["all", "concept", "disorder", "symptom"] as const).map(value => (
              <button className={`chip ${type === value ? "active" : ""}`} onClick={() => setType(value)} key={value}>
                {value === "all" ? "همه" : nodeTypeLabel(value)}
              </button>
            ))}
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
