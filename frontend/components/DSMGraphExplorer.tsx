"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { normalizePersianSearch } from "@/lib/text";
import type { DSMGraphData, DSMGraphNode } from "@/lib/types";
import { dsmTypeLabel } from "@/lib/dsm";

type DSMGraphNeighbor = {
  node: DSMGraphNode;
  edge: DSMGraphData["edges"][number];
  direction: "in" | "out";
  key: string;
};

const edgeLabels = {
  hierarchy: "ساختار",
  nearby: "عنوان نزدیک",
  differential: "افتراق لینک‌شده",
} as const;

export default function DSMGraphExplorer({ data, initialNodeId }: { data: DSMGraphData; initialNodeId?: string }) {
  const preferred = data.nodes.find(row => row.id === initialNodeId)
    || data.nodes.find(row => row.linked_disorder_slug === "panic-disorder")
    || data.nodes[0];
  const [selectedId, setSelectedId] = useState(preferred?.id || "");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | "hierarchy" | "nearby" | "differential">("all");
  const [type, setType] = useState<"all" | DSMGraphNode["display_type"]>("all");

  const nodeById = useMemo(() => new Map(data.nodes.map(node => [node.id, node])), [data.nodes]);
  const selected = nodeById.get(selectedId) || preferred;

  const filtered = useMemo(() => {
    const q = normalizePersianSearch(query.trim());
    return data.nodes
      .filter(node => (type === "all" || node.display_type === type) && (!q || normalizePersianSearch(
        `${node.label} ${node.name_en} ${node.id} ${node.chapter_name_fa} ${node.group_name} ${node.summary}`
      ).includes(q)))
      .sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label, "fa"));
  }, [data.nodes, query, type]);

  const neighbors = useMemo<DSMGraphNeighbor[]>(() => {
    if (!selected) return [];
    const rows = data.edges.reduce<DSMGraphNeighbor[]>((items, edge, index) => {
      if (edge.source === selected.id) {
        const node = nodeById.get(edge.target);
        if (node) items.push({ node, edge, direction: "out", key: `${index}-out` });
      } else if (edge.target === selected.id) {
        const node = nodeById.get(edge.source);
        if (node) items.push({ node, edge, direction: "in", key: `${index}-in` });
      }
      return items;
    }, []);
    return rows
      .filter(row => kind === "all" || row.edge.kind === kind)
      .sort((a, b) => b.node.degree - a.node.degree || a.node.label.localeCompare(b.node.label, "fa"));
  }, [data.edges, kind, nodeById, selected]);

  if (!selected) return <div className="card">DSM Graph هنوز داده‌ای ندارد.</div>;

  return (
    <div className="dsm-graph-explorer stack">
      <section className="graph-overview">
        <div><strong>{data.meta.node_count.toLocaleString("fa-IR")}</strong><span>گره MASTER</span></div>
        <div><strong>{data.meta.edge_count.toLocaleString("fa-IR")}</strong><span>رابطه</span></div>
        <div><strong>{data.meta.relation_counts.hierarchy.toLocaleString("fa-IR")}</strong><span>ساختاری</span></div>
        <div><strong>{data.meta.relation_counts.nearby.toLocaleString("fa-IR")}</strong><span>عنوان نزدیک</span></div>
        <div><strong>{data.meta.relation_counts.differential.toLocaleString("fa-IR")}</strong><span>افتراق لینک‌شده</span></div>
      </section>

      <div className="knowledge-map-layout knowledge-map-layout-v2">
        <aside className="card map-browser map-browser-v2">
          <div><div className="meta">DSM MASTER</div><h3>۴۳۸ گره ساختاری و آموزشی</h3></div>
          <input className="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="نام، فصل، گروه یا MASTER ID..." />
          <select className="search" value={type} onChange={event => setType(event.target.value as typeof type)}>
            <option value="all">همه نوع رکوردها</option>
            <option value="diagnosis">تشخیص رسمی</option>
            <option value="structural">ساختاری</option>
            <option value="clinical_attention">کانون توجه بالینی</option>
            <option value="research">پژوهشی</option>
            <option value="alternative_model">مدل جایگزین</option>
            <option value="specifier">مشخص‌کننده</option>
            <option value="reference">ارجاع</option>
          </select>
          <div className="map-list-summary"><span>{filtered.length.toLocaleString("fa-IR")} نتیجه</span><span>Degree واقعی</span></div>
          <div className="map-node-list map-node-list-v2 dsm-graph-node-list">
            {filtered.map(node => (
              <button key={node.id} className={`map-list-node ${selected.id === node.id ? "active" : ""}`} onClick={() => setSelectedId(node.id)}>
                <div><span>{node.label}</span><small>{node.id} · {dsmTypeLabel(node.display_type)}</small></div>
                <b>{node.degree.toLocaleString("fa-IR")}</b>
              </button>
            ))}
          </div>
        </aside>

        <section className="map-stage card map-stage-v2">
          <div className="map-stage-head map-stage-head-v2">
            <div>
              <div className="meta">{dsmTypeLabel(selected.display_type)} · {selected.id}</div>
              <h2>{selected.label}</h2>
              <div className="latin-title">{selected.name_en}</div>
            </div>
            <div className="actions">
              {selected.linked_disorder_slug && <Link className="button" href={`/disorders/${selected.linked_disorder_slug}`}>صفحه Atlas</Link>}
              <Link className="button primary" href={selected.href}>پروفایل MASTER</Link>
            </div>
          </div>

          <div className="node-profile-grid">
            <div className="map-core map-core-v2 concept">
              <span>{selected.chapter_number ? `فصل ${selected.chapter_number.toLocaleString("fa-IR")}` : "DSM MASTER"}</span>
              <strong>{selected.label}</strong>
              <small>{selected.group_name || selected.chapter_name_fa || selected.id}</small>
            </div>
            <div className="node-profile-copy">
              <p>{selected.summary}</p>
              <div className="node-facts">
                <div><strong>{selected.degree.toLocaleString("fa-IR")}</strong><span>اتصال مستقیم</span></div>
                <div><strong>{neighbors.filter(row => row.edge.kind === "hierarchy").length.toLocaleString("fa-IR")}</strong><span>ساختاری</span></div>
                <div><strong>{neighbors.filter(row => row.edge.kind === "nearby").length.toLocaleString("fa-IR")}</strong><span>عنوان نزدیک</span></div>
                <div><strong>{neighbors.filter(row => row.edge.kind === "differential").length.toLocaleString("fa-IR")}</strong><span>افتراق لینک‌شده</span></div>
              </div>
            </div>
          </div>

          <div className="relation-toolbar">
            <div><strong>روابط MASTER</strong><span>{neighbors.length.toLocaleString("fa-IR")} رابطه در فیلتر فعلی</span></div>
            <div className="relation-filter-row">
              {(["all", "hierarchy", "nearby", "differential"] as const).map(value => (
                <button key={value} className={`chip ${kind === value ? "active" : ""}`} onClick={() => setKind(value)}>
                  {value === "all" ? "همه" : edgeLabels[value]}
                </button>
              ))}
            </div>
          </div>

          <div className="map-neighbors map-neighbors-v2">
            {neighbors.map(({ node, edge, direction, key }) => (
              <button key={key} className="map-neighbor map-neighbor-v2 concept" onClick={() => setSelectedId(node.id)}>
                <div className="neighbor-topline"><span className="edge-label">{direction === "in" ? "ورودی" : "خروجی"} · {edgeLabels[edge.kind]}</span><b>{node.degree.toLocaleString("fa-IR")}</b></div>
                <strong>{node.label}</strong>
                <small>{node.id} · {dsmTypeLabel(node.display_type)}</small>
                {edge.explanation && <p>{edge.explanation}</p>}
              </button>
            ))}
            {!neighbors.length && <div className="empty-relation">رابطه‌ای برای این فیلتر ثبت نشده است.</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
