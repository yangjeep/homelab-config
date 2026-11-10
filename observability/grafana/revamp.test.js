const test = require('node:test');
const assert = require('node:assert/strict');
const r = require('./revamp.js');

test('component expr has no hard-coded signal counts', () => {
  const e = r.componentExpr('TrueNAS');
  assert.doesNotMatch(e, /==\s*\d{2}|== 4\)/);
  assert.match(e, /last_over_time\(homelab_triage_state\{component="TrueNAS"\}\[1d\]\)/);
  assert.match(e, /or on\(\) vector\(2\)/);
});

test('score ranks critical above unknown above warning', () => {
  const e = r.scoreExpr('{component="x"}');
  assert.match(e, /== bool 2\) \* 3/);
  assert.match(e, /== bool 3\) \* 2/);
  assert.match(e, /== bool 1\)$/);
});

test('flatten pulls panels out of rows and drops text panels', () => {
  const out = r.flattenPanels([
    { type: 'text', id: 1 },
    { type: 'row', id: 2, panels: [{ type: 'stat', id: 3 }, { type: 'text', id: 4 }] },
    { type: 'timeseries', id: 5 },
  ]);
  assert.deepEqual(out.map((p) => p.id), [3, 5]);
});

test('merge: one row per source, unique ids, first expanded, rest collapsed', () => {
  const a = { title: 'A', panels: [{ type: 'stat', id: 9, gridPos: { x: 0, y: 2, w: 6, h: 4 } }] };
  const b = { title: 'B', panels: [{ type: 'stat', id: 9, gridPos: { x: 0, y: 0, w: 6, h: 3 } }] };
  const d = r.mergeDashboards({ uid: 'm', title: 'M' }, [a, b]);
  const ids = [];
  d.panels.forEach((p) => { ids.push(p.id); (p.panels || []).forEach((c) => ids.push(c.id)); });
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(d.panels[0].type, 'row');
  assert.equal(d.panels[0].collapsed, false);
  assert.equal(d.panels[1].gridPos.y, 1);
  const rowB = d.panels.find((p) => p.title === 'B');
  assert.equal(rowB.collapsed, true);
  assert.equal(rowB.gridPos.y, 5);
  assert.equal(rowB.panels[0].gridPos.y, 6);
});

test('merge does not mutate source dashboards', () => {
  const a = { title: 'A', panels: [{ type: 'stat', id: 1, gridPos: { x: 0, y: 3, w: 6, h: 4 } }] };
  const snap = JSON.stringify(a);
  r.mergeDashboards({ uid: 'm', title: 'M' }, [a]);
  assert.equal(JSON.stringify(a), snap);
});

test('home board: one tile per component, fits one screen, unique ids', () => {
  const h = r.buildHome();
  const tiles = h.panels.filter((p) => p.gridPos.y === 0);
  assert.equal(tiles.length, r.COMPONENTS.length);
  assert.ok(tiles.every((p) => p.gridPos.w * tiles.length <= 24));
  assert.ok(Math.max(...h.panels.map((p) => p.gridPos.y + p.gridPos.h)) <= 18);
  assert.equal(new Set(h.panels.map((p) => p.id)).size, h.panels.length);
  assert.ok(!h.panels.some((p) => p.type === 'text' || p.type === 'row'));
});

test('every dashboard is placed exactly once', () => {
  const uids = [...r.MERGES.flatMap((m) => m.sources), ...r.KEEP.map((k) => k[0]), ...r.ARCHIVE_ONLY];
  assert.equal(new Set(uids).size, uids.length);
  assert.equal(uids.length, 21);
});

test('service probe rule excludes internet probes and fires on any down series', () => {
  const rule = r.serviceProbeRule('f');
  assert.match(rule.data[0].model.expr, /instance!~".*\(google\|cloudflare\).*"/);
  assert.equal(rule.data[1].model.conditions[0].evaluator.params[0], -1);
  assert.equal(rule.noDataState, 'OK');
});
