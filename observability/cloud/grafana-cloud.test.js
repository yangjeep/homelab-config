const test = require('node:test');
const assert = require('node:assert/strict');
const g = require('./grafana-cloud.js');

test('dead-man rule fires when federated Prometheus up series is absent', () => {
  const r = g.deadmanRule('homelab-cloud');
  assert.equal(r.uid, 'hl-cloud-federate-deadman');
  assert.equal(r.labels.severity, 'critical');
  assert.equal(r.labels.oob, 'true');
  assert.match(r.data[0].model.expr, /absent_over_time\(up\{job="prometheus",source="homelab-federate"\}\[10m\]\)/);
  assert.equal(r.noDataState, 'OK');
});

test('home-unreachable rule needs every ingress check down', () => {
  const r = g.homeUnreachableRule('homelab-cloud');
  assert.equal(r.labels.oob, 'true');
  assert.match(r.data[0].model.expr, /^max\(max_over_time\(probe_success\{job="homelab-ingress"\}\[5m\]\)\)/);
  assert.equal(r.data.at(-1).model.conditions[0].evaluator.type, 'lt');
  assert.equal(r.noDataState, 'Alerting');
});

test('oob route is inserted first and only once', () => {
  const tree = { receiver: 'x', routes: [{ receiver: 'a', object_matchers: [['grafana_folder', '=', 'Homelab Cloud']] }] };
  const once = g.withOobRoute(tree, 'oob-recv');
  const twice = g.withOobRoute(once, 'oob-recv');
  assert.equal(twice.routes.length, 2);
  assert.deepEqual(twice.routes[0].object_matchers, [['oob', '=', 'true']]);
  assert.equal(twice.routes[0].receiver, 'oob-recv');
  assert.equal(tree.routes.length, 1, 'input not mutated');
});

test('oob route receiver is updated in place on re-run', () => {
  const tree = g.withOobRoute({ receiver: 'x', routes: [] }, 'old');
  assert.equal(g.withOobRoute(tree, 'new').routes[0].receiver, 'new');
});

test('external dashboard reads only cloud datasources', () => {
  const d = g.externalDashboard();
  assert.equal(d.uid, 'homelab-external-cloud');
  const uids = new Set(JSON.stringify(d).match(/"uid":"[^"]+"/g));
  assert.ok(![...uids].some((u) => u.includes('pdc')), 'no PDC datasource');
  assert.ok(d.panels.length >= 4);
});
