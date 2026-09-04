const bridge = window.AstrBotPluginPage;
const state = {
  bindings: [],
  subscriptions: [],
  aliases: [],
  kungfu: [],
  servers: [],
  events: {},
  session_control: { mode: "all", entries: [] },
  token_stats: null,
};
const editing = { bindingSession: null, controlSession: null, aliasServer: null, kungfuPzid: null };
const restoreConfirmationTimers = new WeakMap();
let toastTimer;

const byId = (id) => document.getElementById(id);

function formatUsageCount(value) {
  return Number.isSafeInteger(value) && value >= 0
    ? value.toLocaleString("zh-CN")
    : "—";
}

function renderTokenStats() {
  const stats = state.token_stats;
  byId("token-level").textContent = Number.isSafeInteger(stats?.level)
    ? `LV.${stats.level}`
    : "—";
  byId("token-used").textContent = formatUsageCount(stats?.used);
  byId("token-remaining").textContent = formatUsageCount(stats?.remaining);

  const status = byId("token-valid");
  status.classList.remove("token-status--valid", "token-status--invalid");
  if (stats?.valid === true) {
    status.textContent = "有效";
    status.classList.add("token-status--valid");
  } else if (stats?.valid === false) {
    status.textContent = "无效";
    status.classList.add("token-status--invalid");
  } else {
    status.textContent = "未获取";
  }
}

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

function createServerSelect(selectedServer = "", label = "绑定区服") {
  const select = document.createElement("select");
  select.className = "inline-editor";
  select.required = true;
  select.setAttribute("aria-label", label);

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "请选择标准区服";
  placeholder.disabled = true;
  placeholder.defaultSelected = true;
  select.append(placeholder);

  state.servers.forEach((server) => {
    const option = document.createElement("option");
    option.value = server;
    option.textContent = server;
    select.append(option);
  });
  select.value = state.servers.includes(selectedServer) ? selectedServer : "";
  return select;
}

function inlineServerEditor(item, onSave, onCancel) {
  const select = createServerSelect(item.server, `${item.session_id}的绑定区服`);
  const saveButton = button("保存", "", async () => {
    if (!select.reportValidity()) return;
    select.disabled = true;
    saveButton.disabled = true;
    cancelButton.disabled = true;
    const saved = await onSave(select.value);
    if (!saved) {
      select.disabled = false;
      saveButton.disabled = false;
      cancelButton.disabled = false;
      select.focus();
    }
  });
  const cancelButton = button("取消", "", onCancel);
  select.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveButton.click();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelButton.click();
    }
  });
  queueMicrotask(() => select.focus());
  return { select, controls: [saveButton, cancelButton] };
}

function bindingMap() {
  return new Map(state.bindings.map((item) => [item.session_id, item.server]));
}

function renderServerOptions() {
  const select = byId("binding-server");
  const currentValue = select.value;
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "请选择标准区服";
  placeholder.disabled = true;
  placeholder.defaultSelected = true;
  select.replaceChildren(placeholder, ...state.servers.map((server) => {
    const option = document.createElement("option");
    option.value = server;
    option.textContent = server;
    return option;
  }));
  select.value = state.servers.includes(currentValue) ? currentValue : "";
}

function renderSessionOptions() {
  const sessionIds = new Set([
    ...state.bindings.map((item) => item.session_id),
    ...state.subscriptions.map((item) => item.session_id),
    ...state.session_control.entries.map((item) => item.session_id),
  ]);
  byId("session-options").replaceChildren(...[...sessionIds].sort().map((sessionId) => {
    const option = document.createElement("option");
    option.value = sessionId;
    return option;
  }));
}

function controlModeCopy(mode) {
  if (mode === "whitelist") {
    return "只有白名单中的会话可以使用插件和接收事件推送；白名单为空时不放行任何会话。";
  }
  if (mode === "blacklist") {
    return "黑名单中的会话会被拦截；黑名单为空时放行全部会话。";
  }
  return "所有会话都可以使用插件并接收已订阅的事件推送；下方名单暂不生效。";
}

function controlModeLabel(mode) {
  if (mode === "whitelist") return "白名单";
  if (mode === "blacklist") return "黑名单";
  return "全部会话";
}

function updateModeSelection(selectedMode) {
  const activeMode = state.session_control?.mode || "all";
  document.querySelectorAll(".mode-option").forEach((option) => {
    const input = option.querySelector('input[name="control_mode"]');
    option.classList.toggle("is-selected", input?.value === selectedMode);
    option.classList.toggle("is-active-mode", input?.value === activeMode);
  });
  const saveButton = byId("control-mode-save");
  saveButton.textContent = selectedMode === activeMode
    ? "当前模式已生效"
    : `切换为${controlModeLabel(selectedMode)}`;
}

function renderSessionControl() {
  const control = state.session_control || { mode: "all", entries: [] };
  document.querySelectorAll('input[name="control_mode"]').forEach((input) => {
    input.checked = input.value === control.mode;
  });
  updateModeSelection(control.mode);
  byId("control-mode-label").textContent = controlModeLabel(control.mode);
  byId("control-mode-hint").textContent = controlModeCopy(control.mode);

  const body = byId("control-entries-body");
  if (!control.entries.length) {
    body.replaceChildren(emptyRow(4, "暂无白名单或黑名单会话"));
    return;
  }

  body.replaceChildren(...control.entries.map((item) => {
    const row = document.createElement("tr");
    const session = document.createElement("td");
    const listType = document.createElement("td");
    const remark = document.createElement("td");
    const actions = document.createElement("td");
    session.dataset.label = "会话 ID";
    listType.dataset.label = "名单类型";
    remark.dataset.label = "备注";
    actions.dataset.label = "操作";
    actions.className = "actions";
    session.textContent = item.session_id;

    if (editing.controlSession === item.session_id) {
      row.classList.add("is-editing");
      const typeSelect = document.createElement("select");
      typeSelect.className = "inline-editor inline-editor--compact";
      typeSelect.setAttribute("aria-label", `${item.session_id}的名单类型`);
      typeSelect.append(
        new Option("白名单", "whitelist"),
        new Option("黑名单", "blacklist"),
      );
      typeSelect.value = item.list_type;

      const remarkInput = document.createElement("input");
      remarkInput.className = "inline-editor";
      remarkInput.maxLength = 200;
      remarkInput.value = item.remark || "";
      remarkInput.placeholder = "备注（可选）";
      remarkInput.setAttribute("aria-label", `${item.session_id}的备注`);

      const saveButton = button("保存", "", async () => {
        typeSelect.disabled = true;
        remarkInput.disabled = true;
        saveButton.disabled = true;
        cancelButton.disabled = true;
        editing.controlSession = null;
        const saved = await mutate(
          "session-control/save",
          { session_id: item.session_id, list_type: typeSelect.value, remark: remarkInput.value },
          "会话名单已保存",
        );
        if (!saved) {
          editing.controlSession = item.session_id;
          renderSessionControl();
        }
      });
      const cancelButton = button("取消", "", () => {
        editing.controlSession = null;
        renderSessionControl();
      });
      remarkInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          saveButton.click();
        } else if (event.key === "Escape") {
          event.preventDefault();
          cancelButton.click();
        }
      });
      remark.append(remarkInput);
      listType.append(typeSelect);
      actions.append(saveButton, cancelButton);
      queueMicrotask(() => typeSelect.focus());
    } else {
      const badge = document.createElement("span");
      badge.className = `list-badge list-badge--${item.list_type}`;
      badge.textContent = item.list_type === "whitelist" ? "白名单" : "黑名单";
      listType.append(badge);
      remark.textContent = item.remark || "—";
      actions.append(
        button("编辑", "", () => {
          editing.controlSession = item.session_id;
          renderSessionControl();
        }),
        button("删除", "link-button--danger", async (event) => {
          const deleteButton = event.currentTarget;
          deleteButton.disabled = true;
          const deleted = await mutate(
            "session-control/delete",
            { session_id: item.session_id },
            "会话名单已删除",
          );
          if (!deleted) deleteButton.disabled = false;
        }),
      );
    }
    row.append(session, listType, remark, actions);
    return row;
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
    actions.className = "actions";
    if (editing.bindingSession === item.session_id) {
      row.classList.add("is-editing");
      const editor = inlineServerEditor(
        item,
        async (selectedServer) => {
          editing.bindingSession = null;
          const saved = await mutate(
            "bindings/save",
            { session_id: item.session_id, server: selectedServer },
            "绑定信息已保存",
          );
          if (!saved) {
            editing.bindingSession = item.session_id;
            renderBindings();
          }
          return saved;
        },
        () => {
          editing.bindingSession = null;
          renderBindings();
        },
      );
      server.append(editor.select);
      actions.append(...editor.controls);
    } else {
      server.textContent = item.server;
      actions.append(
        button("编辑", "", () => {
          editing.bindingSession = item.session_id;
          renderBindings();
        }),
        button("解除绑定", "link-button--danger", async (event) => {
          const control = event.currentTarget;
          control.disabled = true;
          const deleted = await mutate(
            "bindings/delete",
            { session_id: item.session_id },
            "绑定已解除",
          );
          if (!deleted) control.disabled = false;
        }),
      );
    }
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
  renderTokenStats();
  renderServerOptions();
  renderSessionOptions();
  renderSessionControl();
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

function resetRestoreConfirmation(control) {
  const timer = restoreConfirmationTimers.get(control);
  if (timer) clearTimeout(timer);
  restoreConfirmationTimers.delete(control);
  delete control.dataset.confirming;
  control.classList.remove("button--danger");
  control.textContent = "恢复默认";
}

function confirmRestoreInPage(control, confirmation) {
  if (control.dataset.confirming === "true") {
    resetRestoreConfirmation(control);
    return true;
  }

  control.dataset.confirming = "true";
  control.classList.add("button--danger");
  control.textContent = "再次点击确认";
  showToast(confirmation);
  restoreConfirmationTimers.set(
    control,
    setTimeout(() => resetRestoreConfirmation(control), 5000),
  );
  return false;
}

async function restoreDefaults(control, endpoint, confirmation, successMessage, resetEditing) {
  if (!confirmRestoreInPage(control, confirmation)) return;
  const originalLabel = control.textContent;
  control.disabled = true;
  control.textContent = "恢复中…";
  resetEditing();
  try {
    await bridge.apiPost(endpoint, {});
    await loadData();
    showToast(successMessage);
  } catch (error) {
    showToast(error?.message || "恢复默认失败", true);
  } finally {
    control.disabled = false;
    control.textContent = originalLabel;
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

document.querySelectorAll('input[name="control_mode"]').forEach((input) => {
  input.addEventListener("change", () => {
    updateModeSelection(input.value);
  });
});

byId("control-mode-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const selected = new FormData(event.currentTarget).get("control_mode");
  await mutate("session-control/mode", { mode: selected }, "会话控制模式已保存");
});

byId("control-entry-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const saved = await mutate("session-control/save", {
    session_id: byId("control-session").value,
    list_type: byId("control-list-type").value,
    remark: byId("control-remark").value,
  }, "会话名单已保存");
  if (saved) event.currentTarget.reset();
});

byId("restore-aliases").addEventListener("click", async (event) => {
  await restoreDefaults(
    event.currentTarget,
    "aliases/restore",
    "再次点击按钮，确认使用内置 JSON 覆盖当前全部区服别名",
    "区服别名已恢复默认",
    () => { editing.aliasServer = null; },
  );
});

byId("restore-kungfu").addEventListener("click", async (event) => {
  await restoreDefaults(
    event.currentTarget,
    "kungfu/restore",
    "再次点击按钮，确认使用内置 JSON 覆盖当前全部心法及别名",
    "心法别名已恢复默认",
    () => { editing.kungfuPzid = null; },
  );
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
