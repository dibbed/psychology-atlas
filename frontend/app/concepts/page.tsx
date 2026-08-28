import ConceptExplorer from "@/components/ConceptExplorer";

export default function ConceptsPage() {
  return (
    <main className="shell page stack">
      <div>
        <div className="meta">واژه‌نامه و Concepts Atlas</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>مفهوم را جدا از برچسب تشخیصی یاد بگیر.</h1>
        <p className="section-copy">مفاهیم شناختی، بالینی، رفتاری، هیجانی و درمانی را با تعریف ساده، تعریف دانشگاهی، مثال و روابط ساختاریافته مرور کن.</p>
      </div>
      <ConceptExplorer />
    </main>
  );
}
