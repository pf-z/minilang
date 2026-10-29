(function () {
  let DATA = null;
  let step = 0;
  let timer = null;
  // selection: null
  //   | { kind: "token", tokenStart, tokenEnd, owners: [nodeId], ancestors: [nodeId] }
  //   | { kind: "range", tokenStart, tokenEnd }
  //   | { kind: "node", nodeId, tokenStart, tokenEnd, ancestors: [nodeId] }
  let selection = null;
  let anchorTokenId = null;

  const $title = document.getElementById("title");
  const $source = document.getElementById("source");
  const $tokens = document.getElementById("tokens");
  const $ast = document.getElementById("ast");
  const $state = document.getElementById("state");
  const $output = document.getElementById("output");
  const $stepLabel = document.getElementById("step-label");
  const $prev = document.getElementById("prev");
  const $next = document.getElementById("next");
  const $play = document.getElementById("play");

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function init() {
    const example = new URLSearchParams(location.search).get("example");
    if (!example) {
      $title.textContent = "缺少 ?example= 参数";
      return;
    }
    try {
      const res = await fetch(`data/${example}.json`);
      if (!res.ok) throw new Error(`无法加载 data/${example}.json`);
      DATA = await res.json();
    } catch (e) {
      $title.textContent = e.message;
      return;
    }
    $title.textContent = DATA.name || example;
    renderSource();
    renderTokens();
    renderAst();
    goToStep(0, false);
    bindControls();
  }

  // ---------- 源码 ----------

  function renderSource() {
    const src = DATA.source;
    const ranges = DATA.tokens
      .filter((t) => t.type !== "EOF")
      .map((t) => ({ id: t.id, start: t.start, end: t.end }))
      .sort((a, b) => a.start - b.start);

    const parts = [];
    let pos = 0;
    for (const r of ranges) {
      if (r.end <= pos) continue;
      const s = Math.max(r.start, pos);
      if (s > pos) parts.push(escapeHtml(src.slice(pos, s)));
      parts.push(
        `<span class="source-seg" data-token-id="${r.id}">` +
        `${escapeHtml(src.slice(s, r.end))}</span>`
      );
      pos = r.end;
    }
    if (pos < src.length) parts.push(escapeHtml(src.slice(pos)));
    $source.innerHTML = parts.join("");
  }

  // ---------- Token ----------

  function renderTokens() {
    $tokens.innerHTML = DATA.tokens
      .filter((t) => t.type !== "EOF")
      .map((t) =>
        `<span class="token" data-token-id="${t.id}" ` +
        `title="${escapeHtml(t.type)} line ${t.line}">` +
        `${escapeHtml(t.lexeme || t.type)}</span>`
      ).join("");
  }

  // ---------- AST ----------

  function renderAst() {
    $ast.innerHTML = DATA.ast.map((n) => renderNode(n)).join("");
  }

  function renderNode(node) {
    const children = node.children && node.children.length
      ? `<div class="ast-children">${node.children.map(renderNode).join("")}</div>`
      : "";
    return `<div class="ast-node" data-node-id="${node.id}">` +
           `<span class="ast-label" data-node-id="${node.id}">` +
           `${escapeHtml(node.label)}</span>${children}</div>`;
  }

  // ---------- 选择 ----------

  function selectToken(tokenId, shift) {
    if (shift && anchorTokenId !== null) {
      const start = Math.min(anchorTokenId, tokenId);
      const end = Math.max(anchorTokenId, tokenId);
      selection = { kind: "range", tokenStart: start, tokenEnd: end };
      applyHighlights();
      renderSelectionState();
      return;
    }

    anchorTokenId = tokenId;
    const owners = findOwners(tokenId);
    // 祖先链取第一个 owner 的祖先；如果有多个 owner，合并所有祖先
    const ancestorSet = new Set();
    owners.forEach((n) => {
      findAncestors(n.id).forEach((id) => ancestorSet.add(id));
    });
    selection = {
      kind: "token",
      tokenStart: tokenId,
      tokenEnd: tokenId,
      owners: owners.map((n) => n.id),
      ancestors: [...ancestorSet],
    };
    applyHighlights();
    renderSelectionState();
  }

  function selectNode(nodeId) {
    const node = findNodeById(DATA.ast, nodeId);
    if (!node) return;
    selection = {
      kind: "node",
      nodeId,
      tokenStart: node.tokenStart,
      tokenEnd: node.tokenEnd,
      ancestors: findAncestors(nodeId),
    };
    anchorTokenId = null;
    applyHighlights();
    renderSelectionState();
  }

  function clearSelection() {
    selection = null;
    anchorTokenId = null;
    applyHighlights();
    renderState(null);
  }

  // ---------- 高亮 ----------

  function applyHighlights() {
    document.querySelectorAll(".source-seg.highlight")
      .forEach((el) => el.classList.remove("highlight"));
    document.querySelectorAll(".token.highlight")
      .forEach((el) => el.classList.remove("highlight"));
    document.querySelectorAll(".ast-label.active, .ast-label.ancestor")
      .forEach((el) => el.classList.remove("active", "ancestor"));

    if (!selection) return;

    const start = selection.tokenStart;
    const end = selection.tokenEnd;

    document.querySelectorAll(".token").forEach((el) => {
      const id = Number(el.dataset.tokenId);
      if (id >= start && id <= end) el.classList.add("highlight");
    });

    document.querySelectorAll(".source-seg").forEach((el) => {
      const id = Number(el.dataset.tokenId);
      if (id >= start && id <= end) el.classList.add("highlight");
    });

    if (selection.kind === "node") {
      (selection.ancestors || []).forEach((id) => {
        document.querySelectorAll(`.ast-label[data-node-id="${id}"]`)
          .forEach((el) => el.classList.add("ancestor"));
      });
      document.querySelectorAll(`.ast-label[data-node-id="${selection.nodeId}"]`)
        .forEach((el) => el.classList.add("active"));
    } else if (selection.kind === "token") {
      (selection.ancestors || []).forEach((id) => {
        document.querySelectorAll(`.ast-label[data-node-id="${id}"]`)
          .forEach((el) => el.classList.add("ancestor"));
      });
      (selection.owners || []).forEach((id) => {
        document.querySelectorAll(`.ast-label[data-node-id="${id}"]`)
          .forEach((el) => el.classList.add("active"));
      });
    } else {
      highlightAstForRange(start, end);
    }
  }

  function highlightAstForRange(start, end) {
    const rangeSet = new Set();
    for (let i = start; i <= end; i++) rangeSet.add(i);

    const activeIds = [];
    function walk(nodes) {
      for (const n of nodes) {
        const tokens = n.allTokens || [];
        if (!tokens.length) continue;
        const overlap = tokens.some((t) => rangeSet.has(t));
        if (overlap) {
          activeIds.push(n.id);
          if (n.children) walk(n.children);
        }
      }
    }
    walk(DATA.ast);
    activeIds.forEach((id) => {
      document.querySelectorAll(`.ast-label[data-node-id="${id}"]`)
        .forEach((el) => el.classList.add("active"));
    });
  }

  function findNodeById(nodes, id) {
    for (const n of nodes) {
      if (n.id === id) return n;
      const found = findNodeById(n.children || [], id);
      if (found) return found;
    }
    return null;
  }

  function findOwners(tokenId) {
    const result = [];
    function walk(nodes) {
      for (const n of nodes) {
        if (n.ownTokens && n.ownTokens.includes(tokenId)) result.push(n);
        if (n.children) walk(n.children);
      }
    }
    walk(DATA.ast);
    return result;
  }

  function findAncestors(nodeId) {
    const path = [];
    function walk(nodes, chain) {
      for (const n of nodes) {
        if (n.id === nodeId) {
          path.push(...chain);
          return true;
        }
        if (n.children && walk(n.children, [...chain, n.id])) return true;
      }
      return false;
    }
    walk(DATA.ast, []);
    return path;
  }

  // ---------- 状态面板 ----------

  function renderState(ev) {
    if (!ev) {
      $state.innerHTML =
        `<div class="env-empty">点击源码、Token 或 AST 节点查看详情</div>`;
      return;
    }
    let html = `<span class="state-action ${ev.action}">` +
               `${escapeHtml(ev.action)} / ${escapeHtml(ev.phase)}</span>`;
    if (ev.extra) {
      html += `<div class="env-scope"><div class="env-scope-label">选中对象</div>` +
              `<div class="env-row"><span class="env-value">${escapeHtml(ev.extra)}</span></div>` +
              `</div>`;
    }
    if (ev.env && ev.env.length) {
      ev.env.forEach((scope) => {
        const entries = Object.entries(scope.values);
        if (!entries.length) return;
        html += `<div class="env-scope">` +
                `<div class="env-scope-label">作用域深度 ${scope.depth}</div>` +
                entries.map(([k, v]) =>
                  `<div class="env-row"><span class="env-name">${escapeHtml(k)}</span>` +
                  `<span class="env-value">= ${escapeHtml(v)}</span></div>`
                ).join("") +
                `</div>`;
      });
    }
    $state.innerHTML = html;
  }

  function renderSelectionState() {
    if (!selection) return;
    if (selection.kind === "node") {
      const node = findNodeById(DATA.ast, selection.nodeId);
      renderState({
        action: "select",
        phase: "node",
        env: [],
        extra: node ? node.label : "",
      });
    } else if (selection.kind === "range") {
      renderState({
        action: "select",
        phase: "range",
        env: [],
        extra: `Token ${selection.tokenStart} .. ${selection.tokenEnd}`,
      });
    } else {
      const t = DATA.tokens.find((x) => x.id === selection.tokenStart);
      renderState({
        action: "select",
        phase: "token",
        env: [],
        extra: t ? `${t.type}  ${JSON.stringify(t.lexeme)}  line ${t.line}` : "",
      });
    }
  }

  // ---------- 输出 ----------

  function renderOutput() {
    const lines = [];
    for (let i = 0; i <= step; i++) {
      const e = DATA.execution[i];
      if (e.action === "print" || e.action === "error") {
        lines.push(e.output || "");
      }
    }
    $output.textContent = lines.join("\n");
    $output.scrollTop = $output.scrollHeight;
  }

  // ---------- 步骤切换 ----------

  function goToStep(i, select = true) {
    if (!DATA || !DATA.execution.length) {
      $stepLabel.textContent = "0 / 0";
      return;
    }
    step = Math.max(0, Math.min(i, DATA.execution.length - 1));
    const ev = DATA.execution[step];

    if (select && ev.nodeId !== null) {
      const node = findNodeById(DATA.ast, ev.nodeId);
      selection = {
        kind: "node",
        nodeId: ev.nodeId,
        tokenStart: node ? node.tokenStart : -1,
        tokenEnd: node ? node.tokenEnd : -1,
        ancestors: findAncestors(ev.nodeId),
      };
      anchorTokenId = null;
    }
    applyHighlights();

    let html = `<span class="state-action ${ev.action}">` +
               `${escapeHtml(ev.action)} / ${escapeHtml(ev.phase)}</span>`;
    if (ev.env && ev.env.length) {
      ev.env.forEach((scope) => {
        const entries = Object.entries(scope.values);
        if (!entries.length) return;
        html += `<div class="env-scope">` +
                `<div class="env-scope-label">作用域深度 ${scope.depth}</div>` +
                entries.map(([k, v]) =>
                  `<div class="env-row"><span class="env-name">${escapeHtml(k)}</span>` +
                  `<span class="env-value">= ${escapeHtml(v)}</span></div>`
                ).join("") +
                `</div>`;
      });
    } else {
      html += `<div class="env-empty">（无环境信息）</div>`;
    }
    $state.innerHTML = html;

    renderOutput();
    $stepLabel.textContent = `${step + 1} / ${DATA.execution.length}`;
    $prev.disabled = step === 0;
    $next.disabled = step === DATA.execution.length - 1;
  }

  // ---------- 交互 ----------

  function bindControls() {
    $prev.addEventListener("click", () => { stop(); goToStep(step - 1); });
    $next.addEventListener("click", () => { stop(); goToStep(step + 1); });
    $play.addEventListener("click", () => {
      if (timer) { stop(); return; }
      $play.textContent = "⏸";
      timer = setInterval(() => {
        if (step >= DATA.execution.length - 1) { stop(); return; }
        goToStep(step + 1);
      }, 180);
    });

    document.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === "ArrowLeft") { stop(); goToStep(step - 1); }
      else if (e.key === "ArrowRight") { stop(); goToStep(step + 1); }
      else if (e.key === " ") { e.preventDefault(); $play.click(); }
      else if (e.key === "Escape") clearSelection();
    });

    $source.addEventListener("click", (e) => {
      const seg = e.target.closest(".source-seg");
      if (!seg) { clearSelection(); return; }
      stop();
      selectToken(Number(seg.dataset.tokenId), e.shiftKey);
    });

    $tokens.addEventListener("click", (e) => {
      const el = e.target.closest(".token");
      if (!el) { clearSelection(); return; }
      stop();
      selectToken(Number(el.dataset.tokenId), e.shiftKey);
    });

    $ast.addEventListener("click", (e) => {
      const label = e.target.closest(".ast-label");
      if (!label) { clearSelection(); return; }
      stop();
      selectNode(Number(label.dataset.nodeId));
    });
  }

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    $play.textContent = "▶";
  }

  init();
})();