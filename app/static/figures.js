export const outcomes = ['COMPLIANT', 'VIOLATION', 'PENDING', 'ISOLATED'];
export const names = {COMPLIANT: '合规', VIOLATION: '违规', PENDING: '待证', ISOLATED: '隔离', BALANCED: '已勾稽',
  OPEN: '已受理', UPHELD: '维持原罚', WAIVED: '全额免除', REDUCED: '部分减免', NONE: '未发起',
  APPLIED: '已生效', FAILED: '未生效', REVERTED: '已恢复',
  RECEIVED: '已收件', EMPTY_FILE: '空档', BLANK_FILE: '空行档', HEADER_ONLY: '仅表头'};
const dictionary = JSON.parse(document.getElementById('reason-map').textContent);
export const reason = code => code ? dictionary[code] || code : '—';
export const money = cents => (cents / 100).toFixed(2);
export const signed = cents => `${cents > 0 ? '+' : cents < 0 ? '−' : ''}${money(Math.abs(cents))}`;

export function element(type, value, className) {
  const node = document.createElement(type);
  if (value !== undefined && value !== null) node.textContent = value;
  if (className) node.className = className;
  return node;
}

export function flag(code) {
  const node = element('span', names[code] || code, 'flag');
  node.dataset.status = code;
  return node;
}

export function matrix(root, snapshot) {
  const table = element('table', null, 'matrix');
  const head = table.createTHead().insertRow();
  for (const text of ['店组', ...outcomes.map(code => names[code])]) {
    const heading = element('th', text);
    heading.scope = 'col';
    head.append(heading);
  }
  const title = new Map(snapshot.coverage.strata.map(row => [row.code, row.title]));
  const body = table.createTBody();
  for (const group of snapshot.settlement.strata) {
    const row = body.insertRow();
    const name = element('th', title.get(group.code));
    name.scope = 'row';
    row.append(name);
    for (const code of outcomes) {
      const count = group.counts[code];
      const button = element('button', count, `cell ${code.toLowerCase()}`);
      button.type = 'button';
      button.disabled = !count;
      button.dataset.group = group.code;
      button.dataset.outcome = code;
      button.setAttribute('aria-label', `${title.get(group.code)} ${names[code]} ${count} 柜`);
      row.insertCell().append(button);
    }
  }
  root.replaceChildren(table);
}

export function chart(root, distribution) {
  const max = Math.max(1, ...distribution.map(row => row.target));
  const axis = element('div', null, 'axis');
  axis.append(element('span', '0'), element('span', `${max} 柜`));
  const result = [axis];
  for (const group of distribution) {
    const line = element('div', null, 'gap-row');
    const track = element('div', null, 'gap-track');
    const counts = {verified: group.verified, pending: group.pending, isolated: group.isolated, unfilled: group.unfilled};
    for (const [type, count] of Object.entries(counts)) {
      const segment = element('i', null, type);
      segment.style.width = `${count / max * 100}%`;
      if (count) track.append(segment);
    }
    track.setAttribute('role', 'img');
    track.setAttribute('aria-label', `${group.title} 已核 ${group.verified}，待证 ${group.pending}，隔离 ${group.isolated}，缺额 ${group.unfilled}`);
    const total = element('span', `缺 ${group.gap}`, 'num');
    total.dataset.gap = group.code;
    line.append(element('span', group.title), track, total);
    result.push(line);
  }
  root.replaceChildren(...result);
}

export function cases(root, rows) {
  const priority = {VIOLATION: 0, ISOLATED: 1, PENDING: 2, COMPLIANT: 3};
  const order = [...rows].sort((a, b) => priority[a.status] - priority[b.status] || b.original_cents - a.original_cents || a.key.localeCompare(b.key));
  const entries = order.map(row => {
    const button = element('button', null, 'case-item');
    button.type = 'button';
    button.dataset.key = row.key;
    const message = element('span', reason(row.reason));
    message.title = message.textContent;
    button.append(element('strong', row.key, 'num'), flag(row.status), message, element('span', money(row.original_cents), 'num'));
    return button;
  });
  root.replaceChildren(...(entries.length ? entries : [element('p', '本批暂无抽中柜位。', 'empty')]));
}

export function accounts(root, snapshot) {
  const ledger = snapshot.revisions.ledger;
  const content = [['原批次罚额', ledger.original_cents]];
  if (snapshot.revisions.count) {
    content.push(['补交修订增减', ledger.revision_delta_cents], ['修订后罚额', ledger.revised_original_cents]);
  }
  content.push(['异议减免', ledger.reduction_cents], ['结算净罚额', ledger.net_cents]);
  root.replaceChildren(...content.map(([label, cents], index, rows) => {
    const line = element('div', null, index === rows.length - 1 ? 'money-row is-net' : 'money-row');
    line.append(element('span', label), element('strong', money(cents), 'num'));
    return line;
  }));
}
