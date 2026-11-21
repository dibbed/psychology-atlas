import ResearchRecordDetail from "@/components/cms/ResearchRecordDetail";
export default async function ResearchRecordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResearchRecordDetail key={id} id={id} />;
}
