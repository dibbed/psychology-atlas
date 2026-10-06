import Link from "next/link";
import "./brain.css";

export default function BrainNotFound() {
  return <main className="shell page brain-page"><section className="brain-empty"><span className="eyebrow">۴۰۴ · اطلس مغز</span><h1>این ساختار پیدا نشد</h1><p>ممکن است آدرس اشتباه باشد یا این ساختار در مجموعهٔ عمومی منتشر نشده باشد.</p><Link className="button primary" href="/brain">بازگشت به اطلس مغز</Link></section></main>;
}
