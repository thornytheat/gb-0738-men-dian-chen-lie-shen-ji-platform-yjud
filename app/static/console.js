import {accounts, cases, chart, element, matrix, money, outcomes, reason} from './figures.js';
import {details} from './details.js';

const get = id => document.getElementById(id);
const form = get('audit-form');
const appeal = get('appeal-form');
const revisionForm = get('revision-form');
const revertForm = get('revert-form');
const nav = [...document.querySelectorAll('nav [data-panel]')];
const state = {snapshot: null, panel: null, preview: null, token: 0, filter: null, running: false, saving: false,
  lastRequest: null, lastRevision: null, lastRevert: null};
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

function fillRevisions() {
  const show = state.panel === 'revisions' && !!state.snapshot;
  const pending = (state.snapshot?.penalties.rows || []).filter(row => row.status === 'PENDING' && row.reason !== 'VISIT_MISSING');
  const box = get('revision-key');
  const selected = box.value;
  revisionForm.hidden = !show || !pending.length;
  box.replaceChildren(...pending.map(row => new Option(`${row.key}（${reason(row.reason)}）`, row.key)));
  if (pending.some(row => row.key === selected)) box.value = selected;
  const applied = (state.snapshot?.revisions.revisions || []).filter(row => row.status === 'APPLIED');
  const number = get('revert-number');
  const kept = number.value;
  revertForm.hidden = !show || !applied.length;
  number.replaceChildren(...applied.map(row => new Option(
    `#${row.revision} · ${row.changes.map(change => change.key).join('、')}`, row.revision)));
  if (applied.some(row => String(row.revision) === kept)) number.value = kept;
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
    filter: state.filter, run_id: state.snapshot?.manifest.run_id});
  fillAppeals();
  fillRevisions();
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
  get('stat-net').textContent = money(snapshot.revisions.ledger.net_cents);
  get('matrix-meta').textContent = `${snapshot.coverage.selected} 柜`;
  get('gap-meta').textContent = `${snapshot.coverage.verified} / ${snapshot.coverage.target} 已核`;
  get('cases-meta').textContent = `${snapshot.settlement.counts.VIOLATION} 笔违规`;
  get('account-meta').textContent = snapshot.revisions.count
    ? `含 ${snapshot.revisions.applied} 笔补交修订 · 勾稽通过`
    : (snapshot.appeals.balanced ? '勾稽通过 · 元' : '待勾稽');
  get('run-meta').textContent = `${localTime.format(new Date(snapshot.manifest.created_at))} · UTC+08:00 · ${snapshot.manifest.rule_version}`;
  get('run-feedback').textContent = snapshot.reused ? '已复用巡检批次 · 对账通过' : '巡检完成 · 对账通过';
  const link = get('export');
  link.href = `/api/appeals/${snapshot.manifest.run_id}/export`;
  link.removeAttribute('aria-disabled');
  matrix(get('matrix'), snapshot);
  chart(get('gap'), snapshot.coverage.strata);
  cases(get('cases'), snapshot.penalties.rows);
  accounts(get('account'), snapshot);
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
  if (state.snapshot || section === 'appeals' || section === 'revisions' || !form.reportValidity()) return;
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

const readFile = file => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onerror = () => reject(new Error('照片读取失败，请重试。'));
  reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
  reader.readAsDataURL(file);
});

async function refreshRun(runId) {
  const data = await json(`/api/settlement/runs/${runId}`);
  syncDashboard(data);
}

revisionForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (state.running || state.saving) return;
  state.saving = true;
  const button = get('save-revision');
  button.disabled = true;
  const run = state.snapshot.manifest.run_id;
  try {
    const fields = new FormData(revisionForm);
    const observations = [];
    if (fields.get('complete')) observations.push({kind: 'COMPLETE'});
    for (const index of [1, 2, 3]) {
      const sku = (fields.get(`sku${index}`) || '').trim();
      if (!sku) continue;
      const facings = Number(fields.get(`facings${index}`));
      const price = Number(fields.get(`price${index}`));
      if (!facings || !(price > 0)) throw new Error(`商品${index}须填写排面与价签。`);
      observations.push({kind: 'ITEM', sku, facings, price_cents: Math.round(price * 100)});
    }
    if (!observations.length) throw new Error('请至少填写一行清点记录。');
    const file = get('revision-file').files[0];
    let photo = null;
    if (file) {
      if (file.size > 131072) throw new Error('照片超过 128 KB 上限。');
      const photoId = (fields.get('photo_id') || '').trim();
      if (!photoId || !fields.get('captured')) throw new Error('选择照片后须填写照片编号与拍摄时间。');
      photo = {photo: photoId, file: file.name, captured: fields.get('captured'), content_base64: await readFile(file)};
    }
    const body = {items: [{key: fields.get('key'), photo, observations}],
      actor: fields.get('actor'), note: fields.get('note')};
    const fingerprint = `${run}/${JSON.stringify(body)}`;
    if (state.lastRevision?.fingerprint !== fingerprint) state.lastRevision = {fingerprint, id: crypto.randomUUID()};
    await send(`/api/revisions/${run}`, {...body, request_id: state.lastRevision.id});
    await refreshRun(run);
    note('revision-feedback', '补交修订已留存，勾稽通过。');
    get('run-feedback').textContent = '补交修订已留存 · 对账通过';
    revisionForm.reset();
  } catch (error) {
    note('revision-feedback', error.message, true);
    await refreshRun(run).catch(() => {});
  } finally {
    state.saving = false;
    button.disabled = false;
  }
});

revertForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (state.running || state.saving) return;
  state.saving = true;
  const button = get('save-revert');
  button.disabled = true;
  const run = state.snapshot.manifest.run_id;
  try {
    const fields = new FormData(revertForm);
    const body = {actor: fields.get('actor'), note: fields.get('note')};
    const fingerprint = `${run}/revert/${fields.get('number')}/${JSON.stringify(body)}`;
    if (state.lastRevert?.fingerprint !== fingerprint) state.lastRevert = {fingerprint, id: crypto.randomUUID()};
    await send(`/api/revisions/${run}/${fields.get('number')}/revert`, {...body, request_id: state.lastRevert.id});
    await refreshRun(run);
    note('revert-feedback', '已恢复原批次结论。');
    get('run-feedback').textContent = '修订已恢复 · 原批次不变';
    revertForm.reset();
  } catch (error) {
    note('revert-feedback', error.message, true);
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
