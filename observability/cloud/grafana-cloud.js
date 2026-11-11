// Grafana Cloud watchdog setup — paste into the browser console on yangjeep.grafana.net
// while logged in as admin, or load in Node for tests (pure helpers are exported).
// Default is a dry run. Set `globalThis.CLOUD_APPLY = true` first to apply. Idempotent.
//
// Out-of-band receiver: `homelab-oob-telegram` once the user creates it (bot token and
// chat id are entered in the UI, never here). Until then the oob route falls back to
// Hermes Critical, which cannot page during a full home outage.

const PROM_DS = 'grafanacloud-prom';
const FOLDER_UID = 'homelab-cloud';
const RULE_GROUP = 'homelab-cloud-watchdog';
const OOB_RECEIVER = 'homelab-oob-telegram';
const OOB_FALLBACK = 'Homelab Hermes Critical';
const INGRESS_JOB = 'homelab-ingress';
const FED = 'source="homelab-federate"';

// ---------- pure helpers (unit tested) ----------

function promQuery(expr, seconds) {
  return {
    refId: 'A', datasourceUid: PROM_DS, relativeTimeRange: { from: seconds, to: 0 },
    model: { refId: 'A', expr, instant: true },
  };
}

function threshold(type, value) {
  return {
    refId: 'C', datasourceUid: '__expr__', relativeTimeRange: { from: 0, to: 0 },
    model: { refId: 'C', type: 'threshold', expression: 'A', conditions: [{ evaluator: { type, params: [value] } }] },
  };
}

function rule(folderUID, { uid, title, expr, window, cmp, value, noData, summary }) {
  return {
    uid, title, folderUID, ruleGroup: RULE_GROUP, condition: 'C', for: '5m',
    data: [promQuery(expr, window), threshold(cmp, value)],
    noDataState: noData, execErrState: 'Error',
    labels: { severity: 'critical', subsystem: 'watchdog', oob: 'true' },
    annotations: { summary },
  };
}

function deadmanRule(folderUID) {
  return rule(folderUID, {
    uid: 'hl-cloud-federate-deadman', title: 'P1 · Homelab metrics stopped arriving',
    expr: `absent_over_time(up{job="prometheus",${FED}}[10m])`, window: 900, cmp: 'gt', value: 0,
    noData: 'OK', summary: 'No federated Prometheus samples for 10m: Alloy LXC, Prometheus .216 or home uplink is down.',
  });
}

function homeUnreachableRule(folderUID) {
  return rule(folderUID, {
    uid: 'hl-cloud-home-unreachable', title: 'P1 · Homelab unreachable from internet',
    expr: `max(max_over_time(probe_success{job="${INGRESS_JOB}"}[5m]))`, window: 600, cmp: 'lt', value: 1,
    noData: 'Alerting', summary: 'Every Synthetics ingress check failed for 5m: home internet, Cloudflare tunnel or power is down.',
  });
}

function withOobRoute(tree, receiver) {
  const isOob = (r) => JSON.stringify(r.object_matchers) === JSON.stringify([['oob', '=', 'true']]);
  const rest = (tree.routes || []).filter((r) => !isOob(r));
  const oob = { receiver, object_matchers: [['oob', '=', 'true']], group_by: ['alertname'], group_wait: '30s', repeat_interval: '1h' };
  return { ...tree, routes: [oob, ...rest] };
}

function panel(id, type, title, expr, gridPos, extra = {}) {
  return {
    id, type, title, gridPos, datasource: { type: 'prometheus', uid: PROM_DS },
    targets: [{ refId: 'A', datasource: { type: 'prometheus', uid: PROM_DS }, expr, instant: type !== 'timeseries' }],
    ...extra,
  };
}

function externalDashboard() {
  return {
    uid: 'homelab-external-cloud', title: 'Homelab · External View', tags: ['homelab', 'cloud', 'watchdog'],
    description: 'Cloud-only view: Synthetics ingress checks plus federated snapshot. Keeps working when home is down.',
    time: { from: 'now-6h', to: 'now' }, refresh: '1m', schemaVersion: 39,
    panels: [
      panel(1, 'stat', 'Home reachable (Synthetics)', `max(probe_success{job="${INGRESS_JOB}"})`, { x: 0, y: 0, w: 6, h: 4 }),
      panel(2, 'stat', 'Federation age', `time() - max(timestamp(up{job="prometheus",${FED}}))`, { x: 6, y: 0, w: 6, h: 4 },
        { fieldConfig: { defaults: { unit: 's', thresholds: { mode: 'absolute', steps: [{ color: 'green', value: null }, { color: 'red', value: 300 }] } }, overrides: [] } }),
      panel(3, 'stat', 'Local targets down', `count(up{${FED}} == 0) or vector(0)`, { x: 12, y: 0, w: 6, h: 4 }),
      panel(4, 'stat', 'Local alerts firing', `count(ALERTS{${FED}}) or vector(0)`, { x: 18, y: 0, w: 6, h: 4 }),
      panel(5, 'timeseries', 'Ingress probe success', `probe_success{job="${INGRESS_JOB}"}`, { x: 0, y: 4, w: 24, h: 8 }),
      panel(6, 'table', 'Down targets (last federated)', `up{${FED}} == 0`, { x: 0, y: 12, w: 12, h: 8 }),
      panel(7, 'table', 'Firing local alerts (last federated)', `ALERTS{${FED}}`, { x: 12, y: 12, w: 12, h: 8 }),
    ],
  };
}

// ---------- browser runner ----------

async function api(method, path, body) {
  const res = await fetch(path, {
    method, headers: { 'Content-Type': 'application/json', 'X-Disable-Provenance': 'true' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : null;
}

async function run() {
  const APPLY = globalThis.CLOUD_APPLY === true;
  const plan = [];
  const step = async (desc, fn) => { plan.push(desc); if (APPLY) await fn(); };

  const cps = await api('GET', '/api/v1/provisioning/contact-points');
  const receiver = cps.some((c) => c.name === OOB_RECEIVER) ? OOB_RECEIVER : OOB_FALLBACK;
  if (receiver !== OOB_RECEIVER) plan.push(`WARN ${OOB_RECEIVER} missing; oob route uses ${OOB_FALLBACK}`);

  for (const r of [deadmanRule(FOLDER_UID), homeUnreachableRule(FOLDER_UID)]) {
    const exists = await fetch(`/api/v1/provisioning/alert-rules/${r.uid}`).then((x) => x.ok);
    await step(`${exists ? 'update' : 'create'} rule ${r.uid}`, () =>
      api(exists ? 'PUT' : 'POST', `/api/v1/provisioning/alert-rules${exists ? `/${r.uid}` : ''}`, r));
  }

  const tree = await api('GET', '/api/v1/provisioning/policies');
  await step(`route oob=true -> ${receiver}`, () => api('PUT', '/api/v1/provisioning/policies', withOobRoute(tree, receiver)));

  await step('upsert dashboard homelab-external-cloud', () =>
    api('POST', '/api/dashboards/db', { dashboard: externalDashboard(), folderUid: FOLDER_UID, overwrite: true }));

  return { applied: APPLY, plan };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { deadmanRule, homeUnreachableRule, withOobRoute, externalDashboard };
} else {
  run().then((r) => console.table(r.plan), (e) => console.error(e));
}
