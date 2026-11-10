// Uptime Kuma (v2) homelab revamp — paste into the browser console on the Kuma origin
// while logged in, or load in Node for tests (plan() is pure and exported).
// Default is a dry run that prints the plan. Set `globalThis.REVAMP_APPLY = true` first to apply.
// Run the Grafana revamp first: it adds the "P2 · Service HTTP probe down" rule that
// takes over paging for the services whose Kuma notifications are removed here.
//
// Role after this change: Kuma = human-facing status + watchdog of the monitoring chain.
// Grafana Alerting = the only pager for anything Prometheus already probes.

const TELEGRAM = 1;
const HERMES = 2;
const PAGE = { [TELEGRAM]: true, [HERMES]: true };
const SILENT = {};

const GROUPS = ['Edge', 'Compute & Storage', 'Media', 'Home', 'Radio', 'Monitoring', 'LeaseLab (moving to cloud)'];

// id -> [new name, group, notifications]. Notifications: 'keep' | PAGE | SILENT.
// SILENT = covered by a Grafana alert rule (blackbox probe, PVE/HA/TrueNAS rules).
const SPEC = {
  1: ['Home Assistant · NUC6', 'Home', SILENT],
  2: ['PVE · EC200A', 'Compute & Storage', SILENT],
  4: ['Sense · Energy sensor', 'Home', 'keep'],
  5: ['PiAware · Pi 3B', 'Radio', 'keep'],
  6: ['TrueNAS · Xeon E-2160', 'Compute & Storage', SILENT],
  8: ['PiAware · Radio', 'Radio', 'keep'],
  9: ['PiAware · MLAT', 'Radio', 'keep'],
  10: ['Prowlarr', 'Media', SILENT],
  11: ['Radarr', 'Media', SILENT],
  12: ['Sonarr', 'Media', SILENT],
  13: ['qBittorrent', 'Media', SILENT],
  14: ['Plex', 'Media', SILENT],
  15: ['Jellyfin', 'Media', SILENT],
  16: ['Power · UPS', null, 'keep'],
  20: ['Caddy · Immich HTTPS (CT 900)', 'Edge', SILENT],
  21: ['Cloudflared · Tunnel ready (CT 800)', 'Edge', SILENT],
  22: ['LeaseLab · Production App', 'LeaseLab (moving to cloud)', 'keep'],
  24: ['LeaseLab · Vercel diagnostic alias', 'LeaseLab (moving to cloud)', 'keep'],
  25: ['LeaseLab · Website', 'LeaseLab (moving to cloud)', 'keep'],
  26: ['LeaseLab · Rent with Alda storefront', 'LeaseLab (moving to cloud)', 'keep'],
};

// Kuma probing itself is meaningless; external probing belongs to the cloud phase.
const DELETE = [23];

const WATCHDOGS = [
  ['Monitoring · Prometheus', 'http://192.168.253.216:9090/-/healthy'],
  ['Monitoring · Grafana', 'http://192.168.253.228:3000/api/health'],
  ['Monitoring · Loki', 'http://192.168.253.218:3100/ready'],
  ['Monitoring · InfluxDB', 'http://192.168.253.235:8086/health'],
];

const MIN_RETRIES = 2;
const RETRY_INTERVAL = 30;

function httpMonitor(name, url) {
  return { type: 'http', name, url, method: 'GET', interval: 60, retryInterval: RETRY_INTERVAL,
    maxretries: MIN_RETRIES, timeout: 10, accepted_statuscodes: ['200-299'], maxredirects: 10,
    notificationIDList: { ...PAGE }, ignoreTls: false, upsideDown: false, active: true,
    // Kuma 2 rejects inserts without these (NOT NULL JSON columns).
    conditions: [], kafkaProducerBrokers: [], kafkaProducerSaslOptions: {}, rabbitmqNodes: [] };
}

// Pure: live monitor list -> ordered ops. Groups first so later ops can resolve parents.
function plan(monitors) {
  const ops = GROUPS.map((name) => ({ op: 'ensureGroup', name }));
  for (const m of monitors) {
    if (DELETE.includes(m.id)) { ops.push({ op: 'delete', id: m.id, name: m.name }); continue; }
    const spec = SPEC[m.id];
    if (!spec) continue;
    const [name, group, notif] = spec;
    const patch = { name };
    if (m.type !== 'group' && (m.maxretries ?? 0) < MIN_RETRIES) {
      patch.maxretries = MIN_RETRIES;
      patch.retryInterval = RETRY_INTERVAL;
    }
    if (notif !== 'keep') patch.notificationIDList = { ...notif };
    ops.push({ op: 'edit', id: m.id, group, patch });
  }
  for (const [name, url] of WATCHDOGS) {
    ops.push({ op: 'ensureMonitor', group: 'Monitoring', monitor: httpMonitor(name, url) });
  }
  return ops;
}

// ---------- side-effecting runner (browser only) ----------

async function run() {
  const APPLY = globalThis.REVAMP_APPLY === true;
  const root = document.querySelector('#app').__vue_app__._container._vnode.component.proxy;
  const socket = root.getSocket();
  const call = (event, ...args) => new Promise((resolve, reject) => {
    socket.emit(event, ...args, (res) => (res && res.ok ? resolve(res) : reject(new Error(`${event}: ${res?.msg}`))));
  });
  const byName = () => Object.fromEntries(Object.values(root.monitorList).map((m) => [m.name, m]));
  const log = [];
  const ops = plan(Object.values(root.monitorList));

  for (const o of ops) {
    if (o.op === 'ensureGroup') {
      if (byName()[o.name]) continue;
      log.push(`add group ${o.name}`);
      if (APPLY) await call('add', { ...httpMonitor(o.name, 'https://'), type: 'group', notificationIDList: {} });
    } else if (o.op === 'delete') {
      log.push(`delete #${o.id} ${o.name}`);
      if (APPLY) await call('deleteMonitor', o.id);
    } else if (o.op === 'edit') {
      log.push(`edit #${o.id} ${JSON.stringify(o.patch)}${o.group ? ` -> ${o.group}` : ''}`);
      if (!APPLY) continue;
      const groupId = o.group ? byName()[o.group]?.id : undefined;
      const { monitor } = await call('getMonitor', o.id);
      await call('editMonitor', { ...monitor, ...o.patch, ...(o.group ? { parent: groupId ?? null } : {}) });
    } else if (o.op === 'ensureMonitor') {
      if (byName()[o.monitor.name]) continue;
      log.push(`add ${o.monitor.name} ${o.monitor.url}`);
      if (APPLY) await call('add', { ...o.monitor, parent: byName()[o.group]?.id ?? null });
    }
    // Let monitorList refresh after writes so group ids resolve.
    if (APPLY) await new Promise((r) => setTimeout(r, 400));
  }
  console.info(`${APPLY ? 'APPLIED' : 'DRY RUN'}\n${log.join('\n')}`);
  return log;
}

if (typeof module !== 'undefined') {
  module.exports = { plan, SPEC, GROUPS, WATCHDOGS, DELETE };
} else {
  run().catch((e) => console.error('kuma revamp failed:', e));
}
