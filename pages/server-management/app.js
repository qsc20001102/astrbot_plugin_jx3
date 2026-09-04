const bridge = window.AstrBotPluginPage;
const state = { bindings: [], subscriptions: [], aliases: [], kungfu: [], servers: [], events: {} };
const editing = { aliasServer: null, kungfuPzid: null };
let toastTimer;

const byId = (id) => document.getElementById(id);

function showToast(message, isError = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("is-error", isError);
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2600);
}

function button(label, className, onClick) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = `link-button ${className || ""}`.trim();
  element.textContent = label;
  element.addEventListener("click", onClick);
  return element;
}

function emptyRow(columnCount, message) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = columnCount;
  cell.className = "empty";
  cell.textContent = message;
  row.append(cell);
  return row;
}

function aliasText(aliases) {
  return aliases.length ? aliases.join("、") : "无";
}

function inlineAliasEditor(aliases, label, onSave, onCancel) {
  const input = document.createElement("input");
  input.className = "inline-editor";
  input.value = aliases.join(", ");
  input.placeholder = "多个别名用逗号分隔";
  input.setAttribute("aria-label", label);

  const saveButton = button("保存", "", async () => {
    saveButton.disabled = true;
    cancelButton.disabled = true;
    const saved = await onSave(input.value);
    if (!saved) {
      saveButton.disabled = false;
      cancelButton.disabled = false;
      input.focus();
    }
  });
  const cancelButton = button("取消", "", onCancel);

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveButton.click();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelButton.click();
    }
  });
  queueMicrotask(() => input.focus());
  return { input, controls: [saveButton, cancelButton] };
}

function bindingMap() {
  return new Map(state.bindings.map((item) => [item.session_id, item.server]));
}

function renderSummary() {
  byId("binding-count").textContent = String(state.bindings.length);
  byId("subscription-count").textContent = String(state.subscriptions.filter((item) => item.enabled).length);
  byId("alias-count").textContent = String(state.aliases.reduce((total, item) => total + item.aliases.length, 0));
  byId("kungfu-count").textContent = String(state.kungfu.length);
}

function renderServerOptions() {
  const list = byId("server-options");
  list.replaceChildren(...state.servers.map((server) => {
    const option = document.createElement("option");
    option.value = server;
    return option;
  }));
}

function renderBindings() {
  const body = byId("bindings-body");
  if (!state.bindings.length) {
    body.replaceChildren(emptyRow(3, "暂无会话绑定"));
    return;
  }
  body.replaceChildren(...state.bindings.map((item) => {
    const row = document.createElement("tr");
    const session = document.createElement("td");
    const server = document.createElement("td");
    const actions = document.createElement("td");
    session.dataset.label = "会话 ID";
    server.dataset.label = "绑定区服";
    actions.dataset.label = "操作";
    session.textContent = item.session_id;
    server.textContent = item.server;
    actions.className = "actions";
    actions.append(
      button("编辑", "", () => {
        byId("binding-session").value = item.session_id;
        byId("binding-server").value = item.server;
        byId("binding-server").focus();
      }),
      button("解除绑定", "link-button--danger", async () => {
        if (!window.confirm(`确认解除会话 ${item.session_id} 的区服绑定？`)) return;
        await mutate("bindings/delete", { session_id: item.session_id }, "绑定已解除");
      }),
    );
    row.append(session, server, actions);
    return row;
  }));
}

function renderSubscriptions() {
  const body = byId("subscriptions-body");
  const bindings = bindingMap();
  if (!state.subscriptions.length) {
    body.replaceChildren(emptyRow(4, "暂无事件订阅会话"));
    return;
  }
  body.replaceChildren(...state.subscriptions.map((item) => {
    const row = document.createElement("tr");
    const session = document.createElement("td");
    const server = document.createElement("td");
    const enabled = document.createElement("td");
    const actions = document.createElement("td");
    session.dataset.label = "会话 ID";
    server.dataset.label = "绑定区服";
    enabled.dataset.label = "总开关";
    actions.dataset.label = "已订阅事件";
    session.textContent = item.session_id;
    server.textContent = bindings.get(item.session_id) || "未绑定（全部区服）";
    const stateLabel = document.createElement("span");
    stateLabel.className = `state ${item.enabled ? "state--on" : "state--off"}`;
    stateLabel.textContent = item.enabled ? "开启" : "关闭";
    enabled.append(stateLabel);
    const tags = document.createElement("div");
    tags.className = "tags";
    if (item.actions.length) {
      item.actions.forEach((action) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = `${action} ${state.events[String(action)] || "未知事件"}`;
        tags.append(tag);
      });
    } else {
      tags.textContent = "无";
    }
    actions.append(tags);
    row.append(session, server, enabled, actions);
    return row;
  }));
}

function renderAliases() {
  const body = byId("aliases-body");
  const aliasesByServer = new Map(
    state.aliases.map((item) => [item.server, item.aliases]),
  );
  const servers = [...new Set([
    ...state.servers,
    ...aliasesByServer.keys(),
  ])].sort((left, right) => left.localeCompare(right, "zh-CN"));
  if (!servers.length) {
    body.replaceChildren(emptyRow(3, "暂无标准区服数据"));
    return;
  }
  body.replaceChildren(...servers.map((serverName) => {
    const item = {
      server: serverName,
      aliases: aliasesByServer.get(serverName) || [],
    };
    const row = document.createElement("tr");
    const server = document.createElement("td");
    const aliases = document.createElement("td");
    const actions = document.createElement("td");
    server.dataset.label = "标准区服名";
    aliases.dataset.label = "别名";
    actions.dataset.label = "操作";
    server.textContent = item.server;
    aliases.className = "alias-cell";
    actions.className = "actions";
    if (editing.aliasServer === item.server) {
      row.classList.add("is-editing");
      const editor = inlineAliasEditor(
        item.aliases,
        `${item.server}的区服别名`,
        async (value) => {
          editing.aliasServer = null;
          const saved = await mutate(
            "aliases/save",
            { server: item.server, aliases: value },
            "区服别名已保存",
          );
          if (!saved) {
            editing.aliasServer = item.server;
            renderAliases();
          }
          return saved;
        },
        () => {
          editing.aliasServer = null;
          renderAliases();
        },
      );
      aliases.append(editor.input);
      actions.append(...editor.controls);
    } else {
      aliases.textContent = aliasText(item.aliases);
      actions.append(button("编辑", "", () => {
        editing.aliasServer = item.server;
        renderAliases();
      }));
    }
    row.append(server, aliases, actions);
    return row;
  }));
}

function renderKungfu() {
  const body = byId("kungfu-body");
  if (!state.kungfu.length) {
    body.replaceChildren(emptyRow(3, "暂无心法配置"));
    return;
  }
  body.replaceChildren(...state.kungfu.map((item) => {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    const aliases = document.createElement("td");
    const actions = document.createElement("td");
    name.dataset.label = "标准心法名";
    aliases.dataset.label = "别名";
    actions.dataset.label = "操作";
    name.textContent = item.name;
    aliases.className = "alias-cell";
    actions.className = "actions";
    if (editing.kungfuPzid === item.pzid) {
      row.classList.add("is-editing");
      const editor = inlineAliasEditor(
        item.aliases,
        `${item.name}的心法别名`,
        async (value) => {
          editing.kungfuPzid = null;
          const saved = await mutate(
            "kungfu/save",
            { pzid: item.pzid, aliases: value },
            "心法别名已保存",
          );
          if (!saved) {
            editing.kungfuPzid = item.pzid;
            renderKungfu();
          }
          return saved;
        },
        () => {
          editing.kungfuPzid = null;
          renderKungfu();
        },
      );
      aliases.append(editor.input);
      actions.append(...editor.controls);
    } else {
      aliases.textContent = aliasText(item.aliases);
      actions.append(button("编辑", "", () => {
        editing.kungfuPzid = item.pzid;
        renderKungfu();
      }));
    }
    row.append(name, aliases, actions);
    return row;
  }));
}

function render() {
  renderSummary();
  renderServerOptions();
  renderBindings();
  renderSubscriptions();
  renderAliases();
  renderKungfu();
}

async function loadData() {
  const data = await bridge.apiGet("dashboard");
  Object.assign(state, data);
  render();
}

async function mutate(endpoint, payload, successMessage) {
  try {
    await bridge.apiPost(endpoint, payload);
    await loadData();
    showToast(successMessage);
    return true;
  } catch (error) {
    showToast(error?.message || "操作失败", true);
    return false;
  }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => {
      const active = item === tab;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      const active = panel.id === `${tab.dataset.tab}-panel`;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  });
});

byId("binding-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const saved = await mutate("bindings/save", {
    session_id: byId("binding-session").value,
    server: byId("binding-server").value,
  }, "绑定信息已保存");
  if (saved) event.currentTarget.reset();
});

byId("refresh").addEventListener("click", async (event) => {
  const control = event.currentTarget;
  control.disabled = true;
  try {
    await bridge.apiPost("servers/refresh", {});
    await loadData();
    showToast("区服目录与页面数据已刷新");
  } catch (error) {
    showToast(error?.message || "刷新失败", true);
  } finally {
    control.disabled = false;
  }
});

await bridge.ready();
try {
  await loadData();
} catch (error) {
  showToast(error?.message || "管理数据加载失败", true);
}
