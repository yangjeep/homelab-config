// Grafana homelab revamp — paste into the browser console on the Grafana origin
// while logged in as admin, or load in Node for tests (pure helpers are exported).
// Default is a dry run that only prints the plan. Set `globalThis.REVAMP_APPLY = true` first to apply.
// Idempotent: re-running converges to the same state. Nothing is deleted except the
// unused duplicate Loki datasource; replaced dashboards move to the archive folder
// (Grafana version history also keeps every prior revision).

const PROM = { type: 'prometheus', uid: 'homelab-prometheus' };

const FOLDERS = {
  home: { uid: 'hl-00-home', title: '00 · 总览' },
  sub: { uid: 'hl-10-subsystems', title: '10 · 子系统' },
  meta: { uid: 'hl-90-meta', title: '90 · Meta 与日志' },
  archive: { uid: 'hl-99-archive', title: '99 · 归档（旧版，可回滚）' },
};

// Triage components as emitted by the homelab-triage recording rules.
const COMPONENTS = [
  ['TrueNAS', 'TrueNAS'],
  ['UniFi / WAN', 'UniFi / WAN'],
  ['PVE', 'PVE'],
  ['家庭服务', 'Home Assistant'],
  ['供电', 'UPS'],
  ['Pi', 'Raspberry Pi'],
  ['入口', 'Caddy / Cloudflared'],
  ['监控', '监控链'],
];

// Merged subsystem boards: new uid -> title, folder, sources (each becomes a row).
const MERGES = [
  { uid: 'sub-network', title: '网络 · WAN 与 UniFi', folder: 'sub',
    sources: ['network-wan', 'network-unifi', 'unifi-udm-se-cooling'] },
  { uid: 'sub-compute', title: '计算 · Proxmox 与 IPMI', folder: 'sub',
    sources: ['infra-proxmox', 'hardware-asrockrack-ipmi'] },
  { uid: 'sub-home', title: '家庭 · Home Assistant 与环境', folder: 'sub',
    sources: ['home-assistant', 'ha-automation-runs-20261005', 'home-environment-20261005'] },
  { uid: 'meta-observability', title: 'Meta · 监控链健康与覆盖', folder: 'meta',
    sources: ['observability-health', 'observability-coverage'] },
];

// Kept boards: moved and retitled in place (uid unchanged so existing links work).
const KEEP = [
  ['edge-services', '入口 · Caddy 与 Cloudflared', 'sub'],
  ['storage-truenas', '存储 · TrueNAS', 'sub'],
  ['power-ups', '供电 · UPS', 'sub'],
  ['media-pipeline', '媒体 · 下载与播放', 'sub'],
  ['radio-piaware', '无线电 · PiAware ADS-B', 'sub'],
  ['homelab-apps-script', '自动化 · Apps Script', 'sub'],
  ['ai-control-plane', 'AI · Hermes 控制面', 'meta'],
  ['logs-homelab', '日志 · 全局', 'meta'],
];

// Superseded overview-style boards, archived as-is.
const ARCHIVE_ONLY = ['homelab-overview-local', 'homelab-noc', 'availability-services'];

const DUP_LOKI_UID = 'bfuxd8vdf02kga';
const HOME_UID = 'homelab-home';
const NAV_LINK = { title: '子系统', type: 'dashboards', tags: ['homelab'], asDropdown: true, keepTime: true };

// ---------- pure helpers (unit tested) ----------

// Per-series score: critical 3 > unknown 2 > warning 1 > ok 0.
// Raw triage values: 0 ok, 1 warning, 2 critical, 3 unknown.
function scoreExpr(sel) {
  const s = `homelab_triage_state${sel}`;
  return `(${s} == bool 2) * 3 + (${s} == bool 3) * 2 + (${s} == bool 1)`;
}

// Component status without hard-coded signal counts: signals seen in the last 24h
// but absent now count as unknown (2); no signals at all also yields unknown.
function componentExpr(component) {
  const sel = `{component="${component}"}`;
  const now = `count(homelab_triage_state${sel})`;
  const seen = `count(last_over_time(homelab_triage_state${sel}[1d]))`;
  return `max(label_replace(max(${scoreExpr(sel)}) or on() vector(2), "k", "a", "", "")` +
    ` or label_replace(2 * (${seen} > bool (${now} or on() vector(0))), "k", "b", "", ""))`;
}

const STATUS_MAPPINGS = [{
  type: 'value',
  options: {
    0: { text: '正常', color: 'green', index: 0 },
    1: { text: '警告', color: 'yellow', index: 1 },
    2: { text: '未知 / 过期', color: 'blue', index: 2 },
    3: { text: '严重', color: 'red', index: 3 },
  },
}];

const COUNT_DEFAULTS = { mappings: [], thresholds: { mode: 'absolute',
  steps: [{ color: 'green', value: null }, { color: 'red', value: 1 }] } };

function query(expr, extra = {}) {
  return [{ refId: 'A', datasource: PROM, expr, instant: true, ...extra }];
}

function stat(id, title, expr, gridPos, defaults = {}) {
  return {
    id, type: 'stat', title, datasource: PROM, gridPos, targets: query(expr),
    options: { colorMode: 'background', graphMode: 'none', textMode: 'value',
      reduceOptions: { calcs: ['lastNotNull'], fields: '', values: false } },
    fieldConfig: { defaults: { mappings: STATUS_MAPPINGS, color: { mode: 'thresholds' },
      thresholds: { mode: 'absolute', steps: [{ color: 'green', value: null }] }, ...defaults }, overrides: [] },
  };
}

function gauge(id, title, expr, gridPos) {
  return {
    id, type: 'gauge', title, datasource: PROM, gridPos, targets: query(expr),
    options: { reduceOptions: { calcs: ['lastNotNull'], fields: '', values: false } },
    fieldConfig: { defaults: { unit: 'percent', min: 0, max: 100,
      thresholds: { mode: 'absolute', steps: [
        { color: 'green', value: null }, { color: 'yellow', value: 80 }, { color: 'red', value: 90 }] } },
    overrides: [] },
  };
}

function poolUsedExpr(pool) {
  return `100 * truenas_pool_allocated_bytes{pool="${pool}"} / truenas_pool_size_bytes{pool="${pool}"}` +
    ' and on() (truenas_pool_scrape_success == 1)';
}

function buildHome() {
  const tiles = COMPONENTS.map(([c, title], i) =>
    stat(i + 1, title, componentExpr(c), { x: i * 3, y: 0, w: 3, h: 4 }));
  const alerts = {
    id: 20, type: 'alertlist', title: '正在告警', gridPos: { x: 0, y: 4, w: 12, h: 9 },
    options: { viewMode: 'list', groupMode: 'default', maxItems: 20, sortOrder: 1, dashboardAlerts: false,
      alertName: '', alertInstanceLabelFilter: '',
      stateFilter: { firing: true, pending: true, noData: true, error: true, normal: false } },
  };
  const abnormal = {
    id: 21, type: 'table', title: '异常信号（分诊非正常项）', datasource: PROM,
    gridPos: { x: 12, y: 4, w: 12, h: 9 },
    targets: query('homelab_triage_state > 0', { format: 'table' }),
    transformations: [{ id: 'organize', options: {
      excludeByName: { Time: true, __name__: true, job: true, instance: true },
      renameByName: { component: '子系统', signal: '信号', Value: '状态' } } }],
    fieldConfig: { defaults: { mappings: [{ type: 'value', options: {
      1: { text: '警告', color: 'yellow' }, 2: { text: '严重', color: 'red' }, 3: { text: '未知', color: 'blue' } } }],
    custom: { cellOptions: { type: 'color-text' } } }, overrides: [] },
    options: { showHeader: true, footer: { show: false } },
  };
  const bottom = [
    stat(22, '服务探测失败', 'count(probe_success == 0) or on() vector(0)', { x: 0, y: 13, w: 6, h: 4 }, COUNT_DEFAULTS),
    stat(23, '采集目标掉线', 'count(up == 0) or on() vector(0)', { x: 6, y: 13, w: 6, h: 4 }, COUNT_DEFAULTS),
    gauge(24, 'main 池已用', poolUsedExpr('main'), { x: 12, y: 13, w: 6, h: 4 }),
    gauge(25, 'vm-app-nvme 池已用', poolUsedExpr('vm-app-nvme'), { x: 18, y: 13, w: 6, h: 4 }),
  ];
  return {
    uid: HOME_UID, title: 'Homelab · 总览', tags: ['homelab', 'home'], editable: true,
    refresh: '1m', time: { from: 'now-6h', to: 'now' }, timezone: 'browser', schemaVersion: 39,
    links: [NAV_LINK, { title: 'Uptime Kuma', type: 'link', url: 'https://kuma-home.yangjeep.net/', targetBlank: true }],
    panels: [...tiles, alerts, abnormal, ...bottom],
  };
}

// Flatten collapsed rows; drop explanatory text panels and source row headers.
function flattenPanels(panels) {
  return (panels || [])
    .flatMap((p) => (p.type === 'row' ? p.panels || [] : [p]))
    .filter((p) => p.type !== 'text');
}

// Concatenate sources into one board: one row per source, first row expanded,
// later rows collapsed (their panels nested, as Grafana stores collapsed rows).
function mergeDashboards(merge, sources) {
  const panels = [];
  let y = 0;
  let id = 1;
  sources.forEach((src, i) => {
    const kids = flattenPanels(src.panels);
    const top = kids.length ? Math.min(...kids.map((p) => p.gridPos?.y ?? 0)) : 0;
    const rowY = y;
    const moved = kids.map((p) => ({ ...p, id: id++,
      gridPos: { ...p.gridPos, y: (p.gridPos?.y ?? 0) - top + rowY + 1 } }));
    const row = { id: id++, type: 'row', title: src.title, collapsed: i > 0, gridPos: { x: 0, y: rowY, w: 24, h: 1 } };
    if (i > 0) {
      panels.push({ ...row, panels: moved });
      y = rowY + 1;
      return;
    }
    panels.push({ ...row, panels: [] }, ...moved);
    y = Math.max(rowY + 1, ...moved.map((p) => p.gridPos.y + (p.gridPos.h || 1)));
  });
  return { uid: merge.uid, title: merge.title, tags: ['homelab'], editable: true, refresh: '1m',
    time: { from: 'now-6h', to: 'now' }, timezone: 'browser', schemaVersion: 39, links: [NAV_LINK], panels,
    templating: { list: [] }, annotations: sources[0]?.annotations ?? { list: [] } };
}

// Grafana-managed alert for service probes (takes over paging from Uptime Kuma).
function serviceProbeRule(folderUID) {
  return {
    uid: 'hl-service-probe-down', title: 'P2 · Service HTTP probe down', folderUID,
    ruleGroup: 'Homelab core', condition: 'C', for: '3m', noDataState: 'OK', execErrState: 'Error',
    labels: { severity: 'P2' },
    annotations: { summary: '{{ $labels.instance }} 探测失败超过 3 分钟',
      runbook: '先看 Kuma 同名 monitor 和对应子系统 dashboard' },
    data: [
      { refId: 'A', datasourceUid: PROM.uid, relativeTimeRange: { from: 600, to: 0 },
        model: { refId: 'A', instant: true,
          expr: 'max by (job, instance) (probe_success{job=~"blackbox-http|blackbox-edge", instance!~".*(google|cloudflare).*"} == 0)' } },
      { refId: 'C', datasourceUid: '__expr__', relativeTimeRange: { from: 0, to: 0 },
        model: { refId: 'C', type: 'threshold', expression: 'A',
          conditions: [{ evaluator: { type: 'gt', params: [-1] } }] } },
    ],
  };
}

const archivedTitle = (t) => `[旧] ${t.replace(/^\[旧\] /, '')}`;

// ---------- side-effecting runner (browser only) ----------

async function run() {
  const APPLY = globalThis.REVAMP_APPLY === true;
  const H = { 'Content-Type': 'application/json', 'X-Disable-Provenance': 'true' };
  const plan = [];
  const api = async (method, path, body) => {
    if (method !== 'GET') plan.push(`${method} ${path}`);
    if (!APPLY && method !== 'GET') return null;
    const r = await fetch(path, { method, headers: H, body: body && JSON.stringify(body) });
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`${method} ${path} -> ${r.status} ${await r.text()}`);
    return r.json().catch(() => null);
  };
  const get = (uid) => api('GET', `/api/dashboards/uid/${uid}`);
  const save = (dashboard, folder, message) =>
    api('POST', '/api/dashboards/db', { dashboard, folderUid: FOLDERS[folder].uid, overwrite: true, message });
  const withVersion = async (dash) => {
    const prev = await get(dash.uid);
    return prev ? { ...dash, version: prev.dashboard.version } : dash;
  };

  for (const f of Object.values(FOLDERS)) {
    if (!(await api('GET', `/api/folders/${f.uid}`))) await api('POST', '/api/folders', f);
  }
  for (const m of MERGES) {
    const srcs = [];
    for (const uid of m.sources) {
      const d = await get(uid);
      if (d) srcs.push(d.dashboard); else plan.push(`WARN missing source ${uid}`);
    }
    // Sources already archived by a previous run keep their original titles minus the prefix.
    const clean = srcs.map((d) => ({ ...d, title: d.title.replace(/^\[旧\] /, '') }));
    await save(await withVersion(mergeDashboards(m, clean)), m.folder, 'revamp: merged board');
    for (const d of srcs) {
      await save({ ...d, title: archivedTitle(d.title), tags: (d.tags || []).filter((t) => t !== 'homelab').concat('archived') },
        'archive', 'revamp: archived after merge');
    }
  }
  for (const [uid, title, folder] of KEEP) {
    const d = await get(uid);
    if (!d) { plan.push(`WARN missing ${uid}`); continue; }
    const tags = Array.from(new Set([...(d.dashboard.tags || []), 'homelab']));
    await save({ ...d.dashboard, title, tags }, folder, 'revamp: retitle and move');
  }
  for (const uid of ARCHIVE_ONLY) {
    const d = await get(uid);
    if (!d) continue;
    // Old boards lose the 'homelab' tag so they drop out of the navigation dropdown.
    await save({ ...d.dashboard, title: archivedTitle(d.dashboard.title),
      tags: (d.dashboard.tags || []).filter((t) => t !== 'homelab').concat('archived') }, 'archive', 'revamp: archived');
  }
  await save(await withVersion(buildHome()), 'home', 'revamp: new overview');
  await api('PATCH', '/api/org/preferences', { homeDashboardUID: HOME_UID });

  const rule = serviceProbeRule('homelab-alerts');
  const existing = await api('GET', `/api/v1/provisioning/alert-rules/${rule.uid}`);
  await api(existing ? 'PUT' : 'POST',
    existing ? `/api/v1/provisioning/alert-rules/${rule.uid}` : '/api/v1/provisioning/alert-rules', rule);

  if (await api('GET', `/api/datasources/uid/${DUP_LOKI_UID}`)) {
    await api('DELETE', `/api/datasources/uid/${DUP_LOKI_UID}`);
  }
  console.info(`${APPLY ? 'APPLIED' : 'DRY RUN'}\n${plan.join('\n')}`);
  return plan;
}

if (typeof module !== 'undefined') {
  module.exports = { componentExpr, scoreExpr, flattenPanels, mergeDashboards, buildHome,
    serviceProbeRule, COMPONENTS, MERGES, KEEP, ARCHIVE_ONLY, FOLDERS };
} else {
  run().catch((e) => console.error('revamp failed:', e));
}
