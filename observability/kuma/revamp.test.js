const test = require('node:test');
const assert = require('node:assert/strict');
const k = require('./revamp.js');

const live = [
  { id: 1, name: 'Home Assistance - NUC6', type: 'http', parent: null, maxretries: 3, notificationIDList: { 1: true, 2: true } },
  { id: 6, name: 'TrueNAS - Xeon E-2160', type: 'http', parent: null, maxretries: 0, notificationIDList: { 1: true, 2: true } },
  { id: 9, name: 'PiAware MLAT Data ', type: 'json-query', parent: null, maxretries: 15, notificationIDList: { 2: true } },
  { id: 14, name: 'Plex', type: 'keyword', parent: null, maxretries: 2, notificationIDList: { 1: true, 2: true } },
  { id: 23, name: 'Homelab · Kuma HTTPS ingress', type: 'http', parent: null, maxretries: 2, notificationIDList: { 1: true } },
];

test('groups come first and are unique', () => {
  const ops = k.plan(live);
  const firstEdit = ops.findIndex((o) => o.op !== 'ensureGroup');
  assert.ok(ops.slice(0, firstEdit).every((o) => o.op === 'ensureGroup'));
  const names = ops.filter((o) => o.op === 'ensureGroup').map((o) => o.name);
  assert.equal(new Set(names).size, names.length);
});

test('typo and trailing spaces fixed, monitor put in group', () => {
  const ops = k.plan(live);
  const ha = ops.find((o) => o.op === 'edit' && o.id === 1);
  assert.equal(ha.patch.name, 'Home Assistant · NUC6');
  assert.equal(ha.group, '家庭');
  const mlat = ops.find((o) => o.op === 'edit' && o.id === 9);
  assert.equal(mlat.patch.name, 'PiAware · MLAT');
});

test('retries raised to at least 2 with short retry interval', () => {
  const nas = k.plan(live).find((o) => o.op === 'edit' && o.id === 6);
  assert.equal(nas.patch.maxretries, 2);
  assert.equal(nas.patch.retryInterval, 30);
});

test('services covered by Grafana probes stop paging; watchdogs page', () => {
  const ops = k.plan(live);
  assert.deepEqual(ops.find((o) => o.op === 'edit' && o.id === 14).patch.notificationIDList, {});
  const wd = ops.filter((o) => o.op === 'ensureMonitor');
  assert.ok(wd.length >= 4);
  assert.ok(wd.every((o) => o.group === '监控链' && o.monitor.notificationIDList[1] && o.monitor.notificationIDList[2]));
});

test('new monitors carry the JSON fields Kuma 2 requires on insert', () => {
  const m = k.plan(live).find((o) => o.op === 'ensureMonitor').monitor;
  assert.deepEqual([m.conditions, m.kafkaProducerBrokers, m.rabbitmqNodes], [[], [], []]);
  assert.deepEqual(m.kafkaProducerSaslOptions, {});
});

test('self-monitor deleted; unknown ids ignored; input not mutated', () => {
  const snap = JSON.stringify(live);
  const ops = k.plan(live);
  assert.ok(ops.some((o) => o.op === 'delete' && o.id === 23));
  assert.ok(!ops.some((o) => o.op === 'edit' && o.id === 2));
  assert.equal(JSON.stringify(live), snap);
});
