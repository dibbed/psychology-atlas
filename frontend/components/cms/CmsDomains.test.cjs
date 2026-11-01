const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function runtime(handler = () => Response.json({})) {
  const calls = [], events = [];
  const context = vm.createContext({ Headers, FormData, AbortSignal, Event,
    window: { dispatchEvent: event => events.push(event.type) },
    fetch: async (url, options) => { calls.push({url, options}); return handler(url, options); },
  });
  const cache = new Map();
  function load(name) {
    if (cache.has(name)) return cache.get(name);
    const source = fs.readFileSync(path.resolve(__dirname, '../../lib', name + '.ts'), 'utf8');
    const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
    const module = {exports: {}};
    vm.runInContext(`(function(require,module,exports){${output}\n})`, context)(id => load(id.replace('./', '')), module, module.exports);
    cache.set(name, module.exports); return module.exports;
  }
  return {...load('cmsDomains'), calls, events};
}

test('only server-declared operational fields and create-only identity reach a new draft', () => {
  const api = runtime();
  const schema = {fields: [
    {name: 'name_en', type: 'string', required: true},
    {name: 'slug', type: 'string', create_only: true, readonly_reason: 'CREATE_ONLY_IDENTITY'},
    {name: 'raw_document', type: 'readonly', readonly_reason: 'immutable'},
  ]};
  const form = {name_en: 'NON-SCIENTIFIC fixture', slug: 'non-scientific', raw_document: 'blocked', undeclared: 'blocked'};
  assert.deepEqual(JSON.parse(JSON.stringify(api.draftPayload(schema, form, true))), {name_en: form.name_en, slug: form.slug});
  assert.deepEqual(JSON.parse(JSON.stringify(api.draftPayload(schema, form, false))), {name_en: form.name_en});
});

test('versioned actions fail closed on missing/weak ETag before any fetch', async () => {
  const api = runtime();
  for (const etag of [null, '', 'W/"2"']) {
    await assert.rejects(api.domainAction('concept', 'id', 'preview', etag, 7), e => e.code === 'PRECONDITION_REQUIRED');
  }
  assert.equal(api.calls.length, 0);
});

test('three-way reconciliation retains nonoverlapping edits, requires real conflicts, and recognizes a committed lost response', () => {
  const api = runtime();
  const schema = {fields: [{name: 'name_en', type: 'string'}, {name: 'sort_order', type: 'integer'}, {name: 'slug', type: 'string', create_only: true}]};
  const old = {name_en: 'NON-SCIENTIFIC old', sort_order: 0, slug: 'immutable'};
  const mine = {...old, name_en: 'NON-SCIENTIFIC mine'};
  const server = {...old, sort_order: 2};
  assert.equal(JSON.stringify(api.rebaseChoices(schema, old, mine, server)), '{"name_en":"mine","sort_order":"current"}');
  assert.equal('name_en' in api.rebaseChoices(schema, old, mine, {...server, name_en: 'OTHER NON-SCIENTIFIC'}), false);
  assert.equal(api.rebaseChoices(schema, old, mine, mine).name_en, 'mine');
  assert.equal('slug' in api.rebaseChoices(schema, old, mine, server), false);
});

test('legacy editor uses complete field_values and sends only changed writable fields', () => {
  const api = runtime();
  const schema = {fields: [{name:'name_en',type:'string'}, {name:'sort_order',type:'integer'}, {name:'clinical_features',type:'text'}, {name:'slug',type:'string',create_only:true}]};
  const record = {payload: {name_en:'NON-SCIENTIFIC legacy'}, field_values: {name_en:'NON-SCIENTIFIC legacy',sort_order:17,clinical_features:'NON-SCIENTIFIC preserved',slug:'immutable'}};
  const baseline = api.recordFields(record);
  assert.equal(baseline.sort_order, 17);
  assert.equal(baseline.clinical_features, 'NON-SCIENTIFIC preserved');
  const patch = api.revisionPatch(schema, baseline, {...baseline,name_en:'NON-SCIENTIFIC changed'});
  assert.equal(JSON.stringify(patch), '{"name_en":"NON-SCIENTIFIC changed"}');
  assert.equal(JSON.stringify(api.revisionPatch(schema, baseline, baseline)), '{}');
  assert.equal(api.recordFields({payload:record.payload}).name_en, record.payload.name_en);
});

test('preview retains current account, fresh CSRF, exact ETag and empty payload', async () => {
  const api = runtime(url => Response.json(url.endsWith('/me/') ? {user: {id: 7}} : url.endsWith('/auth/csrf/') ? {csrf_token: 'csrf'} : {valid: true}));
  await api.domainAction('concept', 'id', 'preview', '"12"', 7);
  assert.deepEqual(api.calls.map(c => c.url), ['/api/admin/me/', '/api/admin/auth/csrf/', '/api/admin/content/concept/id/preview/']);
  const request = api.calls.at(-1).options;
  assert.equal(request.headers.get('If-Match'), '"12"');
  assert.equal(request.headers.get('X-CSRFToken'), 'csrf');
  assert.equal(request.body, '{}');
  assert.equal(request.credentials, 'same-origin');
});

test('changed current account blocks domain writes before CSRF or mutation dispatch', async () => {
  const api = runtime(() => Response.json({user: {id: 8}}));
  await assert.rejects(api.domainAction('concept', 'id', 'archive', '"2"', 7), e => e.code === 'UNAUTHENTICATED');
  assert.equal(api.calls.length, 1);
  assert.deepEqual(api.events, ['cms-session-expired']);
});

test('a real stale server response stays blocked with its trace and without retry', async () => {
  const api = runtime(url => Response.json(url.endsWith('/me/') ? {user: {id: 7}} : url.endsWith('/auth/csrf/') ? {csrf_token: 'csrf'} : {code: 'STALE_REVISION', request_id: 'NON-SCIENTIFIC-trace'}, {status: url.endsWith('/validate/') ? 412 : 200}));
  await assert.rejects(api.domainAction('dsm-record', 'id', 'validate', '"2"', 7), e => api.domainWriteBlocked(e) && e.details.request_id === 'NON-SCIENTIFIC-trace');
  assert.equal(api.calls.filter(c => c.options.method === 'POST').length, 1);
});

test('unknown write is blocked and never automatically replayed; stale remains blocked', async () => {
  const api = runtime(url => {
    if (url.endsWith('/me/')) return Response.json({user: {id: 7}});
    if (url.endsWith('/auth/csrf/')) return Response.json({csrf_token: 'csrf'});
    throw new TypeError('lost response');
  });
  await assert.rejects(api.domainAction('dsm-record', 'id', 'archive', '"2"', 7), e => api.domainWriteBlocked(e));
  assert.equal(api.calls.filter(c => c.options.method === 'POST').length, 1);
  assert.equal(api.domainWriteBlocked({status: 412}), true);
});

function renderFields(props) {
  const React = require('react'), {renderToStaticMarkup} = require('react-dom/server');
  const cache = new Map();
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename);
    const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022}}).outputText;
    const module = {exports: {}}; cache.set(filename, module.exports);
    const localRequire = id => {
      if (id === './CmsShell') return {CmsState: () => React.createElement('p', null, 'loading')};
      if (!id.startsWith('.') && !id.startsWith('@/')) return require(id);
      const base = id.startsWith('@/') ? path.resolve(__dirname, '../..', id.slice(2)) : path.resolve(path.dirname(filename), id);
      return load(fs.existsSync(base + '.tsx') ? base + '.tsx' : base + '.ts');
    };
    new Function('require', 'module', 'exports', output)(localRequire, module, module.exports);
    return module.exports;
  }
  return renderToStaticMarkup(React.createElement(load(path.resolve(__dirname, 'DomainFields.tsx')).default, props));
}

test('operational controls retain typed numbers, choices, dates, identity policy and accessible labels', () => {
  const schema = {kind: 'NON-SCIENTIFIC', fields: [
    {name: 'sort_order', type: 'integer', required: false},
    {name: 'domain', type: 'choice', choices: [{value: 'test', label: 'NON-SCIENTIFIC'}]},
    {name: 'version_date', type: 'date'},
    {name: 'slug', type: 'string', create_only: true, readonly_reason: 'CREATE_ONLY_IDENTITY'},
    {name: 'raw_document', type: 'structured', readonly_reason: 'IMMUTABLE_RAW'},
  ]};
  const create = renderFields({schema, form: {sort_order: 0, domain: 'test'}, creating: true, disabled: false, onChange() {}});
  assert.match(create, /type="number"/); assert.match(create, /step="1"/);
  assert.match(create, /type="date"/); assert.match(create, /name="slug"/);
  assert.match(create, /for="domain-sort_order"/); assert.match(create, /NON-SCIENTIFIC/);
  assert.doesNotMatch(create, /name="raw_document"/);
  const edit = renderFields({schema, form: {slug: 'immutable'}, creating: false, disabled: false, onChange() {}});
  assert.doesNotMatch(edit, /name="slug"/); assert.match(edit, /immutable/);
});

test('structured operational fields render typed property/item controls, never a JSON text editor', () => {
  const html = renderFields({schema: {fields: [{name: 'assessment', type: 'structured', structure: {root: 'object', max_items: 100, max_depth: 6, max_nodes: 1000, max_text_length: 2000, max_bytes: 65536, value_types: ['string', 'number', 'boolean', 'null', 'array', 'object']}}]}, form: {assessment: {note: 'NON-SCIENTIFIC fixture', scores: [1, false]}}, creating: false, disabled: false, onChange() {}});
  assert.match(html, /NON-SCIENTIFIC fixture/); assert.match(html, /type="number"/); assert.match(html, /maxlength="160"/i);
  assert.match(html, /fieldset/); assert.doesNotMatch(html, /\{&quot;note&quot;/);
});

test('all 68 actual P07-P09 backend schemas render with operational controls and protected-field omission without DB access', () => {
  const {execFileSync} = require('node:child_process'), os = require('node:os');
  const root = path.resolve(__dirname, '../../..'), backend = path.join(root, 'backend');
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-p07-ui-schema-'));
  const database = path.join(temporary, 'owned-never-opened.sqlite3');
  const code = [
    'import django,json',
    'from django.db.backends.base.base import BaseDatabaseWrapper',
    'def deny_connection(*args,**kwargs): raise AssertionError("Schema test must never connect to a database")',
    'BaseDatabaseWrapper.connect=deny_connection',
    'django.setup()',
    'from atlas.cms_domains import DOMAIN_SPECS,schema_data',
    'print(json.dumps([schema_data(kind) for kind in DOMAIN_SPECS]))',
  ].join('\n');
  try {
    const schemas = JSON.parse(execFileSync(path.join(backend, '.venv/Scripts/python.exe'), ['-c', code], {cwd: backend, encoding: 'utf8', env: {...process.env, DJANGO_SETTINGS_MODULE: 'config.settings', DB_ENGINE: 'sqlite', SQLITE_PATH: database, CMS_ARTIFACT_ROOT: path.join(temporary, 'artifacts')}, maxBuffer: 1024 * 1024}));
    assert.ok(schemas.length >= 90); assert.equal(schemas.filter(x => x.domain === 'brain').length, 13); assert.equal(schemas.filter(x => x.domain === 'assessment').length, 9);
    const api = runtime();
    for (const schema of schemas) {
      const form = Object.fromEntries(schema.fields.map(field => [field.name, field.type === 'integer' || field.related_kind ? 1 : field.type === 'boolean' ? false : field.type === 'structured' ? field.structure?.root === 'array' ? [] : {} : field.type === 'date' ? '2026-10-30' : field.choices?.[0]?.value || 'NON-SCIENTIFIC fixture']));
      const html = renderFields({schema, form, creating: true, disabled: false, onChange() {}});
      assert.ok(html.includes('cms-fieldset'), schema.kind);
      const create = api.draftPayload(schema, form, true), edit = api.draftPayload(schema, form, false);
      for (const field of schema.fields) {
        if (field.readonly_reason && !field.create_only) assert.equal(field.name in create, false, `${schema.kind}.${field.name}`);
        if (field.create_only) {assert.equal(field.name in create, true); assert.equal(field.name in edit, false);}
      }
      assert.equal('raw_document' in create || 'source_payload' in create || 'is_active' in create, false);
    }
    assert.equal(fs.existsSync(database), false);
  } finally {
    // This test owns a single empty temp directory; no recursive deletion is needed.
    for (const name of fs.readdirSync(temporary)) fs.rmdirSync(path.join(temporary, name));
    fs.rmdirSync(temporary);
  }
});
