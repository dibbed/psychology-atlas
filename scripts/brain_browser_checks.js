// Pass this function to Playwright MCP browser_run_code_unsafe (code or filename).
// Use the real published backend at :8013 and a running local frontend page.
// For retry coverage, invoke from the error page after restarting the backend.
async (page) => {
  const current = new URL(page.url());
  if (!["localhost", "127.0.0.1"].includes(current.hostname)) throw new Error("Run on a local QA frontend.");
  const origin = current.origin;
  const api = "http://127.0.0.1:8013/api";
  const checks = [];
  const assert = (condition, label) => {
    if (!condition) throw new Error(label);
    checks.push(label);
  };
  const json = async (path) => {
    const response = await page.request.get(api + path);
    if (!response.ok()) throw new Error("Backend unavailable: " + path);
    return response.json();
  };
  const goto = async (path) => { await page.goto(origin + path); await page.locator("main:visible").first().waitFor(); };
  const cards = () => page.locator(".brain-card");
  const overflow = async (label) => assert(await page.evaluate(() =>
    document.documentElement.scrollWidth <= innerWidth), label);
  const retry = page.getByRole("link", { name: "تلاش دوباره", exact: true });
  if (await retry.count()) {
    await retry.click();
    await cards().first().waitFor();
    assert(await cards().count() > 0, "retry recovers real results");
  }
  const warnings = [];
  const onConsole = message => {
    if (["error", "warning"].includes(message.type()) && !message.text().includes("404 (Not Found)")) warnings.push(message.text());
  };
  const onError = error => warnings.push(error.message);
  page.on("console", onConsole);
  page.on("pageerror", onError);
  try {
    const all = await json("/brain-anatomy/?page_size=300");
    const roots = await json("/brain-anatomy/?roots=true");
    assert(all.results.length > 0 && roots.count > 1, "real published forest available");
    await page.setViewportSize({ width: 1280, height: 800 });
    await goto("/brain");
    await cards().first().waitFor();
    assert(await cards().count() === Math.min(30, all.count), "list uses API pagination");
    await page.keyboard.press("Tab");
    assert(await page.evaluate(() => document.activeElement?.classList.contains("skip-link")), "keyboard reaches skip link");
    if (all.count > 30) {
      await page.getByRole("link", { name: "صفحهٔ بعد", exact: true }).click();
      await page.waitForURL(/page=2/);
      const second = await json("/brain-anatomy/?page=2");
      await page.locator('.brain-card[href="/brain/' + second.results[0].slug + '"]').waitFor();
      assert((await cards().first().getAttribute("href")) === "/brain/" + second.results[0].slug, "next page uses real second-page data");
      await goto("/brain?page=last");
      const last = await json("/brain-anatomy/?page=last");
      await page.locator('.brain-card[href="/brain/' + last.results[0].slug + '"]').waitFor();
      assert(await cards().count() === last.results.length, "last-page token shows real final-page data");
      assert(/صفحهٔ [۰-۹0-9]+/.test(await page.locator(".brain-pagination").innerText()), "last-page label remains numeric");
      const previous = new URL(last.previous).searchParams.get("page") || "1";
      await page.getByRole("link", { name: "صفحهٔ قبل", exact: true }).click();
      await page.waitForURL(url => (url.searchParams.get("page") || "1") === previous);
      const preceding = await json("/brain-anatomy/?page=" + previous);
      await page.locator('.brain-card[href="/brain/' + preceding.results[0].slug + '"]').waitFor();
      assert((await cards().first().getAttribute("href")) === "/brain/" + preceding.results[0].slug, "last-page previous link recovers preceding results");
    }
    const persian = all.results.find(entity => entity.name_fa);
    for (const term of [persian.name_en, persian.name_fa, "کورپوس کالوزوم"]) {
      await page.getByLabel("نام ساختار یا نام جایگزین").fill(term);
      await page.getByRole("button", { name: "اعمال انتخاب‌ها" }).click();
      await page.waitForURL(url => url.searchParams.get("q") === term);
      const expected = await json("/brain-anatomy/?q=" + encodeURIComponent(term));
      await cards().first().waitFor();
      assert(await cards().count() === Math.min(30, expected.count), "real name/alias search: " + term);
      assert(!new URL(page.url()).searchParams.has("page"), "search resets pagination: " + term);
    }
    const filteredUrl = page.url();
    await cards().first().click();
    await page.locator(".brain-detail-header h1").waitFor();
    await page.goBack();
    await cards().first().waitFor();
    assert(page.url() === filteredUrl, "browser back preserves search");
    await goto("/brain");
    await page.getByLabel("نوع ساختار", { exact: true }).selectOption("lobe");
    await page.getByLabel("سمت", { exact: true }).selectOption("not_established");
    await page.getByRole("button", { name: "اعمال انتخاب‌ها" }).click();
    await page.waitForURL(url => url.searchParams.get("kind") === "lobe");
    const filtered = await json("/brain-anatomy/?kind=lobe&laterality=not_established");
    await cards().first().waitFor();
    assert(await cards().count() === filtered.count, "kind and laterality combine against backend");
    await page.getByRole("link", { name: "پاک‌کردن انتخاب‌ها", exact: true }).click();
    await page.waitForURL(origin + "/brain");
    await cards().first().waitFor();
    assert(await page.getByLabel("نوع ساختار", { exact: true }).inputValue() === "", "clear resets form and URL");
    await page.getByLabel("نام ساختار یا نام جایگزین").fill("no-matching-anatomy-v093");
    await page.getByRole("button", { name: "اعمال انتخاب‌ها" }).click();
    await page.getByRole("heading", { name: "ساختاری مطابق این انتخاب پیدا نشد" }).waitFor();
    assert(await cards().count() === 0, "honest no-results state");
    await goto("/brain?roots=true");
    await cards().first().waitFor();
    assert(await cards().count() === roots.results.length, "root browsing uses public API");
    const root = roots.results.find(entity => !entity.name_fa);
    await page.locator('.brain-card[href="/brain/' + root.slug + '"]').click();
    await page.locator(".brain-detail-header h1").waitFor();
    assert((await page.locator("main h1").innerText()).trim() === root.name_en, "untranslated entity keeps English scientific name");
    assert((await page.locator("main h1 bdi").getAttribute("lang")) === "en", "English scientific heading has language");
    assert(await page.getByText("برای این ساختار، والد منتشرشده‌ای ثبت نشده است.", { exact: false }).count() > 0, "missing parent is described honestly");
    await goto("/brain/frontal-lobe");
    await page.getByRole("link", { name: /مرور همهٔ زیرساختارها/ }).click();
    await page.waitForURL(/parent=frontal-lobe/);
    await cards().first().waitFor();
    const children = await json("/brain-anatomy/?parent=frontal-lobe");
    assert(await cards().count() === children.count, "parent browsing uses published child filter");
    await goto("/brain/ca1-field");
    const child = await json("/brain-anatomy/ca1-field/");
    await page.locator(".brain-detail-header h1").waitFor();
    assert(await page.locator(".brain-hierarchy-parent a").first().getAttribute("href") === "/brain/" + child.parent.entity.slug, "detail parent navigation matches API");
    const disclosure = page.locator(".brain-hierarchy .brain-disclosure > summary").first();
    await disclosure.focus();
    await page.keyboard.press("Enter");
    assert(await disclosure.evaluate(summary => summary.parentElement.open), "hierarchy provenance opens by keyboard");
    assert(await page.locator(".brain-sources a[target='_blank'][rel='noreferrer']").count() > 0, "source links preserve safe external navigation");
    assert(child.network_memberships.length === 0 && child.functional_associations.length === 0, "real publication has no inferred functional relations");
    const longest = all.results.reduce((a, b) => a.name_en.length > b.name_en.length ? a : b);
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({ width, height: width === 1280 ? 800 : 844 });
      await goto("/brain");
      await cards().first().waitFor();
      await overflow("list reflows at " + width);
      await goto("/brain/" + longest.slug);
      await page.locator(".brain-detail-header h1").waitFor();
      await overflow("long English detail reflows at " + width);
      await page.getByText("منبع داده و حقوق استفاده", { exact: true }).click();
      await overflow("expanded attribution reflows at " + width);
      await page.locator(".brain-hierarchy .brain-disclosure > summary").first().click();
      await overflow("expanded hierarchy source reflows at " + width);
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    await goto("/brain");
    await cards().first().waitFor();
    assert(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches), "reduced-motion preference respected");
    assert(await cards().first().evaluate(card => parseFloat(getComputedStyle(card).transitionDuration) <= .01), "card motion is reduced");
    const invalid = await page.goto(origin + "/brain/not-an-approved-entity");
    await page.getByRole("heading", { name: "این ساختار پیدا نشد" }).waitFor();
    assert(invalid.status() === 404 || (await page.locator('meta[name="robots"]').first().getAttribute("content")).includes("noindex"), "missing detail uses framework not-found and noindex");
    await goto("/brain?kind=invalid");
    await page.getByRole("heading", { name: "این انتخاب قابل نمایش نیست" }).waitFor();
    assert(await page.getByRole("link", { name: "همهٔ ساختارها", exact: true }).count() > 0, "invalid query has a recovery path");
    assert(warnings.length === 0, "no hydration, runtime or console warnings");
    return { passed: checks.length, checks };
  } finally {
    page.off("console", onConsole);
    page.off("pageerror", onError);
    await page.emulateMedia({ reducedMotion: "no-preference" });
  }
}
