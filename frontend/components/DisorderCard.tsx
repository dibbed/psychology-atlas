import Link from "next/link";
import type { Disorder } from "@/lib/types";

export default function DisorderCard({ disorder }: { disorder: Disorder }) {
  return (
    <Link className="card" href={`/disorders/${disorder.slug}`}>
      <div className="meta disorder-card-meta">
        <span>{disorder.category}</span>
        {disorder.data_origin === "dsm_master" && <span>DSM MASTER</span>}
      </div>
      <h3>{disorder.name_fa || disorder.name_en}</h3>
      {disorder.name_en && disorder.name_en !== disorder.name_fa && <div className="latin-label disorder-english-name">{disorder.name_en}</div>}
      <p>{disorder.short_description}</p>
    </Link>
  );
}
