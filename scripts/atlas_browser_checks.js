// Run with Playwright MCP browser_run_code_unsafe against a local frontend
// using the real curated backend at :8015. No publication or data writes.
async (page) => {
  const origin = new URL(page.url()).origin;
  if (!["localhost", "127.0.0.1"].includes(new URL(origin).hostname)) throw new Error("Local QA only.");
  const api = "http://127.0.0.1:8015/api";
  const checks = [];
  const assert = (ok, label) => { if (!ok) throw new Error(label); checks.push(label); };
  const json = async (path) => {
    const response = await page.request.get(api + path);
    assert(response.ok(), "API available: " + path);
    return response.json();
  };
  const goto = async (path) => { await page.goto(origin + path); await page.locator("main:visible").waitFor(); };
  const overflow = async (label) => assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label);
  const instruments = await json("/assessments/?page_size=300");
  const anatomy = await json("/brain-anatomy/?page_size=300");
  const graph = await json("/concept-map/");
  assert(instruments.results.length > 1 && anatomy.results.length > 1, "real reviewed corpus available");
  const phq = instruments.results.find(row => row.versions.results.some(version => version.key === "phq-9"));
  assert(!!phq, "exact PHQ-9 version belongs to a family");
  const details = await json("/assessments/" + phq.slug + "/");
  const brain = anatomy.results.find(row => row.name_fa) || anatomy.results[0];
  const brainDetail = await json("/brain-anatomy/" + brain.slug + "/");
  const brainAlias = brainDetail.aliases.find(row => row.text !== brain.name_en);
  const persianAssessmentAlias = [...details.aliases.results, ...details.versions.results.flatMap(version => version.aliases.results)]
    .find(alias => alias.language === "fa");
  const failures = [];
  const onError = error => failures.push(error.message);
  const onConsole = message => {
    if (message.type() === "error" && !message.location().url.includes("v095-unknown-slug")) failures.push(message.text());
  };
  const onResponse = response => {
    if (response.status() >= 400 && !response.url().includes("v095-unknown-slug")) failures.push("HTTP " + response.status() + ": " + response.url());
  };
  page.on("pageerror", onError);
  page.on("console", onConsole);
  page.on("response", onResponse);
  try {
    await page.setViewportSize({ width: 1280, height: 800 });
    await goto("/assessments");
    await page.locator(".assessment-card").first().waitFor();
    assert(await page.locator(".assessment-card").count() === Math.min(30, instruments.count), "explorer uses real API results");
    await page.keyboard.press("Tab");
    assert(await page.evaluate(() => document.activeElement?.classList.contains("skip-link")), "keyboard reaches skip link");
    await goto("/assessments?page_size=2");
    await page.locator(".assessment-card").first().waitFor();
    const firstPage = await json("/assessments/?page_size=2");
    assert(await page.locator(".assessment-card").count() === firstPage.results.length, "bounded page size uses API");
    if (firstPage.next) {
      await page.getByRole("link", { name: "صفحهٔ بعد ←", exact: true }).click();
      await page.waitForURL(url => url.searchParams.get("page") === "2");
      const secondPage = await json("/assessments/?page_size=2&page=2");
      await page.locator('.assessment-card[href="/assessments/' + secondPage.results[0].slug + '"]').waitFor();
      assert(await page.locator(".assessment-card").count() === secondPage.results.length, "next page renders canonical API page");
    }
    await page.locator('main input[name="q"]').fill("PHQ-9");
    await page.locator('main form button[type="submit"]').click();
    await page.waitForURL(url => url.searchParams.get("q") === "PHQ-9");
    await page.locator('.assessment-card[href="/assessments/' + phq.slug + '"]').waitFor();
    assert(!new URL(page.url()).searchParams.has("page"), "search resets page");
    const filteredUrl = page.url();
    await page.locator(".assessment-card").first().click();
    await page.waitForURL(origin + "/assessments/" + phq.slug);
    await page.locator(".assessment-finding").first().waitFor();
    assert((await page.locator("main:visible").innerText()).includes("0.873"), "original contextual precision rendered");
    assert((await page.locator("main:visible").innerText()).includes("0.86"), "separate pilot finding rendered");
    assert(/185|۱۸۵/.test(await page.locator("main:visible").innerText()), "study sample accompanies metric");
    assert((await page.locator("main:visible").innerText()).includes("مجوز استفاده احراز نشده"), "unknown Persian-form rights stay explicit");
    assert((await page.locator("main:visible").innerText()).includes("این رکورد فقط دربارهٔ ماده، فرم و استفادهٔ بالا است"), "rights stay scoped to material, form and use");
    await page.goBack();
    await page.locator(".assessment-card").first().waitFor();
    assert(page.url() === filteredUrl, "browser back preserves Assessment search");
    await goto("/assessments");
    await page.locator('main select[name="form_kind"]').selectOption("short");
    await page.locator('main form button[type="submit"]').click();
    await page.waitForURL(url => url.searchParams.get("form_kind") === "short");
    const shortForms = await json("/assessments/?form_kind=short");
    await page.locator(".assessment-card").first().waitFor();
    assert(await page.locator(".assessment-card").count() === shortForms.results.length, "supported version-form filter uses reviewed API");
    await page.getByRole("link", { name: "پاک‌کردن", exact: true }).click();
    await page.waitForURL(origin + "/assessments");
    await page.locator(".assessment-card").first().waitFor();
    await page.locator('main input[name="language"]').fill("fa");
    await page.locator('main select[name="access"]').selectOption("unknown");
    await page.locator('main form button[type="submit"]').click();
    await page.waitForURL(url => url.searchParams.get("language") === "fa");
    const faForms = await json("/assessments/?language=fa&access=unknown");
    await page.locator('.assessment-card[href="/assessments/' + faForms.results[0].slug + '"]').waitFor();
    assert(await page.locator(".assessment-card").count() === faForms.results.length, "language and access refer to the same public form");
    await goto("/assessments?q=zzzz-v095-no-match");
    await page.getByText(/پیدا نشد|یافت نشد/).first().waitFor();
    assert(await page.locator(".assessment-card").count() === 0, "no matches distinct from server failure");
    await goto("/assessments/v095-unknown-slug");
    await page.getByText(/پیدا نشد|یافت نشد/).first().waitFor();
    assert(await page.getByRole("link", { name: "تلاش دوباره", exact: true }).count() === 0, "unknown slug is not retryable server failure");
    for (const item of instruments.results) {
      await goto("/assessments/" + item.slug);
      await page.locator("main:visible h1").waitFor();
      assert((await page.locator("main:visible").innerText()).includes(item.name_en), "real detail identity: " + item.slug);
      if (item.slug !== phq.slug) assert((await page.locator("main:visible").innerText()).includes("مطالعه و یافتهٔ بازبینی‌شده‌ای"), "missing optional evidence explicit: " + item.slug);
    }
    const terms = [brain.name_en, brain.name_fa, brainAlias?.text, phq.name_en, "PHQ-9", phq.name_fa, persianAssessmentAlias?.text].filter(Boolean);
    for (const term of terms) {
      const expected = await json("/search/?q=" + encodeURIComponent(term));
      await goto("/search?q=" + encodeURIComponent(term));
      await page.locator(".results-count").waitFor();
      const domain = expected.assessments.length ? "assessments" : "brain";
      const rows = domain === "assessments" ? expected.assessments : expected.brain_entities;
      assert(rows.length > 0, "reviewed name/alias returns canonical entity: " + term);
      await page.locator('#search-' + domain + ' a[href="/' + domain + '/' + rows[0].slug + '"]').waitFor();
      assert(await page.locator("#search-disorders").count() === 1, "legacy search sections preserved: " + term);
    }
    await page.locator('#search-assessments a[href="/assessments/' + phq.slug + '"]').click();
    await page.waitForURL(origin + "/assessments/" + phq.slug);
    await page.locator(".assessment-detail-header h1").waitFor();
    await page.goBack();
    await page.locator(".results-count").waitFor();
    assert(new URL(page.url()).searchParams.get("q") === phq.name_fa, "Global Search back preserves latest query");
    const phqNode = graph.nodes.find(row => row.type === "assessment" && row.slug === phq.slug);
    const brainNode = graph.nodes.find(row => row.type === "brain_anatomy");
    assert(!!phqNode && !!brainNode, "both domains in real graph");
    const newIds = new Set(graph.nodes.filter(row => ["assessment", "brain_anatomy"].includes(row.type)).map(row => row.id));
    assert(graph.edges.filter(edge => newIds.has(edge.source) || newIds.has(edge.target)).every(edge =>
      edge.kind === "brain_part_of" && edge.source.startsWith("brain_anatomy:") && edge.target.startsWith("brain_anatomy:") && edge.sources?.length),
      "new-domain edges only source-backed anatomical hierarchy");
    assert(phqNode.degree === 0, "Assessment remains honestly isolated");
    await goto("/map?node=" + encodeURIComponent(phqNode.id));
    await page.locator(".map-stage h2").waitFor();
    assert((await page.locator(".map-stage h2").innerText()) === phqNode.label, "deep link selects isolated Assessment");
    await page.getByRole("button", { name: "ابزار ارزیابی", exact: true }).click();
    assert(await page.locator(".map-list-node").count() === graph.meta.node_types.assessment, "Assessment graph filter");
    await page.getByLabel("جست‌وجوی گره‌های نقشه").fill("PHQ-9");
    assert(await page.locator(".map-list-node").count() === 1, "reviewed version alias discovers canonical family in graph");
    await page.getByLabel("جست‌وجوی گره‌های نقشه").fill("");
    await page.locator(".map-stage").getByRole("link", { name: "صفحه کامل", exact: true }).click();
    await page.waitForURL(origin + "/assessments/" + phq.slug);
    await page.locator(".assessment-detail-header h1").waitFor();
    await page.goBack();
    await page.locator(".map-stage h2").waitFor();
    assert((await page.locator(".map-stage h2").innerText()) === phqNode.label, "graph detail back preserves selected node");
    await page.getByRole("button", { name: "ساختار مغز", exact: true }).click();
    await page.locator(".map-list-node").first().click();
    assert(new URL(page.url()).searchParams.get("node")?.startsWith("brain_anatomy:"), "Brain graph selection canonical identity");
    assert((await page.locator(".map-stage-head").innerText()).includes("ساختار مغز"), "Brain graph domain label");
    const legacy = graph.nodes.find(node => node.type === "concept");
    const legacySearch = await json("/search/?q=" + encodeURIComponent(legacy.label));
    assert(legacySearch.concepts.some(item => item.slug === legacy.slug), "legacy concept search retains canonical identity");
    await goto("/search?q=" + encodeURIComponent(legacy.label));
    await page.locator('#search-concepts a[href="/concepts/' + legacy.slug + '"]').waitFor();
    await goto("/map?node=" + encodeURIComponent(legacy.id));
    await page.locator(".map-stage h2").waitFor();
    assert((await page.locator(".map-stage h2").innerText()) === legacy.label, "legacy graph discovery and selection retained");
    await page.reload();
    await page.locator(".map-stage h2").waitFor();
    assert((await page.locator(".map-stage h2").innerText()) === legacy.label, "graph refresh preserves canonical selection");
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({ width, height: width === 1280 ? 800 : 844 });
      for (const path of ["/assessments", "/assessments/" + phq.slug, "/search?q=PHQ-9", "/map?node=" + encodeURIComponent(phqNode.id)]) {
        await goto(path);
        if (path.startsWith("/search")) await page.locator(".results-count").waitFor();
        if (path.startsWith("/map")) await page.locator(".map-stage h2").waitFor();
        await page.locator("main:visible h1").waitFor();
        await overflow(width + "px reflow: " + path);
        assert(await page.locator("main:visible h1").count() === 1, "one main heading: " + path);
      }
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    await overflow("reduced motion reflow");
    assert(failures.length === 0, "no page runtime errors: " + failures.join(" | "));
    return { checks: checks.length, evidence: checks, corpus: { assessments: instruments.count, anatomy: anatomy.count },
      limitations: persianAssessmentAlias ? [] : ["No reviewed Persian alias in the inspected PHQ family/edition; reviewed Persian display name tested."], supplementalMocks: false };
  } finally {
    page.off("pageerror", onError);
    page.off("console", onConsole);
    page.off("response", onResponse);
    await page.emulateMedia({ reducedMotion: null });
  }
}
