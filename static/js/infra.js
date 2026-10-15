function pageDocker(ctx) {
  const showStopped = getPref("stopped"), onlyUsed = getPref("onlyUsed");
  const st = data.docker_stats || {};
  let cs = (data.containers || []).slice().sort((a, b) => (a.state !== "running") - (b.state !== "running") || a.name.localeCompare(b.name));
  const total = cs.length, running = cs.filter(c => c.state === "running").length;
  if (!showStopped) cs = cs.filter(c => c.state === "running");
  if (onlyUsed) cs = cs.filter(c => ctx.ctrUsers[c.name]);
  const rows = cs.map(c => {
    const s = st[c.name] || {}, pg = ctx.ctrConns[c.name], slug = ctx.slugOf(c.name), wt = slug && ctx.wtBySlug[slug];
    const web = c.ports.find(p => p.container === "8069");
    const notes = [];
    if (slug && !wt) notes.push('<span class="badge warn">worktree gone</span>');
    if (isLeftover(c.name)) notes.push('<span class="badge warn">leftover one-off run</span>');
    if (c.health && c.health !== "healthy") notes.push(`<span class="badge warn">${esc(c.health)}</span>`);
    return `<tr><td><div class="main mono">${esc(c.name)}</div><div class="subt">${wt ? "worktree " + esc(wt.name) : esc(c.image)}</div></td>
      <td class="nowrap"><span class="status"><span class="dot ${c.state === "running" ? "ok" : "bad"}"></span>${c.state === "running" ? "Running · " + dur(now() - c.started) : esc(c.state) + " · " + ago(c.finished)}</span></td>
      <td class="num">${s.cpu != null ? s.cpu.toFixed(1) + "%" : "—"}</td><td class="num">${s.mem ? bytes(s.mem) : "—"}</td>
      <td class="nowrap" title="${esc(c.ports.map(p => p.host + " → " + p.container).join("\n"))}">${web ? `<a href="http://127.0.0.1:${web.host}/web/login" target="_blank">:${web.host} ↗</a>` : c.ports.length ? `<span class="muted">${c.ports.length} port${c.ports.length > 1 ? "s" : ""}</span>` : ""}</td>
      <td class="mono">${esc(c.db_name)}</td>
      <td class="num" title="${pg ? esc([...pg.dbs].join(", ")) : ""}">${pg ? pg.total : ""}</td>
      <td>${(ctx.ctrUsers[c.name] || []).map(sessTag).join("<br>")}</td><td>${notes.join(" ")}</td></tr>`;
  });
  return `<div class="pagehead"><h1>Docker</h1><span class="sub">${running} running of ${total}</span></div>
    <div class="toolbar"><label><input type="checkbox" data-pref="stopped" ${showStopped ? "checked" : ""}> Show stopped</label><label><input type="checkbox" data-pref="onlyUsed" ${onlyUsed ? "checked" : ""}> Only ones a session uses</label></div>
    ${table(["Container", "Status", ["CPU", "num"], ["Memory", "num"], "Open", "Database", ["PG conns", "num"], "Used by", ""], rows)}`;
}

function pagePostgres(ctx) {
  const pg = data.pg || {}, all = getPref("allDbs");
  const total = Object.values(ctx.dbConns).reduce((a, x) => a + x.total, 0);
  const sum = k => Object.values(ctx.dbConns).reduce((a, x) => a + x[k], 0);
  const act = (pg.active || []).map(a => `<tr><td><div class="mono clamp" title="${esc(a.query)}">${esc(a.query)}</div></td><td class="mono nowrap">${esc(a.db)}</td><td class="nowrap">${esc(ctx.byIp[a.addr] || a.addr)}</td><td class="nowrap">${a.state === "active" ? '<span class="badge ok">active</span>' : `<span class="badge warn">${esc(a.state)}</span>`}${a.wait ? `<div class="subt">${esc(a.wait)}</div>` : ""}</td><td class="num" style="color:${a.secs > 30 ? "var(--bad)" : a.secs > 5 ? "var(--warn)" : "inherit"}">${dur(a.secs)}</td></tr>`);
  const names = new Set([...Object.keys(ctx.sizes), ...Object.keys(ctx.dbConns).filter(Boolean)]);
  const list = [...names].map(n => ({ n, size: ctx.sizes[n] || 0, c: ctx.dbConns[n] }));
  const keep = r => all || r.c || ctx.dbUsers[r.n] || ctx.orphanDb.includes(r.n);
  const shown = list.filter(keep).sort((a, b) => (b.c?.total || 0) - (a.c?.total || 0) || b.size - a.size);
  const rows = shown.map(({ n, size, c }) => {
    const notes = [];
    if (ctx.orphanDb.includes(n)) notes.push('<span class="badge warn">worktree gone</span>');
    if (c && c.tx) notes.push(`<span class="badge ${c.txFor > 60 ? "bad" : "warn"}">${c.tx} idle in transaction · ${dur(c.txFor)}</span>`);
    return `<tr><td class="mono">${esc(n)}</td><td class="num">${bytes(size)}</td><td class="num">${c ? c.total : ""}</td><td class="num">${c && c.active ? c.active : ""}</td>
      <td>${c ? [...c.from].map(f => `<div class="mono subt">${esc(f)}</div>`).join("") : ""}</td><td>${(ctx.dbUsers[n] || []).map(sessTag).join("<br>")}</td><td>${notes.join(" ")}</td></tr>`;
  });
  return `<div class="pagehead"><h1>Postgres</h1><span class="sub">${pg.ok ? esc(pg.version) : `<span class="err">${esc(conf("db.container") || "Postgres container")} is not reachable</span>`}</span></div>
    <section><div class="tiles">
      ${tile("Connections", `${total} / ${pg.max_connections || "?"}`, `${sum("idle")} idle`, bar([[pct(total, pg.max_connections), color(pct(total, pg.max_connections))]]))}
      ${tile("Active", sum("active"), "running a query now")}
      ${tile("Idle in transaction", sum("tx"), "holding a transaction open")}
      ${tile("Waiting locks", pg.waiting_locks ?? "—", "blocked on another session")}
      ${tile("Databases", Object.keys(ctx.sizes).length, `${bytes(Object.values(ctx.sizes).reduce((a, b) => a + b, 0))} total`)}
    </div></section>
    <section><h2>Queries in progress<span class="count">${act.length}</span></h2>${table(["Query", "Database", "From", "State", ["Running", "num"]], act, "No queries running right now.")}</section>
    <section><h2>Databases<span class="count">${shown.length}${shown.length < list.length ? ` of ${list.length}` : ""}</span></h2>
      <div class="toolbar"><label><input type="checkbox" data-pref="allDbs" ${all ? "checked" : ""}> Show all (${list.length - shown.length} idle and unused hidden)</label></div>
      ${table(["Database", ["Size", "num"], ["Conns", "num"], ["Active", "num"], "Connected from", "Used by", ""], rows)}</section>`;
}

function pageWorktrees(ctx) {
  const ws = (data.worktrees || []).slice().sort((a, b) => b.mtime - a.mtime);
  const rows = ws.map(w => {
    const c = ctx.byName[wtContainer(w.slug)], web = c?.ports.find(p => p.container === (data.profile?.containers?.web_port || ""));
    const dbs = wtDbs(w.slug).filter(d => ctx.sizes[d] != null);
    return `<tr><td><div class="main">${esc(w.name)}</div><div class="subt mono">${esc(w.branch)}</div></td>
      <td class="num">${w.dirty ? `<span class="text-warn">${w.dirty} files</span>` : '<span class="muted">clean</span>'}</td>
      <td><div class="clamp">${esc(w.last_commit)}</div><div class="subt" title="${esc(fmtDateTime(w.last_commit_ts))}">${ago(w.last_commit_ts)}</div></td>
      <td class="nowrap">${c ? `<span class="status"><span class="dot ${c.state === "running" ? "ok" : "bad"}"></span>${c.state === "running" ? "Running" : esc(c.state)}</span>${web && c.state === "running" ? ` <a href="http://127.0.0.1:${web.host}/web/login" target="_blank">:${web.host} ↗</a>` : ""}` : '<span class="muted">—</span>'}</td>
      <td>${dbs.map(d => `<div class="mono subt">${esc(d)} · ${bytes(ctx.sizes[d])}</div>`).join("") || '<span class="muted">—</span>'}</td>
      <td>${(ctx.wtUsers[w.name] || []).map(sessTag).join("<br>")}</td></tr>`;
  });
  return `<div class="pagehead"><h1>Worktrees</h1><span class="sub">${ws.length} · ${ws.filter(w => w.dirty).length} with uncommitted changes</span></div>
    ${table(["Worktree", ["Uncommitted", "num"], "Last commit", "Server", "Databases", "Used by"], rows)}`;
}

function pageProcesses() {
  const p = data.procs || {};
  const t = rows => table(["Process", ["CPU", "num"], ["RAM", "num"]], (rows || []).map(r => `<tr><td><div class="main">${esc(r.name)} <span class="muted">${r.pid}</span></div><div class="subt mono clamp" title="${esc(r.args)}">${esc(r.args)}</div></td><td class="num">${r.cpu.toFixed(1)}%</td><td class="num">${bytes(r.rss)}</td></tr>`));
  const m = data.mac || {};
  return `<div class="pagehead"><h1>Processes</h1><span class="sub">${p.count || 0} running on this Mac</span></div>
    <section><div class="tiles">
      ${tile("CPU", `${(m.cpu ?? 0).toFixed(0)}%`, `load ${(m.load || []).map(x => (+x).toFixed(1)).join(" / ")}`, bar([[m.cpu || 0, color(m.cpu || 0)]]))}
      ${tile("RAM", `${bytes(m.mem_used)} <small class="muted">/ ${bytes(m.mem_total, 0)}</small>`, "", bar([[pct(m.mem_used, m.mem_total), color(pct(m.mem_used, m.mem_total))]]))}
      ${m.swap_total ? tile("Swap", bytes(m.swap_used), `of ${bytes(m.swap_total)}`, bar([[pct(m.swap_used, m.swap_total), color(pct(m.swap_used, m.swap_total))]])) : ""}
    </div></section>
    <div class="cols"><section><h2>Top by CPU</h2>${t(p.cpu)}</section><section><h2>Top by memory</h2>${t(p.mem)}</section></div>`;
}
