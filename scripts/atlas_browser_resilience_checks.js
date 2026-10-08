// Supplemental deterministic fault/race checks; run after the real-corpus journey.
async (page) => {
  const origin = new URL(page.url()).origin;
  if (!["localhost", "127.0.0.1"].includes(new URL(origin).hostname)) throw new Error("Local QA only.");
  const checks = [];
  const assert = (ok, label) => { if (!ok) throw new Error(label); checks.push(label); };
  const pattern = "**/api/search/**";
  await page.route(pattern, route => route.abort("connectionrefused"));
  try {
    await page.goto(origin + "/search?q=PHQ-9");
    await page.locator('main:visible [role="alert"]').waitFor();
    assert(await page.locator(".results-count").count() === 0, "network failure is not empty results");
  } finally { await page.unroute(pattern); }
  await page.getByRole("button", { name: "تلاش دوباره", exact: true }).click();
  await page.locator('#search-assessments a[href="/assessments/patient-health-questionnaire"]').waitFor();
  assert(await page.locator(".results-count").count() === 1, "retry recovers actual backend data");

  // Return real old responses after cancellation to cover transports that finish late.
  for (const failure of [false, true]) {
    await page.evaluate(fail => {
      const original = window.fetch;
      window.__v095Fetch = original;
      window.__v095Pending = 0;
      window.fetch = (input, options) => {
        const url = new URL(typeof input === "string" ? input : input.url, location.href);
        if (url.searchParams.get("q") !== "Amygdala") return original(input, options);
        window.__v095Pending++;
        return original(input, { ...options, signal: undefined }).then(response => new Promise((resolve, reject) =>
          setTimeout(() => {
            window.__v095Pending--;
            if (fail) reject(new Error("Deterministic old transport failure"));
            else resolve(response);
          }, 900)));
      };
    }, failure);
    try {
      const started = page.waitForRequest(request => new URL(request.url()).pathname === "/api/search/" && new URL(request.url()).searchParams.get("q") === "Amygdala");
      await page.getByLabel("جست‌وجوی سراسری اطلس").fill("Amygdala");
      await started;
      await page.getByLabel("جست‌وجوی سراسری اطلس").fill("PHQ-9");
      await page.locator('#search-assessments a[href="/assessments/patient-health-questionnaire"]').waitFor();
      await page.waitForFunction(() => window.__v095Pending === 0);
      assert(await page.locator('#search-assessments a[href="/assessments/patient-health-questionnaire"]').count() === 1,
        failure ? "late error cannot erase newer results" : "late success cannot overwrite newer results");
      assert(await page.locator('main:visible [role="alert"]').count() === 0, "old transport leaves no stale error");
      assert(new URL(page.url()).searchParams.get("q") === "PHQ-9", "rapid search preserves latest URL query");
    } finally {
      await page.evaluate(() => { window.fetch = window.__v095Fetch; delete window.__v095Fetch; delete window.__v095Pending; });
    }
  }
  await page.route(pattern, async route => { await new Promise(resolve => setTimeout(resolve, 800)); await route.continue(); });
  try {
    await page.getByLabel("جست‌وجوی سراسری اطلس").fill("BDI");
    await page.getByText("در حال جست‌وجو…", { exact: true }).waitFor();
    assert(await page.locator(".results-count").count() === 0, "loading does not show old results");
    await page.locator('#search-assessments a[href="/assessments/beck-depression-inventory"]').waitFor();
    assert(await page.locator('#search-assessments a[href="/assessments/beck-depression-inventory"]').count() === 1, "BDI resolves canonical family");
  } finally { await page.unroute(pattern); }
  const graphPattern = "**/api/concept-map/";
  await page.route(graphPattern, route => route.abort("connectionrefused"));
  try {
    await page.goto(origin + "/map");
    await page.locator('main:visible [role="alert"]').waitFor();
    assert(await page.locator(".knowledge-explorer").count() === 0, "graph failure is not empty corpus");
  } finally { await page.unroute(graphPattern); }
  await page.getByRole("button", { name: "تلاش دوباره", exact: true }).click();
  await page.locator(".map-stage h2").waitFor();
  assert(await page.locator(".knowledge-explorer").count() === 1, "graph retry recovers live corpus");
  return { checks: checks.length, evidence: checks, supplementalMocks: true };
}
