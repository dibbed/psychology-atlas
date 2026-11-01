import ReviewDetail from "@/components/cms/ReviewDetail";
export default async function ReviewRecordPage({ params }: { params: Promise<{ kind: string; id: string }> }) {
  const { kind, id } = await params;
  return <ReviewDetail key={`${kind}/${id}`} kind={kind} id={id} />;
}
