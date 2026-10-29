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
  const $sourceInfo = document.getElementById("source-info");
  const $tokenInfo = document.getElementById("token-info");
  const $nodeInfo = document.getElementById("node-info");
  const $envState = document.getElementById("env-state");
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
    renderSourceInfo(null);
    renderTokenInfo(null);
    renderNodeInfo(null);
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
      renderSourceInfoForRange(start, end);
      renderTokenInfoForRange(start, end);
      renderNodeInfoForRange(start, end);
      return;
    }

    anchorTokenId = tokenId;
    const owners = findOwners(tokenId);
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
    renderSourceInfo(tokenId);
    renderTokenInfo(tokenId);
    renderNodeInfoForToken(owners);
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
    renderSourceInfoForRange(node.tokenStart, node.tokenEnd);
    renderTokenInfoForRange(node.tokenStart, node.tokenEnd);
    renderNodeInfo(nodeId);
  }

  function clearSelection() {
    selection = null;
    anchorTokenId = null;
    applyHighlights();
    renderSourceInfo(null);
    renderTokenInfo(null);
    renderNodeInfo(null);
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

  // ---------- 通用渲染 ----------

  function renderInfoGrid(rows) {
    if (!rows.length) return `<div class="info-empty">（无）</div>`;
    return `<div class="info-grid">` +
           rows.map(([k, v]) =>
             `<span class="info-key">${escapeHtml(k)}</span>` +
             `<span class="info-value">${escapeHtml(v)}</span>`
           ).join("") +
           `</div>`;
  }

  function renderNodeBlock(node) {
    const rows = [["type", node.type]];
    (node.fields || []).forEach(([k, v]) => rows.push([k, v]));
    return renderInfoGrid(rows);
  }

  // ---------- 源码信息 ----------

  function tokenLine(t) {
    return t.line;
  }

  function renderSourceInfo(tokenId) {
    if (tokenId === null) {
      $sourceInfo.innerHTML = `<div class="info-empty">未选中源码位置</div>`;
      return;
    }
    const t = DATA.tokens.find((x) => x.id === tokenId);
    if (!t) {
      $sourceInfo.innerHTML = `<div class="info-empty">未找到</div>`;
      return;
    }
    const lines = DATA.source.split("\n");
    const lineText = lines[t.line - 1] || "";
    const col = t.start - (DATA.source.lastIndexOf("\n", t.start - 1) + 1) + 1;
    const rows = [
      ["行号", String(t.line)],
      ["列号", String(col)],
      ["字符范围", `${t.start} .. ${t.end}`],
      ["当前行", lineText],
    ];
    $sourceInfo.innerHTML = renderInfoGrid(rows);
  }

  function renderSourceInfoForRange(start, end) {
    if (start < 0 || end < start) {
      $sourceInfo.innerHTML = `<div class="info-empty">无对应源码位置</div>`;
      return;
    }
    const t1 = DATA.tokens.find((x) => x.id === start);
    const t2 = DATA.tokens.find((x) => x.id === end);
    if (!t1 || !t2) {
      $sourceInfo.innerHTML = `<div class="info-empty">未找到</div>`;
      return;
    }
    const rows = [
      ["起始行", String(t1.line)],
      ["结束行", String(t2.line)],
      ["字符范围", `${t1.start} .. ${t2.end}`],
      ["Token 范围", `${start} .. ${end}`],
    ];
    $sourceInfo.innerHTML = renderInfoGrid(rows);
  }

  // ---------- Token 信息 ----------

  function renderTokenInfo(tokenId) {
    if (tokenId === null) {
      $tokenInfo.innerHTML = `<div class="info-empty">未选中 Token</div>`;
      return;
    }
    const t = DATA.tokens.find((x) => x.id === tokenId);
    if (!t) {
      $tokenInfo.innerHTML = `<div class="info-empty">未找到</div>`;
      return;
    }
    const rows = [
      ["type", t.type],
      ["lexeme", JSON.stringify(t.lexeme)],
      ["literal", t.literal === null || t.literal === undefined ? "nil" : String(t.literal)],
      ["line", String(t.line)],
    ];
    $tokenInfo.innerHTML = renderInfoGrid(rows);
  }

  function renderTokenInfoForRange(start, end) {
    if (start < 0 || end < start) {
      $tokenInfo.innerHTML = `<div class="info-empty">无对应 Token</div>`;
      return;
    }
    if (start === end) {
      renderTokenInfo(start);
      return;
    }

    // 按 owner 分组：每个 Token 找它最深层拥有它的节点
    const groups = new Map();
    const orphan = [];

    for (let id = start; id <= end; id++) {
      const t = DATA.tokens.find((x) => x.id === id);
      if (!t || t.type === "EOF") continue;
      const owners = findOwners(id);
      if (!owners.length) {
        orphan.push(t);
        continue;
      }
      const deepest = owners.reduce((a, b) => {
        if (a.tokenStart > b.tokenStart) return a;
        if (a.tokenStart < b.tokenStart) return b;
        return a.tokenEnd < b.tokenEnd ? a : b;
      });
      if (!groups.has(deepest.id)) {
        groups.set(deepest.id, { node: deepest, tokens: [] });
      }
      groups.get(deepest.id).tokens.push(t);
    }

    let html = `<div class="info-grid">` +
               `<span class="info-key">范围</span>` +
               `<span class="info-value">Token ${start} .. ${end}</span>` +
               `</div>`;

    for (const { node, tokens } of groups.values()) {
      html += `<div class="info-sub">` +
              `<div class="info-sub-title">${escapeHtml(node.label)}</div>` +
              `<div class="info-grid">` +
              tokens.map((t) =>
                `<span class="info-key">${escapeHtml(t.type)}</span>` +
                `<span class="info-value">${escapeHtml(t.lexeme || "")}</span>`
              ).join("") +
              `</div></div>`;
    }

    if (orphan.length) {
      html += `<div class="info-sub">` +
              `<div class="info-sub-title">（不属于任何节点）</div>` +
              `<div class="info-grid">` +
              orphan.map((t) =>
                `<span class="info-key">${escapeHtml(t.type)}</span>` +
                `<span class="info-value">${escapeHtml(t.lexeme || "")}</span>`
              ).join("") +
              `</div></div>`;
    }

    $tokenInfo.innerHTML = html;
  }

  // ---------- AST 节点信息 ----------

  function renderNodeInfo(nodeId) {
    if (nodeId === null) {
      $nodeInfo.innerHTML = `<div class="info-empty">未选中 AST 节点</div>`;
      return;
    }
    const node = findNodeById(DATA.ast, nodeId);
    if (!node) {
      $nodeInfo.innerHTML = `<div class="info-empty">未找到</div>`;
      return;
    }
    $nodeInfo.innerHTML = renderNodeBlock(node);
  }

  function renderNodeInfoForToken(owners) {
    if (!owners.length) {
      $nodeInfo.innerHTML = `<div class="info-empty">该 Token 不属于任何 AST 节点</div>`;
      return;
    }
    if (owners.length === 1) {
      $nodeInfo.innerHTML = renderNodeBlock(owners[0]);
      return;
    }
    let html = "";
    owners.forEach((n) => {
      html += `<div class="info-sub">` +
              `<div class="info-sub-title">${escapeHtml(n.label)}</div>` +
              renderNodeBlock(n) +
              `</div>`;
    });
    $nodeInfo.innerHTML = html;
  }

  function renderTokenInfoForRange(start, end) {
    if (start < 0 || end < start) {
      $tokenInfo.innerHTML = `<div class="info-empty">无对应 Token</div>`;
      return;
    }
    if (start === end) {
      renderTokenInfo(start);
      return;
    }

    // 收集所有节点，用于判断每个 Token 属于哪个最深层节点
    const allNodes = [];
    function collect(nodes) {
      for (const n of nodes) {
        if (n.tokenStart >= 0) allNodes.push(n);
        if (n.children) collect(n.children);
      }
    }
    collect(DATA.ast);

    const groups = new Map();
    const orphan = [];

    for (let id = start; id <= end; id++) {
      const t = DATA.tokens.find((x) => x.id === id);
      if (!t || t.type === "EOF") continue;

      const covering = allNodes.filter(
        (n) => id >= n.tokenStart && id <= n.tokenEnd
      );
      if (!covering.length) {
        orphan.push(t);
        continue;
      }
      const deepest = covering.reduce((a, b) => {
        if (a.tokenStart > b.tokenStart) return a;
        if (a.tokenStart < b.tokenStart) return b;
        return a.tokenEnd < b.tokenEnd ? a : b;
      });
      if (!groups.has(deepest.id)) {
        groups.set(deepest.id, { node: deepest, tokens: [] });
      }
      groups.get(deepest.id).tokens.push(t);
    }

    let html = `<div class="info-grid">` +
               `<span class="info-key">范围</span>` +
               `<span class="info-value">Token ${start} .. ${end}</span>` +
               `</div>`;

    function renderTokenRows(tokens) {
      let s = "";
      tokens.forEach((t) => {
        s += `<div class="info-sub">` +
             `<div class="info-grid">` +
             `<span class="info-key">type</span><span class="info-value">${escapeHtml(t.type)}</span>` +
             `<span class="info-key">lexeme</span><span class="info-value">${escapeHtml(JSON.stringify(t.lexeme))}</span>` +
             `<span class="info-key">literal</span><span class="info-value">${t.literal === null || t.literal === undefined ? "nil" : escapeHtml(String(t.literal))}</span>` +
             `<span class="info-key">line</span><span class="info-value">${t.line}</span>` +
             `</div></div>`;
      });
      return s;
    }

    for (const { node, tokens } of groups.values()) {
      html += `<div class="info-sub">` +
              `<div class="info-sub-title">${escapeHtml(node.label)}</div>` +
              renderTokenRows(tokens) +
              `</div>`;
    }

    if (orphan.length) {
      html += `<div class="info-sub">` +
              `<div class="info-sub-title">（不属于任何节点）</div>` +
              renderTokenRows(orphan) +
              `</div>`;
    }

    $tokenInfo.innerHTML = html;
  }

  // ---------- 执行环境 ----------

  function renderEnv(ev) {
    if (!ev) {
      $envState.innerHTML = `<div class="info-empty">无执行事件</div>`;
      return;
    }
    let html = `<div class="info-grid">` +
               `<span class="info-key">action</span>` +
               `<span class="info-value">${escapeHtml(ev.action)}</span>` +
               `<span class="info-key">phase</span>` +
               `<span class="info-value">${escapeHtml(ev.phase)}</span>` +
               `</div>`;
    if (ev.env && ev.env.length) {
      ev.env.forEach((scope) => {
        const entries = Object.entries(scope.values);
        if (!entries.length) return;
        html += `<div class="info-grid info-sub">` +
                `<span class="info-key">depth</span>` +
                `<span class="info-value">${scope.depth}</span>`;
        entries.forEach(([k, v]) => {
          html += `<span class="info-key">${escapeHtml(k)}</span>` +
                  `<span class="info-value">${escapeHtml(v)}</span>`;
        });
        html += `</div>`;
      });
    } else {
      html += `<div class="info-empty info-sub">无环境变量</div>`;
    }
    $envState.innerHTML = html;
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
      applyHighlights();
      const s = node ? node.tokenStart : -1;
      const e = node ? node.tokenEnd : -1;
      renderSourceInfoForRange(s, e);
      renderTokenInfoForRange(s, e);
      renderNodeInfo(ev.nodeId);
    } else {
      applyHighlights();
    }

    renderEnv(ev);
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