export function createCommunities({ list, top, topList, bridgesList, cosmos, fmt, escapeHtml, rgb, kindName, isHttp, onRegion, onNode, onBridge }) {
  function row(dot, name, detail, count, onClick) {
    const li = document.createElement('li');
    li.innerHTML = `<button type="button"><span class="dot" style="--c: ${dot}"></span><span class="info"><b>${escapeHtml(name)}</b>${detail ? `<span>${escapeHtml(detail)}</span>` : ''}</span><span class="count">${count}</span></button>`;
    li.querySelector('button').addEventListener('click', onClick);
    return li;
  }

  function renderRegions() {
    const rows = cosmos.regions
      .map((R, i) => ({ R, i, size: cosmos.regionNodes[i].length }))
      .filter((x) => x.i > 0)
      .sort((a, b) => b.size - a.size || a.R.name.localeCompare(b.R.name));
    list.innerHTML = '';
    if (!rows.length) {
      list.innerHTML = '<li class="empty">todavía no hay comunidades tejidas</li>';
      return;
    }
    for (const { R, i, size } of rows) {
      const sub = R.sub && R.sub !== R.name ? R.sub : '';
      list.appendChild(row(rgb(R.color), R.name, sub, fmt(size), () => onRegion(i)));
    }
  }

  function renderTop() {
    const best = [];
    cosmos.meta.forEach((m, id) => {
      if (!m) return;
      const deg = m.deg || 0;
      if (best.length < 10) best.push([id, deg]);
      else if (deg > best[9][1]) best[9] = [id, deg];
      else return;
      best.sort((a, b) => b[1] - a[1]);
    });
    top.hidden = !best.length;
    topList.innerHTML = '';
    for (const [id, deg] of best) {
      const m = cosmos.meta[id];
      const R = cosmos.regions[m.region];
      const detail = `${kindName[m.kind] || m.kind} · ${m.file}`;
      topList.appendChild(row(rgb(R ? R.color : [0.6, 0.85, 1]), m.name, detail, fmt(deg), () => onNode(id)));
    }
  }

  function renderBridges() {
    const scroll = bridgesList.parentElement.scrollTop;
    const rows = cosmos.endpoints();
    bridgesList.innerHTML = '';
    if (!rows.length) bridgesList.innerHTML = '<li class="empty">este grafo no tiene endpoints</li>';
    for (const { id, m, callers } of rows.slice(0, 300)) {
      const R = cosmos.regions[m.region];
      const http = isHttp(m);
      const li = row(http ? 'rgb(255 199 122)' : 'rgb(122 235 214)', m.route || m.name, `${http ? 'HTTP' : 'RPC'} · ${R ? R.name : ''} · ${m.file}`, fmt(callers), () => onBridge(id));
      li.querySelector('.dot').classList.add('diamond');
      li.querySelector('.count').title = `${callers} ${callers === 1 ? 'llamada entrante' : 'llamadas entrantes'}`;
      bridgesList.appendChild(li);
    }
    bridgesList.parentElement.scrollTop = scroll;
  }

  return {
    renderBridges,
    render() {
      const scroll = list.parentElement.scrollTop;
      renderRegions();
      renderTop();
      list.parentElement.scrollTop = scroll;
    },
  };
}
