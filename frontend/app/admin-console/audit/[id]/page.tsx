import AuditExplorer from "@/components/cms/AuditExplorer";
export default async function AuditDetail({ params }: { params: Promise<{ id: string }> }) { return <AuditExplorer id={(await params).id} />; }
