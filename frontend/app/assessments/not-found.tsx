import Link from "next/link";
import "./assessments.css";

export default function AssessmentNotFound() {
  return <main className="shell page assessment-page"><section className="assessment-empty"><span className="eyebrow">۴۰۴ · ابزارهای سنجش</span><h1>این خانوادهٔ ابزار پیدا نشد</h1><p>ممکن است آدرس اشتباه باشد یا این خانواده در مجموعهٔ عمومی منتشر نشده باشد.</p><Link className="button primary" href="/assessments">بازگشت به فهرست ابزارها</Link></section></main>;
}
