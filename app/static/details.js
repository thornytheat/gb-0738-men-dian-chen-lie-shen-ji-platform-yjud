import {element, flag, money, reason, outcomes, names} from './figures.js';

const raw = origin => origin?.raw.join(' | ');
const source = origin => origin?.id;

function table(columns, values) {
  if (!values.length) return element('p', '当前没有记录。', 'empty');
  const box = element('div', null, 'table-scroll');
  const tab = element('table', null, 'records-table');
  const head = tab.createTHead().insertRow();
  for (const [heading, local] of columns) {
    const label = element('th', heading, local);
    label.scope = 'col';
    head.append(label);
  }
  const body = tab.createTBody();
  for (const record of values) {
    const line = body.insertRow();
    for (const [index, value] of record.entries()) {
      const cell = line.insertCell();
      cell.className = columns[index][1] || '';
      if (value instanceof Node) cell.append(value);
      else cell.textContent = value ?? '—';
      if (cell.classList.contains('clip')) cell.title = cell.textContent;
    }
  }
  box.append(tab);
  return box;
}

const group = (root, title, child) => root.append(element('h3', title), child);

function quarantine(root, entries) {
  group(root, '原件隔离', table([['源行'], ['原因码'], ['原因'], ['录入原值', 'clip']],
    entries.map(row => [source(row.source), row.reason, reason(row.reason), raw(row.source)])));
}

function intake(root, payload) {
  root.append(table([['档件'], ['编码'], ['状态'], ['记录数', 'num'], ['空行', 'num'], ['重复表头', 'num']],
    Object.values(payload.tables).map(row => [row.name, row.encoding, flag(row.state), row.input, row.blank, row.repeated_headers])));
  group(root, '采信巡检时间', table([['巡检'], ['门店'], ['UTC 时间'], ['源行'], ['原值', 'clip']],
    payload.visits.map(row => [row.visit, row.store, row.at_utc, source(row.source), raw(row.source)])));
  quarantine(root, payload.quarantine);
}

function plans(root, payload) {
  root.append(table([['柜位'], ['巡检时刻 UTC'], ['生效版'], ['应陈商品'], ['重叠候选'], ['原因'], ['源行']],
    payload.decisions.map(row => [`${row.store}:${row.slot}`, row.visit?.at_utc, row.plan?.plan, row.plan?.sku,
      row.candidates.map(item => item.plan).join(' / '), reason(row.reason), source(row.plan?.source) || source(row.roster_source)])));
  group(root, '商品旧名', table([['旧名'], ['归并编号']], Object.entries(payload.aliases)));
  group(root, '替代巡检', table([['门店'], ['已替代'], ['采信'], ['源行']],
    payload.replaced_visits.map(row => [row.store, row.inactive_visit, row.active_visit, source(row.source)])));
  quarantine(root, payload.quarantine);
}

function thumbnail(row, dataset) {
  const link = element('a', null, 'image-link');
  link.href = `/api/photos/original/${dataset}/${encodeURIComponent(row.file)}/${row.sha256}`;
  link.target = '_blank';
  link.rel = 'noopener';
  const image = element('img');
  image.alt = '';
  image.loading = 'lazy';
  image.src = link.href;
  link.append(image, element('span', row.photo));
  return link;
}

function photos(root, payload, dataset) {
  root.append(table([['原件'], ['巡检'], ['柜位'], ['SHA-256', 'clip'], ['拍摄 UTC'], ['源行']], payload.photos.map(row => [
    thumbnail(row, dataset), row.visit, row.slot, row.sha256, row.captured_utc, source(row.source),
  ])));
  group(root, '复用照片', table([['同图摘要', 'clip'], ['跨柜绑定'], ['原始行']], payload.reused_groups.map(row => [
    row.sha256, row.bindings.map(binding => binding.join(':')).join(' / '), row.sources.join(' / '),
  ])));
  quarantine(root, payload.quarantine);
}

function coverage(root, payload) {
  root.append(table([['店组'], ['权重', 'num'], ['目标', 'num'], ['候选', 'num'], ['入样', 'num'], ['已核', 'num'], ['待证', 'num'],
    ['隔离', 'num'], ['缺额', 'num'], ['有效缺口', 'num']], payload.strata.map(row => [row.title, row.weight, row.target,
    row.pool, row.selected, row.verified, row.pending, row.isolated, row.unfilled, row.gap])));
  group(root, '抽中柜位', table([['柜位'], ['店组'], ['证据状态'], ['原因'], ['名册源行'], ['抽签摘要', 'clip']], payload.slots.map(row => [
    row.key, row.group, row.evidence_status === 'VERIFIED' ? '已核' : names[row.evidence_status], reason(row.reason), source(row.source), row.score,
  ])));
}

function penalties(root, payload, filter) {
  const rows = payload.rows.filter(row => !filter || (filter.key ? filter.key === row.key : filter.group === row.group && filter.outcome === row.status));
  root.append(table([['柜位'], ['状态'], ['原因码'], ['命中罚则与金额'], ['执行额 · 元', 'num'], ['生效版'], ['照片'], ['清点源行']],
    rows.map(row => [row.key, flag(row.status), row.reason,
      row.candidates.map(entry => `${reason(entry.code)} ${money(entry.cents)}`).join(' / ') || '—', money(row.original_cents), row.plan?.plan,
      row.evidence?.photos.map(pic => `${pic.photo} / ${source(pic.source)}`).join(' · '), row.evidence?.completed_sources.join(' / ')])));
  if (rows.length === 1) {
    const [row] = rows;
    const products = row.evidence?.products || {};
    group(root, `${row.key} 清点商品`, table([['应陈商品'], ['实陈商品'], ['排面', 'num'], ['价签 · 元', 'num'], ['来源']],
      Object.entries(products).map(([key, item]) => [row.plan?.sku, key, item.facings, money(item.price_cents), item.sources.join(' / ')])));
  }
}

function settlement(root, payload) {
  root.append(table([['店组'], ...outcomes.map(key => [names[key], 'num']), ['原罚额 · 元', 'num']], payload.strata.map(row => [
    row.code, ...outcomes.map(key => row.counts[key]), money(row.original_cents),
  ])));
  group(root, '原件行数勾稽', table([['档件'], ['输入', 'num'], ['采信', 'num'], ['隔离', 'num'], ['空行', 'num'], ['表头', 'num']],
    Object.entries(payload.sources).map(([file, row]) => [file, row.input, row.accepted, row.isolated, row.blank, row.repeated_headers])));
  quarantine(root, payload.quarantine);
}

function appeals(root, payload) {
  root.append(table([['柜位'], ['状态'], ['原罚额 · 元', 'num'], ['减免 · 元', 'num'], ['净罚额 · 元', 'num'], ['版本', 'num']],
    payload.rows.map(row => [row.key, flag(row.status), money(row.original_cents), money(row.reduction_cents), money(row.net_cents), row.version])));
  group(root, '异议时间线', table([['柜位'], ['动作'], ['经办人'], ['依据编号', 'clip'], ['说明', 'clip'], ['UTC 时间'], ['原罚则'], ['陈列源行']],
    payload.events.map(row => [row.key, flag(row.status), row.actor, row.evidence_ref, row.note, row.created_at, row.original_rule, row.plan_source])));
}

export function details(root, key, payload, options) {
  root.replaceChildren();
  if (!payload) {
    root.append(element('p', '先运行审计。', 'empty'));
    return;
  }
  if (key === 'photos') photos(root, payload, options.dataset);
  else if (key === 'penalties') penalties(root, payload, options.filter);
  else ({intake, plans, coverage, settlement, appeals})[key](root, payload);
}
