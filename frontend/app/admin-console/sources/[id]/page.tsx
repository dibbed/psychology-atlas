import SourceRecord from "@/components/cms/SourceRecord";
export default async function SourcePage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <SourceRecord key={id} id={id} />; }
