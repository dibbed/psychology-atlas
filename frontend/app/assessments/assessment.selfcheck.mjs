// Run from the repository root: node --experimental-strip-types frontend/app/assessments/assessment.selfcheck.mjs
import assert from "node:assert/strict";
import { assessmentHref, assessmentPaginationHref, assessmentQuery } from "../../lib/assessment.ts";

// Native GET forms send blank controls; the strict API must receive only selected filters.
const selected = assessmentQuery({
  q: "  پرسش‌نامه PHQ  ", construct: "", language: "fa", intended_use: "screening",
  access: "unknown", license: "unknown", form_kind: "", page_size: "1",
});
assert.equal(selected.invalid, false);
assert.equal(selected.params.get("q"), "پرسش‌نامه PHQ");
assert.equal(selected.params.has("construct"), false);
assert.equal(selected.params.has("form_kind"), false);
assert.equal(assessmentQuery({ language: ["fa", "en"] }).invalid, true);
assert.equal(assessmentQuery({ q: ["PHQ", "GAD"] }).invalid, true);
assert.equal(assessmentQuery({ unexpected: "value" }).invalid, true);
assert.equal(assessmentHref(assessmentQuery({ q: " ", access: "" }).params), "/assessments");

// Pagination keeps all scientific filters and never navigates to the API host.
const before = selected.params.toString();
for (const apiHref of [
  "http://127.0.0.1:8015/api/assessments/?page=2&page_size=1",
  "/api/assessments/?page=2",
]) {
  const href = assessmentPaginationHref(selected.params, apiHref);
  const url = new URL(href, "http://127.0.0.1:3015");
  assert.equal(url.pathname, "/assessments");
  assert.equal(url.origin, "http://127.0.0.1:3015");
  assert.equal(url.searchParams.get("page"), "2");
  for (const [key, value] of selected.params) assert.equal(url.searchParams.get(key), value);
}
assert.equal(selected.params.toString(), before);
const pageTwo = new URLSearchParams(selected.params);
pageTwo.set("page", "2");
assert.equal(assessmentHref(pageTwo, { page: "" }), assessmentHref(selected.params));
assert.equal(new URL(assessmentPaginationHref(pageTwo, "/api/assessments/?page_size=1"), "http://127.0.0.1:3015").searchParams.get("page"), "1");

console.log("PASS: Assessment GET normalization, duplicate/unsupported filters, local pagination, filter preservation and page reset.");
