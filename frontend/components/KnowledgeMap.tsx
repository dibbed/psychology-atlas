"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type MapNode = {
  id: string;
  type: "concept" | "disorder" | "symptom";
  slug: string;
  label: string;
  kind: string;
  href: string;
};

type MapEdge = { source: string; target: string; kind: string };
type MapNeighbor = { node: MapNode; edge: MapEdge; direction: "in" | "out"; key: string };

type MapData = { nodes: MapNode[]; edges: MapEdge[] };

function nodeTypeLabel(type: MapNode["type"]) {
  if (type === "concept") return "مفهوم";
  if (type === "disorder") return "اختلال";
  return "نشانه";
}

const edgeLabels: Record<string, string> = {
  related: "مرتبط",
  part_of: "جزئی از",
  maintains: "حفظ‌کننده",
  influences: "اثرگذار",
  contrasts: "مقایسه/تفاوت",
  applied_in: "کاربرد",
  core: "محوری",
  associated: "مرتبط با اختلال",
  maintaining: "حفظ‌کننده اختلال",
  assessment: "ارزیابی",
  treatment: "درمان/مداخله",
  differential: "افتراقی",
  symptom_core: "نشانه محوری",
  symptom_common: "نشانه رایج",
  symptom_possible: "نشانه ممکن",
  symptom_contextual: "نشانه زمینه‌ای",
};

export default function KnowledgeMap({ data, initialNodeId }: { data: MapData; initialNodeId?: string }) {
  const preferred = data.nodes.find(node => node.id === initialNodeId)
    || data.nodes.find(node => node.id === "concept:cognitive-distortions")
    || data.nodes.find(node => node.type === "concept")
    || data.nodes[0];
  const [selectedId, setSelectedId] = useState(preferred?.id || "");
  const [query, setQuery] = useState("");
  const [type, setType] = useState<"all" | "concept" | "disorder" | "symptom">("all");

  const nodeById = useMemo(() => new Map(data.nodes.map(node => [node.id, node])), [data.nodes]);
  const selected = nodeById.get(selectedId) || preferred;
  const neighbors = useMemo<MapNeighbor[]>(() => {
    if (!selected) return [];
    return data.edges.reduce<MapNeighbor[]>((rows, edge, index) => {
      if (edge.source === selected.id) {
        const node = nodeById.get(edge.target);
        if (node) rows.push({ node, edge, direction: "out", key: `${index}-${node.id}` });
      } else if (edge.target === selected.id) {
        const node = nodeById.get(edge.source);
        if (node) rows.push({ node, edge, direction: "in", key: `${index}-${node.id}` });
      }
      return rows;
    }, []);
  }, [data.edges, nodeById, selected]);

  const filteredNodes = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.nodes.filter(node => (type === "all" || node.type === type) && (!q || `${node.label} ${node.slug}`.toLowerCase().includes(q)));
  }, [data.nodes, query, type]);

  if (!selected) return <div className="card">نقشه هنوز داده‌ای ندارد.</div>;

  return (
    <div className="knowledge-map-layout">
      <aside className="card map-browser">
        <div className="meta">Node Browser</div>
        <input className="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="پیدا کردن node..." />
        <div className="category-chips compact-chips">
          <button className={`chip ${type === "all" ? "active" : ""}`} onClick={() => setType("all")}>همه</button>
          <button className={`chip ${type === "concept" ? "active" : ""}`} onClick={() => setType("concept")}>مفهوم</button>
          <button className={`chip ${type === "disorder" ? "active" : ""}`} onClick={() => setType("disorder")}>اختلال</button>
          <button className={`chip ${type === "symptom" ? "active" : ""}`} onClick={() => setType("symptom")}>نشانه</button>
        </div>
        <div className="map-node-list">
          {filteredNodes.map(node => (
            <button className={`map-list-node ${selected.id === node.id ? "active" : ""}`} onClick={() => setSelectedId(node.id)} key={node.id}>
              <span>{node.label}</span><small>{nodeTypeLabel(node.type)}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="map-stage card">
        <div className="map-stage-head">
          <div><div className="meta">Knowledge Graph V1</div><h2>{selected.label}</h2><p className="muted small">{neighbors.length.toLocaleString("fa-IR")} رابطه مستقیم در داده ساختاریافته</p></div>
          <Link className="button" href={selected.href}>باز کردن صفحه ←</Link>
        </div>

        <div className="map-orbit">
          <div className={`map-core ${selected.type}`}>
            <span>{nodeTypeLabel(selected.type)}</span>
            <strong>{selected.label}</strong>
          </div>
          <div className="map-neighbors">
            {neighbors.map(({ node, edge, direction, key }) => (
              <button className={`map-neighbor ${node.type}`} onClick={() => setSelectedId(node.id)} key={key}>
                <span className="edge-label">{direction === "in" ? "← " : ""}{edgeLabels[edge.kind] || edge.kind}{direction === "out" ? " →" : ""}</span>
                <strong>{node.label}</strong>
                <small>{nodeTypeLabel(node.type)}</small>
              </button>
            ))}
            {!neighbors.length && <div className="muted">برای این node هنوز edge مستقیمی ثبت نشده است.</div>}
          </div>
        </div>
      </section>
    </div>
  );
}
