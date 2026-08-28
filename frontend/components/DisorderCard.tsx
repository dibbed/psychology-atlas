import Link from "next/link";
import type { Disorder } from "@/lib/types";

export default function DisorderCard({ disorder }: { disorder: Disorder }) {
  return (
    <Link className="card" href={`/disorders/${disorder.slug}`}>
      <div className="meta">{disorder.category}</div>
      <h3>{disorder.name_fa || disorder.name_en}</h3>
      <p>{disorder.short_description}</p>
    </Link>
  );
}
