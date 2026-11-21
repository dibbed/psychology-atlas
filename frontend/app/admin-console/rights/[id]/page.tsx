import GovernanceRecord from "@/components/cms/GovernanceRecord";
export default async function RightsRecordPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <GovernanceRecord key={id} kind="rights" id={id} />; }
