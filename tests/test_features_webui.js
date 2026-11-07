const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const appPath = path.join(__dirname, "../pages/server-management/app.js");
const source = fs.readFileSync(appPath, "utf8");

function createPage() {
  const elements = new Map();
  const server = { 日常: true, 日常预测: true };
  const requests = [];
  const toasts = [];
  let inputs = [];
  let failFeatures = false;
  const byId = (id) => {
    if (!elements.has(id)) {
      elements.set(id, {
        disabled: false,
        handlers: {},
        value: "",
        addEventListener(name, callback) { this.handlers[name] = callback; },
      });
    }
    return elements.get(id);
  };
  const bridge = {
    async apiGet(endpoint) {
      requests.push(endpoint);
      if (endpoint === "dashboard") return {};
      assert.equal(endpoint, "features/status");
      if (failFeatures) throw new Error("Feature status unavailable");
      return {
        features: { ...server },
        feature_catalog: [{
          key: "activity_calendar",
          commands: Object.entries(server).map(([name, enabled]) => ({ name, enabled })),
        }],
      };
    },
    async apiPost(endpoint, payload) {
      if (endpoint === "features/save") Object.assign(server, payload.features.activity_calendar);
      return { saved: true };
    },
  };
  const context = vm.createContext({
    window: { AstrBotPluginPage: bridge },
    document: {
      getElementById: byId,
      querySelectorAll: (selector) => selector === "#feature-grid input[data-group]" ? inputs : [],
    },
    setTimeout,
    clearTimeout,
    draw(catalog) {
      inputs = catalog.flatMap((group) => group.commands.map((command) => ({
        dataset: { group: group.key, command: command.name },
        checked: command.enabled,
      })));
    },
    toast(message, error = false) { toasts.push({ message, error }); },
  });
  // Run the real handlers and API wiring without starting the host or a browser.
  vm.runInContext(source.slice(0, source.lastIndexOf("\nawait bridge.ready();")), context, { filename: appPath });
  vm.runInContext("renderFeatures = () => draw(state.feature_catalog); render = () => renderFeatures(); showToast = toast;", context);
  return {
    server,
    requests,
    toasts,
    byId,
    run: (script) => vm.runInContext(script, context),
    input: (command) => inputs.find((input) => input.dataset.command === command),
    failFeatures: () => { failFeatures = true; },
    refresh: () => byId("refresh").handlers.click({ currentTarget: byId("refresh") }),
  };
}

test("loading management data also loads the current feature switches", async () => {
  const page = createPage();
  await page.run("loadData()");
  assert.deepEqual(page.requests.sort(), ["dashboard", "features/status"]);
  assert.equal(page.input("日常").checked, true);
});

test("refresh preserves external switch updates when another command is saved", async () => {
  const page = createPage();
  await page.run("loadFeatures()");
  page.run("renderFeatures()");
  page.server.日常 = false;
  page.requests.length = 0;
  await page.refresh();
  assert.deepEqual(page.requests.sort(), ["dashboard", "features/status"]);
  assert.equal(page.input("日常").checked, false);
  page.input("日常预测").checked = false;
  await page.run("saveFeatures()");
  assert.equal(page.server.日常, false);
  assert.equal(page.server.日常预测, false);
  assert.equal(page.toasts.at(-1).error, false);
});

test("refresh after other management changes also uses current switch values", async () => {
  const page = createPage();
  await page.run("loadFeatures()");
  page.server.日常 = false;
  await page.run('mutate("bindings/save", {}, "Saved")');
  assert.equal(page.input("日常").checked, false);
});

test("a failed switch refresh reports failure and releases the refresh button", async () => {
  const page = createPage();
  await page.run("loadFeatures()");
  page.failFeatures();
  await page.refresh();
  assert.equal(page.toasts.at(-1).error, true);
  assert.equal(page.toasts.at(-1).message, "Feature status unavailable");
  assert.equal(page.byId("refresh").disabled, false);
});
