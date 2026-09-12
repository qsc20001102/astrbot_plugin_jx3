const bridge = window.AstrBotPluginPage;
const state = {
  bindings: [],
  subscriptions: [],
  aliases: [],
  kungfu: [],
  servers: [],
  events: {},
  free_event_actions: [],
  session_control: { mode: "all", entries: [] },
  legacy_bilei: [],
  teams: [],
  team_kungfu_icons: {},
  team_rule_sessions: [],
  team_rule_config: null,
  token_stats: null,
  cache: {
    defaults: { api: 300, image: 300 },
    limits: { api_memory_max_mb: 16, api_max_entries: 1024, image_max_mb: 512 },
    api: [],
    images: [],
    stats: {},
  },
};
const editing = { bindingSession: null, controlSession: null, aliasServer: null, kungfuPzid: null, subscriptionSession: null, teamRuleId: null };
const expandedTeamIds = new Set();
let subscriptionSaving = false;
const restoreConfirmationTimers = new WeakMap();
let toastTimer;

const byId = (id) => document.getElementById(id);

function formatUsageCount(value) {
  return Number.isSafeInteger(value) && value >= 0
    ? value.toLocaleString("zh-CN")
    : "—";
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
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
    ...state.teams.map((item) => item.session_id),
    ...state.team_rule_sessions,
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

function renderLegacyBilei() {
  const records = state.legacy_bilei || [];
  const body = byId("legacy-bilei-body");
  byId("legacy-bilei-count").textContent = String(records.length);
  if (!records.length) {
    body.replaceChildren(emptyRow(7, "没有待迁移的旧避雷数据"));
    return;
  }

  body.replaceChildren(...records.map((item) => {
    const row = document.createElement("tr");
    const id = document.createElement("td");
    const name = document.createElement("td");
    const note = document.createElement("td");
    const time = document.createElement("td");
    const user = document.createElement("td");
    const target = document.createElement("td");
    const actions = document.createElement("td");
    id.dataset.label = "ID";
    name.dataset.label = "避雷名称";
    note.dataset.label = "避雷备注";
    time.dataset.label = "时间";
    user.dataset.label = "记录人";
    target.dataset.label = "目标会话";
    actions.dataset.label = "操作";
    id.textContent = String(item.id);
    name.textContent = item.name || "—";
    note.textContent = item.text || "—";
    note.className = "legacy-note-cell";
    time.textContent = item.time || "—";
    user.textContent = item.user || "—";
    target.className = "legacy-session-cell";
    actions.className = "actions";

    const sessionInput = document.createElement("input");
    sessionInput.className = "inline-editor";
    sessionInput.maxLength = 512;
    sessionInput.required = true;
    sessionInput.setAttribute("list", "session-options");
    sessionInput.setAttribute("aria-label", `避雷记录 ${item.id} 的目标会话`);
    sessionInput.placeholder = "选择已有会话或直接输入";
    target.append(sessionInput);

    const migrateButton = button("迁移", "", async () => {
      if (!sessionInput.reportValidity()) return;
      sessionInput.disabled = true;
      migrateButton.disabled = true;
      const migrated = await mutate(
        "bilei/legacy/migrate",
        { id: item.id, session_id: sessionInput.value },
        `避雷记录 ${item.id} 已迁移`,
      );
      if (!migrated) {
        sessionInput.disabled = false;
        migrateButton.disabled = false;
        sessionInput.focus();
      }
    });
    sessionInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        migrateButton.click();
      }
    });
    actions.append(migrateButton);
    row.append(id, name, note, time, user, target, actions);
    return row;
  }));
}

function openSubscriptionEditor(item = null) {
  if (subscriptionSaving) return;
  editing.subscriptionSession = item?.session_id ?? null;
  const form = byId("subscription-form");
  form.reset();
  byId("subscription-editor-title").textContent = item ? "编辑推送配置" : "添加推送会话";
  const sessionInput = byId("subscription-session");
  sessionInput.value = item?.session_id || "";
  sessionInput.readOnly = Boolean(item);
  byId("subscription-enabled").checked = item?.enabled ?? false;

  const selected = new Set(item?.actions || []);
  const freeActions = new Set(state.free_event_actions);
  const groups = [
    { title: "免费事件", free: true },
    { title: "令牌事件", free: false },
  ];
  byId("subscription-events").replaceChildren(...groups.map((group) => {
    const fieldset = document.createElement("fieldset");
    fieldset.className = "subscription-event-group";
    const legend = document.createElement("legend");
    legend.textContent = group.title;
    const grid = document.createElement("div");
    grid.className = "subscription-event-grid";
    Object.entries(state.events).forEach(([action, name]) => {
      if (freeActions.has(Number(action)) !== group.free) return;
      const label = document.createElement("label");
      label.className = "subscription-choice";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "subscription_action";
      input.value = action;
      input.checked = selected.has(Number(action));
      const text = document.createElement("span");
      text.textContent = `${action} ${name}`;
      label.append(input, text);
      grid.append(label);
    });
    fieldset.append(legend, grid);
    return fieldset;
  }));
  updateSubscriptionSelectionCount();
  form.hidden = false;
  form.scrollIntoView({ block: "nearest" });
  (item ? byId("subscription-enabled") : sessionInput).focus({ preventScroll: true });
}

function updateSubscriptionSelectionCount() {
  const count = byId("subscription-events").querySelectorAll("input:checked").length;
  byId("subscription-selection-count").textContent = `已选择 ${count} 项`;
}

function renderSubscriptions() {
  const body = byId("subscriptions-body");
  const bindings = bindingMap();
  if (!state.subscriptions.length) {
    body.replaceChildren(emptyRow(5, "暂无事件订阅会话，点击“添加推送会话”开始配置"));
    return;
  }
  body.replaceChildren(...state.subscriptions.map((item) => {
    const row = document.createElement("tr");
    const session = document.createElement("td");
    const server = document.createElement("td");
    const enabled = document.createElement("td");
    const actions = document.createElement("td");
    const controls = document.createElement("td");
    session.dataset.label = "会话 ID";
    server.dataset.label = "绑定区服";
    enabled.dataset.label = "总开关";
    actions.dataset.label = "已订阅事件";
    controls.dataset.label = "操作";
    controls.className = "actions";
    session.className = "subscription-session-cell";
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
    controls.append(
      button("编辑", "", () => openSubscriptionEditor(item)),
      button("删除", "link-button--danger", async (event) => {
        if (subscriptionSaving) return;
        const control = event.currentTarget;
        control.disabled = true;
        subscriptionSaving = true;
        byId("subscription-fields").disabled = true;
        byId("add-subscription").disabled = true;
        try {
          const deleted = await mutate(
            "subscriptions/delete",
            { session_id: item.session_id },
            "会话推送配置已删除",
          );
          if (deleted && editing.subscriptionSession === item.session_id) {
            byId("subscription-form").hidden = true;
            editing.subscriptionSession = null;
          }
        } finally {
          subscriptionSaving = false;
          control.disabled = false;
          byId("subscription-fields").disabled = false;
          byId("add-subscription").disabled = false;
        }
      }),
    );
    row.append(session, server, enabled, actions, controls);
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
  byId("kungfu-options").replaceChildren(...state.kungfu.map((item) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.label = `${roleTypeLabel(item.role_type)}｜${item.aliases.join("、")}`;
    return option;
  }));
  if (!state.kungfu.length) {
    body.replaceChildren(emptyRow(4, "暂无心法配置"));
    return;
  }
  body.replaceChildren(...state.kungfu.map((item) => {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    const roleType = document.createElement("td");
    const aliases = document.createElement("td");
    const actions = document.createElement("td");
    name.dataset.label = "标准心法名";
    roleType.dataset.label = "职责";
    aliases.dataset.label = "别名";
    actions.dataset.label = "操作";
    name.textContent = item.name;
    const roleSelect = document.createElement("select");
    roleSelect.className = "inline-editor inline-editor--compact";
    roleSelect.setAttribute("aria-label", `${item.name}的职责`);
    [["T", "T"], ["HEALER", "奶"], ["DPS", "DPS"]].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      roleSelect.append(option);
    });
    roleSelect.value = item.role_type;
    roleSelect.addEventListener("change", async () => {
      roleSelect.disabled = true;
      const saved = await mutate(
        "kungfu/role-type",
        { pzid: item.pzid, role_type: roleSelect.value },
        `${item.name}的职责已保存`,
      );
      if (!saved) roleSelect.disabled = false;
    });
    roleType.append(roleSelect);
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
    row.append(name, roleType, aliases, actions);
    return row;
  }));
}

function cacheSettingRow(cacheType, item) {
  const row = document.createElement("tr");
  const name = document.createElement("td");
  const ttl = document.createElement("td");
  const status = document.createElement("td");
  const actions = document.createElement("td");
  name.dataset.label = cacheType === "api" ? "接口路径" : "图片指令";
  ttl.dataset.label = "缓存时间（秒）";
  status.dataset.label = "配置状态";
  actions.dataset.label = "操作";
  name.textContent = item.name;
  name.className = "cache-name-cell";
  actions.className = "actions";

  const input = document.createElement("input");
  input.className = "inline-editor inline-editor--ttl";
  input.type = "number";
  input.min = "0";
  input.max = "2592000";
  input.step = "1";
  input.required = true;
  input.value = String(item.ttl_seconds);
  input.setAttribute("aria-label", `${item.name}缓存时间（秒）`);
  ttl.append(input);

  const badge = document.createElement("span");
  badge.className = `cache-badge ${item.overridden ? "cache-badge--custom" : ""}`.trim();
  badge.textContent = item.overridden
    ? "独立设置"
    : item.safe_default
      ? "安全默认"
      : "继承默认";
  status.append(badge);

  const saveButton = button("保存", "", async () => {
    if (!input.reportValidity()) return;
    saveButton.disabled = true;
    restoreButton.disabled = true;
    const saved = await mutate(
      "cache/settings/save",
      { cache_type: cacheType, cache_name: item.name, ttl_seconds: Number(input.value) },
      `${item.name}缓存时间已保存`,
    );
    if (!saved) {
      saveButton.disabled = false;
      restoreButton.disabled = false;
    }
  });
  const restoreButton = button("恢复默认", "", async () => {
    restoreButton.disabled = true;
    saveButton.disabled = true;
    const saved = await mutate(
      "cache/settings/save",
      { cache_type: cacheType, cache_name: item.name, inherit: true },
      `${item.name}已恢复默认时间`,
    );
    if (!saved) {
      restoreButton.disabled = false;
      saveButton.disabled = false;
    }
  });
  const clearButton = button("清除此项", "link-button--danger", async () => {
    clearButton.disabled = true;
    const cleared = await mutate(
      "cache/item/clear",
      { cache_type: cacheType, cache_name: item.name },
      `${item.name}缓存已清除，下次调用将重新生成`,
    );
    if (!cleared) clearButton.disabled = false;
  });
  restoreButton.disabled = !item.overridden;
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveButton.click();
    }
  });
  actions.append(saveButton, restoreButton, clearButton);
  row.append(name, ttl, status, actions);
  return row;
}

function renderCacheTable(cacheType) {
  const isApi = cacheType === "api";
  const items = isApi ? state.cache.api : state.cache.images;
  const filter = byId(isApi ? "api-cache-filter" : "image-cache-filter")
    .value.trim().toLocaleLowerCase("zh-CN");
  const visible = items.filter((item) => item.name.toLocaleLowerCase("zh-CN").includes(filter));
  const body = byId(isApi ? "api-cache-settings-body" : "image-cache-settings-body");
  body.replaceChildren(...(
    visible.length
      ? visible.map((item) => cacheSettingRow(cacheType, item))
      : [emptyRow(4, filter ? "没有匹配的缓存项目" : "暂无缓存项目")]
  ));
}

function renderCache() {
  const cache = state.cache || { defaults: {}, limits: {}, api: [], images: [], stats: {} };
  const stats = cache.stats || {};
  const apiDefault = cache.defaults?.api ?? 300;
  const imageDefault = cache.defaults?.image ?? 600;
  const memoryLimitMb = cache.limits?.api_memory_max_mb ?? 16;
  const apiEntryLimit = cache.limits?.api_max_entries ?? stats.api_entry_limit ?? 256;
  const imageLimitMb = cache.limits?.image_max_mb ?? 512;
  byId("api-cache-count").textContent = `${stats.api_count || 0} / ${apiEntryLimit} 条`;
  byId("api-cache-size").textContent = formatBytes(stats.api_size_bytes);
  byId("image-cache-count").textContent = `${stats.image_count || 0} 张`;
  byId("image-cache-size").textContent = `${formatBytes(stats.image_size_bytes)} / ${formatBytes(stats.image_limit_bytes)}`;
  byId("api-default-ttl").value = String(apiDefault);
  byId("image-default-ttl").value = String(imageDefault);
  byId("api-memory-size-limit").value = String(memoryLimitMb);
  byId("api-entry-limit").value = String(apiEntryLimit);
  byId("image-size-limit").value = String(imageLimitMb);
  byId("api-memory-summary").textContent = `${formatBytes(stats.api_memory_size_bytes)} / ${formatBytes(stats.api_memory_limit_bytes)}`;
  byId("api-memory-count").textContent = `${stats.api_memory_count || 0} 条，最久未使用优先淘汰`;
  byId("cache-default-summary").textContent = `${apiDefault} / ${imageDefault} 秒`;
  renderCacheTable("api");
  renderCacheTable("image");
}

function roleTypeLabel(value) {
  if (value === "HEALER") return "奶";
  if (value === "BOSS") return "老板";
  return value;
}

function selectedTeamRuleScope() {
  const value = byId("team-rule-scope").value;
  if (value.startsWith("team:")) {
    const teamId = Number(value.slice(5));
    const team = state.teams.find((item) => item.id === teamId);
    return { team_id: teamId, capacity: team?.capacity || 25 };
  }
  return { team_id: 0, capacity: Number(value.split(":")[1] || 25) };
}

function renderTeamRuleScopeOptions() {
  const sessionId = byId("team-rule-session").value.trim();
  const select = byId("team-rule-scope");
  const previous = select.value;
  const entries = [
    { value: "default:10", label: "会话默认 · 10 人" },
    { value: "default:25", label: "会话默认 · 25 人" },
    ...state.teams
      .filter((team) => team.session_id === sessionId)
      .map((team) => ({
        value: `team:${team.id}`,
        label: `团队 #${team.id} ${team.name} · ${team.capacity} 人`,
      })),
  ];
  select.replaceChildren(...entries.map((entry) => {
    const option = document.createElement("option");
    option.value = entry.value;
    option.textContent = entry.label;
    return option;
  }));
  select.value = entries.some((entry) => entry.value === previous)
    ? previous
    : "default:10";
  if (state.team_rule_config) {
    const selected = selectedTeamRuleScope();
    if (
      state.team_rule_config.session_id !== sessionId
      || state.team_rule_config.team_id !== selected.team_id
      || state.team_rule_config.capacity !== selected.capacity
    ) {
      state.team_rule_config = null;
      resetTeamRuleEditor();
    }
  }
}

function renderTeamRuleTargets(selectedValue = "") {
  const type = byId("team-rule-type").value;
  const target = byId("team-rule-target");
  let entries;
  if (type === "role") {
    entries = [
      { value: "T", label: "T" },
      { value: "HEALER", label: "奶" },
      { value: "DPS", label: "DPS" },
      { value: "BOSS", label: "老板" },
    ];
  } else {
    entries = state.kungfu.map((item) => ({ value: item.name, label: item.name }));
  }
  target.replaceChildren(...entries.map((entry) => {
    const option = document.createElement("option");
    option.value = entry.value;
    option.textContent = entry.label;
    return option;
  }));
  target.disabled = false;
  target.value = entries.some((entry) => entry.value === selectedValue)
    ? selectedValue
    : entries[0]?.value || "";
}

function resetTeamRuleEditor() {
  editing.teamRuleId = null;
  byId("team-rule-id").value = "";
  byId("team-rule-type").value = "role";
  renderTeamRuleTargets();
  byId("team-rule-min").value = "0";
  byId("team-rule-max").value = String(state.team_rule_config?.capacity || 25);
  byId("team-rule-form").querySelector('button[type="submit"]').textContent = "新增规则";
  byId("team-rule-cancel").hidden = true;
}

function teamRuleTargetLabel(rule) {
  if (rule.rule_type === "role") return roleTypeLabel(rule.target_value);
  return rule.target_value;
}

function teamRuleTypeLabel(ruleType) {
  return { role: "职责", kungfu: "心法" }[ruleType] || ruleType;
}

function renderTeamRuleConfig() {
  const config = state.team_rule_config;
  const fields = byId("team-rule-fields");
  const reset = byId("team-rule-reset");
  if (!config) {
    fields.disabled = true;
    reset.hidden = true;
    byId("team-rule-status").textContent = "请先选择会话和规则范围。";
    byId("team-rule-body").replaceChildren(emptyRow(5, "尚未读取规则"));
    return;
  }

  fields.disabled = false;
  byId("team-rule-min").max = String(config.capacity);
  byId("team-rule-max").max = String(config.capacity);
  const isTeam = config.team_id > 0;
  reset.hidden = !isTeam || config.inherited;
  byId("team-rule-status").textContent = isTeam
    ? config.inherited
      ? `团队 #${config.team_id} 正在继承该会话的 ${config.capacity} 人默认规则；首次保存会复制默认规则并转为独立配置。`
      : `团队 #${config.team_id} 正在使用独立规则，可恢复为继承 ${config.capacity} 人默认规则。`
    : `正在配置该会话的 ${config.capacity} 人默认规则。`;

  const body = byId("team-rule-body");
  if (!config.rules.length) {
    body.replaceChildren(emptyRow(5, "暂无限制规则，报名只受团队人数上限约束"));
    return;
  }
  body.replaceChildren(...config.rules.map((rule) => {
    const row = document.createElement("tr");
    const type = document.createElement("td");
    const target = document.createElement("td");
    const minimum = document.createElement("td");
    const maximum = document.createElement("td");
    const actions = document.createElement("td");
    type.dataset.label = "类型";
    target.dataset.label = "目标";
    minimum.dataset.label = "最小数量";
    maximum.dataset.label = "最大数量";
    actions.dataset.label = "操作";
    type.textContent = teamRuleTypeLabel(rule.rule_type);
    target.textContent = teamRuleTargetLabel(rule);
    minimum.textContent = String(rule.min_count);
    maximum.textContent = String(rule.max_count);
    actions.className = "actions";
    actions.append(button("编辑", "", () => {
      editing.teamRuleId = rule.id;
      byId("team-rule-id").value = String(rule.id);
      byId("team-rule-type").value = rule.rule_type;
      renderTeamRuleTargets(rule.target_value);
      byId("team-rule-min").value = String(rule.min_count);
      byId("team-rule-max").value = String(rule.max_count);
      byId("team-rule-form").querySelector('button[type="submit"]').textContent = "保存修改";
      byId("team-rule-cancel").hidden = false;
    }));
    if (!config.inherited) {
      actions.append(button("删除", "link-button--danger", async (event) => {
        if (!confirmRestoreInPage(
          event.currentTarget,
          `再次点击“删除”，确认移除“${teamRuleTargetLabel(rule)}”限制`,
        )) return;
        await mutateTeamRule("team-rules/delete", { rule_id: rule.id }, "限制规则已删除");
      }));
    }
    row.append(type, target, minimum, maximum, actions);
    return row;
  }));
}

async function loadTeamRuleConfig() {
  const sessionId = byId("team-rule-session").value.trim();
  if (!sessionId) {
    showToast("会话 ID 不能为空", true);
    byId("team-rule-session").focus();
    return false;
  }
  const scope = selectedTeamRuleScope();
  try {
    const result = await bridge.apiPost("team-rules/config", {
      session_id: sessionId,
      ...scope,
    });
    if (result?.team_not_found) {
      showToast("团队不存在，已刷新团队列表", true);
      await loadData();
      return false;
    }
    state.team_rule_config = result.config;
    resetTeamRuleEditor();
    renderTeamRuleConfig();
    return true;
  } catch (error) {
    showToast(error?.message || "读取限制规则失败", true);
    return false;
  }
}

async function mutateTeamRule(endpoint, extraPayload, successMessage) {
  const config = state.team_rule_config;
  if (!config) return false;
  try {
    const result = await bridge.apiPost(endpoint, {
      session_id: config.session_id,
      capacity: config.capacity,
      team_id: config.team_id,
      ...extraPayload,
    });
    if (result?.team_not_found) {
      showToast("团队不存在，已刷新团队列表", true);
      await loadData();
      return false;
    }
    state.team_rule_config = result.config;
    resetTeamRuleEditor();
    renderTeamRuleConfig();
    showToast(successMessage);
    return true;
  } catch (error) {
    showToast(error?.message || "限制规则操作失败", true);
    return false;
  }
}

async function runTeamAction(endpoint, payload, successMessage) {
  try {
    const result = await bridge.apiPost(endpoint, payload);
    await loadData();
    if (result?.team_not_found) {
      showToast("团队编号不存在，已刷新该会话的团队列表", true);
      return false;
    }
    showToast(successMessage);
    return true;
  } catch (error) {
    showToast(error?.message || "团队操作失败", true);
    return false;
  }
}

function renderTeams() {
  const filter = byId("team-session-filter").value.trim();
  const teams = state.teams.filter((team) => !filter || team.session_id.includes(filter));
  const list = byId("team-list");
  if (!teams.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = filter ? "该会话暂无团队" : "暂无团队，请先使用上方表单开团";
    list.replaceChildren(empty);
    return;
  }

  list.replaceChildren(...teams.map((team) => {
    const card = document.createElement("article");
    card.className = "team-card";
    const isExpanded = expandedTeamIds.has(team.id);

    const header = document.createElement("header");
    header.className = "team-card__header";
    const headingWrap = document.createElement("div");
    const title = document.createElement("div");
    title.className = "team-card__title";
    const heading = document.createElement("h3");
    heading.textContent = `#${team.id} ${team.name}`;
    const status = document.createElement("span");
    status.className = `state ${team.registration_open ? "state--on" : "state--off"}`;
    status.textContent = team.registration_open ? "报名中" : "未开放";
    title.append(heading, status);
    const meta = document.createElement("p");
    meta.className = "team-card__meta";
    meta.textContent = `${team.session_id}｜${team.member_count}/${team.capacity} 人｜老板 ${team.boss_count} 人｜创建于 ${team.created_at}`;
    headingWrap.append(title, meta);

    const actions = document.createElement("div");
    actions.className = "team-card__actions";
    const toggleDetails = button(isExpanded ? "折叠详情" : "展开详情", "", () => {
      const expanded = !expandedTeamIds.has(team.id);
      if (expanded) expandedTeamIds.add(team.id);
      else expandedTeamIds.delete(team.id);
      details.hidden = !expanded;
      toggleDetails.textContent = expanded ? "折叠详情" : "展开详情";
      toggleDetails.setAttribute("aria-expanded", String(expanded));
    });
    toggleDetails.setAttribute("aria-expanded", String(isExpanded));
    actions.append(
      toggleDetails,
      button(team.registration_open ? "关闭报名" : "打开报名", "", async (event) => {
        const control = event.currentTarget;
        control.disabled = true;
        const saved = await runTeamAction(
          "teams/registration",
          { session_id: team.session_id, team_id: team.id, registration_open: !team.registration_open },
          `团队 #${team.id} 已${team.registration_open ? "关闭" : "打开"}报名`,
        );
        if (!saved) control.disabled = false;
      }),
      button("清空报名", "", async (event) => {
        if (!confirmRestoreInPage(
          event.currentTarget,
          `再次点击“清空报名”，确认移除团队 #${team.id} 的全部 ${team.member_count} 条报名`,
        )) return;
        await runTeamAction(
          "teams/clear",
          { session_id: team.session_id, team_id: team.id },
          `团队 #${team.id} 的报名已清空`,
        );
      }),
      button("结束团队", "link-button--danger", async (event) => {
        if (!confirmRestoreInPage(
          event.currentTarget,
          `再次点击“结束团队”，确认删除团队 #${team.id} 及其全部报名`,
        )) return;
        await runTeamAction(
          "teams/delete",
          { session_id: team.session_id, team_id: team.id },
          `团队 #${team.id} 已结束`,
        );
      }),
    );
    header.append(headingWrap, actions);

    const announcement = document.createElement("p");
    announcement.className = "team-announcement";
    announcement.textContent = `公告：${team.announcement || "无"}`;

    const memberEditor = document.createElement("form");
    memberEditor.className = "team-member-editor";
    memberEditor.hidden = true;
    const editorTitle = document.createElement("strong");
    editorTitle.className = "team-member-editor__title";
    const originalName = document.createElement("input");
    originalName.type = "hidden";
    const nameLabel = document.createElement("label");
    nameLabel.innerHTML = "<span>角色名</span>";
    const nameInput = document.createElement("input");
    nameInput.required = true;
    nameInput.maxLength = 80;
    nameLabel.append(nameInput);
    const editKungfuLabel = document.createElement("label");
    editKungfuLabel.innerHTML = "<span>心法</span>";
    const editKungfuInput = document.createElement("input");
    editKungfuInput.required = true;
    editKungfuInput.maxLength = 50;
    editKungfuInput.setAttribute("list", "kungfu-options");
    editKungfuLabel.append(editKungfuInput);
    const editBossLabel = document.createElement("label");
    editBossLabel.className = "team-boss-choice";
    const editBossInput = document.createElement("input");
    editBossInput.type = "checkbox";
    editBossLabel.append(editBossInput, "标记为老板");
    const editorActions = document.createElement("div");
    editorActions.className = "team-member-editor__actions";
    const saveMember = document.createElement("button");
    saveMember.className = "button button--primary";
    saveMember.type = "submit";
    saveMember.textContent = "保存成员";
    const cancelEdit = button("取消", "", () => {
      memberEditor.hidden = true;
    });
    editorActions.append(saveMember, cancelEdit);
    memberEditor.append(
      editorTitle,
      originalName,
      nameLabel,
      editKungfuLabel,
      editBossLabel,
      editorActions,
    );
    memberEditor.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!memberEditor.reportValidity()) return;
      saveMember.disabled = true;
      const saved = await runTeamAction(
        "teams/member-update",
        {
          session_id: team.session_id,
          team_id: team.id,
          role_name: originalName.value,
          new_role_name: nameInput.value,
          kungfu: editKungfuInput.value,
          is_boss: editBossInput.checked,
        },
        `${nameInput.value} 的报名信息已更新`,
      );
      if (!saved) saveMember.disabled = false;
    });

    const openMemberEditor = (member) => {
      originalName.value = member.role_name;
      nameInput.value = member.role_name;
      editKungfuInput.value = member.kungfu;
      editBossInput.checked = Boolean(member.is_boss);
      editorTitle.textContent = `修改 ${member.role_name}`;
      memberEditor.hidden = false;
      nameInput.focus();
    };

    const slots = document.createElement("div");
    slots.className = "team-slots";
    slots.style.setProperty("--team-columns", String(team.capacity / 5));
    for (let slotNumber = 1; slotNumber <= team.capacity; slotNumber += 1) {
      const member = team.members.find((item) => item.slot_number === slotNumber);
      const cell = document.createElement("div");
      cell.dataset.slot = String(slotNumber);
      cell.setAttribute("aria-label", member ? `${member.role_name}，${member.kungfu}` : "空位置");
      if (!member) {
        cell.className = "team-slot team-slot--empty";
        cell.textContent = "空";
      } else {
        const roleClass = member.is_boss
          ? "boss"
          : { T: "tank", HEALER: "healer", DPS: "dps" }[member.role_type] || "dps";
        cell.className = `team-slot team-slot--member team-slot--${roleClass}`;
        cell.draggable = true;

        const icon = document.createElement("img");
        icon.className = "team-slot__icon";
        icon.alt = "";
        const iconSource = state.team_kungfu_icons?.[member.kungfu];
        if (iconSource) {
          icon.src = iconSource;
          icon.addEventListener("error", () => { icon.hidden = true; });
        } else {
          icon.hidden = true;
        }
        const memberText = document.createElement("div");
        memberText.className = "team-slot__content";
        const memberName = document.createElement("strong");
        memberName.className = "team-slot__name";
        memberName.textContent = member.role_name;
        const kungfu = document.createElement("span");
        kungfu.className = "team-slot__kungfu";
        kungfu.textContent = member.kungfu;
        memberText.append(memberName, kungfu);
        const memberActions = document.createElement("div");
        memberActions.className = "team-slot__actions";
        const editMember = button("编辑", "", (event) => {
          event.stopPropagation();
          openMemberEditor(member);
        });
        editMember.draggable = false;
        const remove = button("移除", "link-button--danger", async (event) => {
          event.stopPropagation();
          if (!confirmRestoreInPage(
            event.currentTarget,
            `再次点击“移除”，确认将 ${member.role_name} 移出团队 #${team.id}`,
          )) return;
          await runTeamAction(
            "teams/cancel",
            { session_id: team.session_id, team_id: team.id, role_name: member.role_name },
            `${member.role_name} 已移出团队 #${team.id}`,
          );
        });
        remove.draggable = false;
        memberActions.append(editMember, remove);
        cell.append(icon, memberText, memberActions);
        cell.addEventListener("click", (event) => {
          if (!event.target.closest("button")) openMemberEditor(member);
        });
        cell.addEventListener("dragstart", (event) => {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", String(slotNumber));
          cell.classList.add("is-dragging");
        });
        cell.addEventListener("dragend", () => {
          cell.classList.remove("is-dragging");
          slots.querySelectorAll(".is-drop-target").forEach((item) => {
            item.classList.remove("is-drop-target");
          });
        });
      }
      cell.addEventListener("dragover", (event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        cell.classList.add("is-drop-target");
      });
      cell.addEventListener("dragleave", () => cell.classList.remove("is-drop-target"));
      cell.addEventListener("drop", async (event) => {
        event.preventDefault();
        cell.classList.remove("is-drop-target");
        const firstSlot = Number(event.dataTransfer.getData("text/plain"));
        if (!firstSlot || firstSlot === slotNumber) return;
        await runTeamAction(
          "teams/swap",
          {
            session_id: team.session_id,
            team_id: team.id,
            first_slot: firstSlot,
            second_slot: slotNumber,
          },
          `团队 #${team.id} 的位置已调整`,
        );
      });
      slots.append(cell);
    }

    const signup = document.createElement("form");
    signup.className = "team-signup-form";
    const kungfuLabel = document.createElement("label");
    kungfuLabel.innerHTML = "<span>心法</span>";
    const kungfuInput = document.createElement("input");
    kungfuInput.maxLength = 50;
    kungfuInput.placeholder = "标准心法或别名";
    kungfuInput.required = true;
    kungfuInput.setAttribute("list", "kungfu-options");
    kungfuLabel.append(kungfuInput);
    const roleLabel = document.createElement("label");
    roleLabel.innerHTML = "<span>角色名</span>";
    const roleInput = document.createElement("input");
    roleInput.maxLength = 80;
    roleInput.placeholder = "游戏角色名";
    roleInput.required = true;
    roleLabel.append(roleInput);
    const bossLabel = document.createElement("label");
    bossLabel.className = "team-boss-choice";
    const bossInput = document.createElement("input");
    bossInput.type = "checkbox";
    bossLabel.append(bossInput, "标记为老板");
    const submit = document.createElement("button");
    submit.className = "button button--primary";
    submit.type = "submit";
    submit.textContent = "添加报名";
    signup.append(kungfuLabel, roleLabel, bossLabel, submit);
    signup.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      const saved = await runTeamAction(
        "teams/signup",
        {
          session_id: team.session_id,
          team_id: team.id,
          kungfu: kungfuInput.value,
          role_name: roleInput.value,
          is_boss: bossInput.checked,
        },
        `${roleInput.value} 已加入团队 #${team.id}`,
      );
      if (!saved) submit.disabled = false;
    });

    const details = document.createElement("div");
    details.className = "team-card__details";
    details.hidden = !isExpanded;
    details.append(announcement, slots, memberEditor, signup);
    card.append(header, details);
    return card;
  }));
}

function render() {
  renderTokenStats();
  renderServerOptions();
  renderSessionOptions();
  renderSessionControl();
  renderLegacyBilei();
  renderBindings();
  renderSubscriptions();
  renderAliases();
  renderKungfu();
  renderCache();
  renderTeamRuleScopeOptions();
  renderTeamRuleTargets(byId("team-rule-target").value);
  renderTeamRuleConfig();
  renderTeams();
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
  control.textContent = control.dataset.confirmLabel || "恢复默认";
  delete control.dataset.confirmLabel;
}

function confirmRestoreInPage(control, confirmation) {
  if (control.dataset.confirming === "true") {
    resetRestoreConfirmation(control);
    return true;
  }

  control.dataset.confirmLabel = control.textContent;
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

byId("add-subscription").addEventListener("click", () => openSubscriptionEditor());
byId("cancel-subscription").addEventListener("click", () => {
  byId("subscription-form").hidden = true;
  editing.subscriptionSession = null;
});
byId("subscription-events").addEventListener("change", updateSubscriptionSelectionCount);
byId("subscription-select-all").addEventListener("click", () => {
  byId("subscription-events").querySelectorAll("input").forEach((input) => { input.checked = true; });
  updateSubscriptionSelectionCount();
});
byId("subscription-clear-all").addEventListener("click", () => {
  byId("subscription-events").querySelectorAll("input").forEach((input) => { input.checked = false; });
  updateSubscriptionSelectionCount();
});
byId("subscription-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (subscriptionSaving) return;
  const form = event.currentTarget;
  const sessionId = (editing.subscriptionSession ?? byId("subscription-session").value).trim();
  if (!sessionId) {
    showToast("会话 ID 不能为空", true);
    byId("subscription-session").focus();
    return;
  }
  const payload = {
    session_id: sessionId,
    enabled: byId("subscription-enabled").checked,
    actions: [...byId("subscription-events").querySelectorAll("input:checked")].map((input) => Number(input.value)),
    mode: editing.subscriptionSession === null ? "create" : "update",
  };
  subscriptionSaving = true;
  byId("subscription-fields").disabled = true;
  byId("add-subscription").disabled = true;
  try {
    const saved = await mutate("subscriptions/save", payload, "会话推送配置已保存");
    if (saved) {
      form.hidden = true;
      editing.subscriptionSession = null;
    }
  } finally {
    subscriptionSaving = false;
    byId("subscription-fields").disabled = false;
    byId("add-subscription").disabled = false;
  }
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

byId("team-session-filter").addEventListener("input", (event) => {
  const sessionId = event.currentTarget.value.trim();
  if (sessionId) {
    byId("team-create-session").value = sessionId;
    byId("team-rule-session").value = sessionId;
  }
  renderTeamRuleScopeOptions();
  renderTeamRuleConfig();
  renderTeams();
});

byId("team-rule-session").addEventListener("input", () => {
  renderTeamRuleScopeOptions();
  renderTeamRuleConfig();
});
byId("team-rule-scope").addEventListener("change", () => {
  state.team_rule_config = null;
  resetTeamRuleEditor();
  renderTeamRuleConfig();
});
byId("team-rule-load").addEventListener("click", loadTeamRuleConfig);
byId("team-rule-type").addEventListener("change", () => renderTeamRuleTargets());
byId("team-rule-cancel").addEventListener("click", resetTeamRuleEditor);
byId("team-rule-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  await mutateTeamRule(
    "team-rules/save",
    {
      rule_id: Number(byId("team-rule-id").value) || 0,
      rule_type: byId("team-rule-type").value,
      target_value: byId("team-rule-target").value,
      min_count: Number(byId("team-rule-min").value),
      max_count: Number(byId("team-rule-max").value),
    },
    editing.teamRuleId ? "限制规则已修改" : "限制规则已添加",
  );
});
byId("team-rule-reset").addEventListener("click", async (event) => {
  const config = state.team_rule_config;
  if (!config?.team_id) return;
  if (!confirmRestoreInPage(
    event.currentTarget,
    `再次点击“恢复继承默认”，确认删除团队 #${config.team_id} 的专属规则`,
  )) return;
  await mutateTeamRule("team-rules/reset", {}, "团队已恢复继承默认规则");
});

byId("team-create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const sessionId = byId("team-create-session").value;
  const saved = await runTeamAction(
    "teams/create",
    {
      session_id: sessionId,
      name: byId("team-create-name").value,
      capacity: Number(byId("team-create-capacity").value),
      announcement: byId("team-create-announcement").value,
    },
    "团队已创建，当前默认关闭报名",
  );
  if (saved) {
    event.currentTarget.reset();
    byId("team-create-session").value = sessionId;
  }
});

byId("team-delete-all").addEventListener("click", async (event) => {
  const sessionId = byId("team-session-filter").value.trim();
  if (!sessionId) {
    showToast("请先在筛选框中输入要结束全部团队的完整会话 ID", true);
    byId("team-session-filter").focus();
    return;
  }
  if (!confirmRestoreInPage(
    event.currentTarget,
    `再次点击“结束该会话全部团队”，确认删除会话 ${sessionId} 的全部团队及报名`,
  )) return;
  await runTeamAction(
    "teams/delete-all",
    { session_id: sessionId },
    `会话 ${sessionId} 的全部团队已结束`,
  );
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
    "再次点击按钮，确认恢复全部心法职责和内置别名",
    "心法职责与别名已恢复默认",
    () => { editing.kungfuPzid = null; },
  );
});

byId("api-cache-filter").addEventListener("input", () => renderCacheTable("api"));
byId("image-cache-filter").addEventListener("input", () => renderCacheTable("image"));

byId("cache-default-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await bridge.apiPost("cache/settings/save", {
      cache_type: "api",
      cache_name: "*",
      ttl_seconds: Number(byId("api-default-ttl").value),
    });
    await bridge.apiPost("cache/settings/save", {
      cache_type: "image",
      cache_name: "*",
      ttl_seconds: Number(byId("image-default-ttl").value),
    });
    await loadData();
    showToast("默认缓存时间已保存");
  } catch (error) {
    showToast(error?.message || "默认缓存时间保存失败", true);
  } finally {
    submit.disabled = false;
  }
});

byId("cache-limit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await bridge.apiPost("cache/limits/save", {
      api_memory_max_mb: Number(byId("api-memory-size-limit").value),
      api_max_entries: Number(byId("api-entry-limit").value),
      image_max_mb: Number(byId("image-size-limit").value),
    });
    await loadData();
    showToast("缓存容量限制已保存并立即生效");
  } catch (error) {
    showToast(error?.message || "缓存容量限制保存失败", true);
  } finally {
    submit.disabled = false;
  }
});

async function clearCache(cacheType, control) {
  control.disabled = true;
  try {
    const result = await bridge.apiPost("cache/clear", { cache_type: cacheType });
    await loadData();
    const removed = result?.removed?.[cacheType] ?? 0;
    showToast(`${cacheType === "api" ? "接口" : "图片"}缓存已清空，共清理 ${removed} 项`);
  } catch (error) {
    showToast(error?.message || "缓存清理失败", true);
  } finally {
    control.disabled = false;
  }
}

byId("clear-api-cache").addEventListener("click", (event) => {
  clearCache("api", event.currentTarget);
});
byId("clear-image-cache").addEventListener("click", (event) => {
  clearCache("image", event.currentTarget);
});

byId("refresh").addEventListener("click", async (event) => {
  const control = event.currentTarget;
  control.disabled = true;
  try {
    await loadData();
    showToast("页面数据已刷新");
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
