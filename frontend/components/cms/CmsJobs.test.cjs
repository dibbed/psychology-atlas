// Run from frontend: node --test components/cms/CmsJobs.test.cjs
const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const me = { user: { id: 7, username: "test" }, session: { id: "session-a", expires_at: "2099-01-01" }, ready_capabilities: [] };
function runtime(handler) {
  const calls = [], events = [], messages = [];
  const context = vm.createContext({ FormData, File, Headers, AbortSignal, Event,
    window: { dispatchEvent: event => events.push(event.type) },
    BroadcastChannel: class { postMessage(message) { messages.push(message); } close() {} },
    fetch: async (url, options) => { calls.push({ url, options }); return handler(url, options); },
  });
  const cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name);
    const source = fs.readFileSync(path.resolve(__dirname, "../../lib", name + ".ts"), "utf8");
    const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
    const module = { exports: {} };
    vm.runInContext(`(function(require,module,exports){${output}\n})`, context)(id => load(id.replace("./", "")), module, module.exports);
    cache.set(name, module.exports); return module.exports;
  }
  return { ...load("cms"), ...load("cmsJobs"), calls, events, messages };
}
function json(body, status = 200) { return Response.json(body, { status, headers: { ETag: '"3"' } }); }
function standard(url) {
  if (url.endsWith("/me/")) return json(me);
  if (url.endsWith("/auth/csrf/")) return json({ csrf_token: "test-csrf" });
  return json({ artifact: { id: "opaque" } });
}

test("multipart upload keeps current-account, fresh CSRF, private transport and browser boundary", async () => {
  const api = runtime(standard); const body = new FormData(); body.set("kind", "research_json"); body.set("file", new File(["{}"], "test.json", { type: "application/json" }));
  await api.cmsJobs("/artifacts/", { method: "POST", body }, me);
  assert.deepEqual(api.calls.map(call => call.url), ["/api/admin/me/", "/api/admin/me/", "/api/admin/auth/csrf/", "/api/admin/artifacts/"]);
  const { options } = api.calls.at(-1);
  assert.equal(options.body, body); assert.equal(options.headers.has("Content-Type"), false);
  assert.equal(options.headers.get("X-CSRFToken"), "test-csrf");
  assert.equal(options.credentials, "same-origin"); assert.equal(options.cache, "no-store");
});

test("JSON writes still carry Content-Type and exact server If-Match", async () => {
  const api = runtime(standard);
  await api.cmsJobs("/jobs/opaque/cancel/", { method: "POST", headers: api.versionHeaders('"3"'), body: "{}" }, me);
  assert.equal(api.calls.at(-1).options.headers.get("Content-Type"), "application/json");
  assert.equal(api.calls.at(-1).options.headers.get("If-Match"), '"3"');
});

test("account mismatch prevents CSRF acquisition and mutation", async () => {
  const api = runtime(() => json({ ...me, user: { id: 8 } }));
  await assert.rejects(api.cms("/artifacts/", { method: "POST", body: new FormData() }, 7), error => error.code === "UNAUTHENTICATED");
  assert.equal(api.calls.length, 1); assert.deepEqual(api.events, ["cms-session-expired"]); assert.deepEqual(api.messages, ["changed"]);
});

test("same-account session rotation stops private reads and actions before dispatch", async () => {
  for (const method of ["GET", "POST"]) {
    const api = runtime(() => json({ ...me, session: { id: "rotated" } }));
    await assert.rejects(api.cmsJobs("/jobs/opaque/", { method }, me), error => error.code === "UNAUTHENTICATED");
    assert.equal(api.calls.length, 1); assert.deepEqual(api.events, ["cms-session-expired"]);
  }
});

test("lost upload response stays unknown and never replays the mutation", async () => {
  const api = runtime(url => { if (url.endsWith("/artifacts/")) throw new TypeError("lost response"); return standard(url); });
  await assert.rejects(api.cmsJobs("/artifacts/", { method: "POST", body: new FormData() }, me), error => error instanceof api.CmsJobsError && error.jobCode === "UNKNOWN_OUTCOME" && api.mutationBlocked(error));
  assert.equal(api.calls.filter(call => call.options.method === "POST").length, 1);
});

test("unreadable successful write remains unknown without retry", async () => {
  const api = runtime(url => url.endsWith("/research/imports/") ? new Response("broken", { status: 202 }) : standard(url));
  await assert.rejects(api.cmsJobs("/research/imports/", { method: "POST", body: "{}" }, me), error => error.code === "UNKNOWN_OUTCOME");
  assert.equal(api.calls.filter(call => call.options.method === "POST").length, 1);
});

test("safe read network failures do not claim a write outcome", async () => {
  const api = runtime(url => { if (url.endsWith("/jobs/")) throw new TypeError("offline"); return standard(url); });
  await assert.rejects(api.cmsJobs("/jobs/", {}, me), error => error.code === "NETWORK_ERROR" && !api.mutationBlocked(error));
  assert.equal(api.calls.length, 2);
});

test("typed API errors preserve status, trace and field diagnostics", async () => {
  const api = runtime(url => url.endsWith("/artifacts/") ? json({ code: "INVALID_UPLOAD", request_id: "trace", field_errors: { file: ["invalid"] } }, 400) : standard(url));
  await assert.rejects(api.cmsJobs("/artifacts/", { method: "POST", body: new FormData() }, me), error => error instanceof api.CmsJobsError && error.jobCode === "INVALID_UPLOAD" && error.status === 400 && error.details.request_id === "trace" && error.details.field_errors.file[0] === "invalid");
});

test("missing or weak ETags cannot authorize a mutation", () => {
  const api = runtime(standard);
  for (const value of [null, "", 'W/"3"']) assert.throws(() => api.versionHeaders(value), error => error.code === "PRECONDITION_REQUIRED");
  assert.equal(api.versionHeaders('"0"')["If-Match"], '"0"');
});

test("source mapping rejects ambiguous, repeated or unsafe IDs", () => {
  const api = runtime(standard);
  assert.equal(JSON.stringify(api.researchSourceIds("12، 34\n56")), "[12,34,56]");
  assert.equal(JSON.stringify(api.researchSourceIds("")), "[]");
  for (const value of ["0", "-1", "1.5", "1e2", "01", "12,12", "9007199254740992", "source-a"]) assert.throws(() => api.researchSourceIds(value), error => error.code === "INVALID_MAPPING");
});

test("only ready, unexpired files and active jobs receive action hints", () => {
  const api = runtime(standard);
  for (const state of ["quarantine", "revoked", "expired", "rejected"]) assert.equal(api.artifactUsable({ state, expires_at: "2099-01-01" }), false);
  assert.equal(api.artifactUsable({ state: "ready", expires_at: "2000-01-01" }), false);
  assert.equal(api.artifactUsable({ state: "ready", expires_at: "2099-01-01" }), true);
  for (const status of ["queued", "running", "reconciling"]) assert.equal(api.jobActive({ status }), true);
  for (const status of ["succeeded", "failed", "cancelled"]) assert.equal(api.jobActive({ status }), false);
});
