import {accounts, cases, chart, element, matrix, money, outcomes} from './figures.js';
import {details} from './details.js';

const get = id => document.getElementById(id);
const form = get('audit-form');
const appeal = get('appeal-form');
const nav = [...document.querySelectorAll('nav [data-panel]')];
const state = {snapshot: null, panel: null, preview: null, token: 0, filter: null, running: false, saving: false, lastRequest: null};
const localTime = new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'medium'});

async function json(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error('暂时无法连接，请重试。');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail?.message || '操作失败，请重试。');
  }
  return response.json();
}

const send = (url, body) => json(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
const options = () => ({dataset: get('dataset').value, sample_size: Number(get('sample-size').value)});

function note(id, message, problem = false) {
  const node = get(id);
  node.hidden = !message;
  node.textContent = message || '';
  node.classList.toggle('error', problem);
}

function updateActions() {
  const action = get('appeal-action');
  const previous = action.value;
  const current = state.snapshot?.appeals.rows.find(row => row.key === get('appeal-key').value);
  const available = current?.status === 'OPEN' ? [['UPHELD', '维持原罚'], ['WAIVED', '全额免除'], ['REDUCED', '部分减免']]
    : [['OPEN', '发起异议']];
  action.replaceChildren(...available.map(([value, label]) => new Option(label, value)));
  if (available.some(([value]) => value === previous)) action.value = previous;
  get('appeal-reduction').max = current ? current.original_cents - 1 : 0;
  updateReduction();
}

function updateReduction() {
  const enabled = get('appeal-action').value === 'REDUCED';
  get('reduction-field').hidden = !enabled;
  get('appeal-reduction').required = enabled;
  get('appeal-reduction').disabled = !enabled;
}

function fillAppeals() {
  const choices = (state.snapshot?.appeals.rows || []).filter(row => row.status === 'NONE' || row.status === 'OPEN');
  const box = get('appeal-key');
  const selected = box.value;
  appeal.hidden = state.panel !== 'appeals' || !choices.length;
  box.replaceChildren(...choices.map(row => new Option(row.key, row.key)));
  if (choices.some(row => row.key === selected)) box.value = selected;
  updateActions();
}

function refreshDetails() {
  if (!state.panel) return;
  get('detail').hidden = false;
  const link = nav.find(link => link.dataset.panel === state.panel);
  for (const item of nav) {
    if (item === link) item.setAttribute('aria-current', 'location');
    else item.removeAttribute('aria-current');
  }
  get('detail-title').textContent = link.textContent.trim();
  get('clear-filter').hidden = !state.filter;
  const payload = state.snapshot?.[state.panel] || state.preview;
  details(get('detail-body'), state.panel, payload, {dataset: state.snapshot?.manifest.parameters.dataset || options().dataset,
    filter: state.filter});
  fillAppeals();
}

function syncDashboard(snapshot) {
  state.token++;
  state.snapshot = snapshot;
  state.preview = null;
  get('campaign').textContent = snapshot.campaign.title;
  get('batch-stamp').textContent = `${snapshot.manifest.version} / ${snapshot.manifest.run_id.slice(0, 12)}`;
  get('batch-stamp').title = snapshot.manifest.run_id;
  get('stat-selected').textContent = snapshot.settlement.selected;
  for (const status of outcomes) get(`stat-${status.toLowerCase()}`).textContent = snapshot.settlement.counts[status];
  get('stat-net').textContent = money(snapshot.appeals.net_cents);
  get('matrix-meta').textContent = `${snapshot.coverage.selected} 柜`;
  get('gap-meta').textContent = `${snapshot.coverage.verified} / ${snapshot.coverage.target} 已核`;
  get('cases-meta').textContent = `${snapshot.settlement.counts.VIOLATION} 笔违规`;
  get('account-meta').textContent = snapshot.appeals.balanced ? '勾稽通过 · 元' : '待勾稽';
  get('run-meta').textContent = `${localTime.format(new Date(snapshot.manifest.created_at))} · UTC+08:00 · ${snapshot.manifest.rule_version}`;
  get('run-feedback').textContent = snapshot.reused ? '已复用巡检批次 · 对账通过' : '巡检完成 · 对账通过';
  const link = get('export');
  link.href = `/api/appeals/${snapshot.manifest.run_id}/export`;
  link.removeAttribute('aria-disabled');
  matrix(get('matrix'), snapshot);
  chart(get('gap'), snapshot.coverage.strata);
  cases(get('cases'), snapshot.penalties.rows);
  accounts(get('account'), snapshot.appeals);
  refreshDetails();
}

async function openPanel(section, filter = null, focus = true) {
  state.panel = section;
  state.filter = filter;
  state.preview = null;
  const token = ++state.token;
  note('appeal-feedback', null);
  refreshDetails();
  if (focus) {
    history.replaceState(null, '', `#${section}`);
    get('detail-title').focus({preventScroll: true});
    get('detail').scrollIntoView({block: 'start'});
  }
  if (state.snapshot || section === 'appeals' || !form.reportValidity()) return;
  get('detail-body').replaceChildren(element('p', '正在读取档件。', 'empty'));
  try {
    const result = await json(`/api/${section}?${new URLSearchParams(options())}`);
    if (token !== state.token) return;
    state.preview = result;
    refreshDetails();
  } catch (error) {
    if (token === state.token) get('detail-body').replaceChildren(element('p', error.message, 'feedback'));
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (state.running || state.saving) return;
  state.running = true;
  get('run').disabled = true;
  note('run-error', null);
  get('run-feedback').textContent = '审计运行中…';
  try {
    const snapshot = await send('/api/settlement/runs', options());
    state.filter = null;
    syncDashboard(snapshot);
    get('run').textContent = '重跑审计';
  } catch (error) {
    note('run-error', error.message, true);
    get('run-feedback').textContent = '运行失败 · 可重试';
  } finally {
    state.running = false;
    get('run').disabled = false;
  }
});

appeal.addEventListener('submit', async event => {
  event.preventDefault();
  if (state.running || state.saving) return;
  state.saving = true;
  const button = get('save-appeal');
  button.disabled = true;
  const run = state.snapshot.manifest.run_id;
  const fields = new FormData(appeal);
  const selected = state.snapshot.appeals.rows.find(row => row.key === fields.get('key'));
  const body = Object.fromEntries(fields);
  if (body.reduction_cents) body.reduction_cents = Number(body.reduction_cents);
  body.expected_version = selected.version;
  const fingerprint = `${run}/${JSON.stringify(body)}`;
  if (state.lastRequest?.fingerprint !== fingerprint) state.lastRequest = {fingerprint, id: crypto.randomUUID()};
  try {
    await send(`/api/appeals/${run}/events`, {...body, request_id: state.lastRequest.id});
    const data = await json(`/api/settlement/runs/${run}`);
    syncDashboard(data);
    note('appeal-feedback', '复核事件已留存。');
    get('run-feedback').textContent = '复核事件已留存 · 对账通过';
    get('appeal-note').value = '';
    get('appeal-evidence').value = '';
    get('appeal-reduction').value = '';
  } catch (error) {
    note('appeal-feedback', error.message, true);
  } finally {
    state.saving = false;
    button.disabled = false;
  }
});

for (const link of nav) link.addEventListener('click', event => {
  event.preventDefault();
  openPanel(link.dataset.panel);
});
get('clear-filter').addEventListener('click', () => openPanel('penalties'));
get('matrix').addEventListener('click', event => {
  const cell = event.target.closest('[data-outcome]');
  if (cell) openPanel('penalties', {group: cell.dataset.group, outcome: cell.dataset.outcome});
});
get('cases').addEventListener('click', event => {
  const button = event.target.closest('[data-key]');
  if (button) openPanel('penalties', {key: button.dataset.key});
});
get('appeal-key').addEventListener('change', updateActions);
get('appeal-action').addEventListener('change', updateReduction);
form.addEventListener('change', () => { if (state.panel && !state.snapshot) openPanel(state.panel, null, false); });
const section = nav.find(link => link.hash === location.hash);
if (section) openPanel(section.dataset.panel, null, false);
