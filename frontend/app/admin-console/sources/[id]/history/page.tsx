import SourceHistory from "@/components/cms/SourceHistory";
export default async function SourceHistoryPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <SourceHistory key={id} id={id} />; }
