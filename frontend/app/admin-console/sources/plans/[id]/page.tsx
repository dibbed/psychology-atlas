import SourcePlanRecord from "@/components/cms/SourcePlanRecord";
export default async function SourcePlanPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <SourcePlanRecord key={id} id={id} />; }
