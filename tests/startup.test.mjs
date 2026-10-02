import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const appSource = readFileSync(new URL('../static/js/app.js', import.meta.url), 'utf8');
const bootSource = appSource.slice(appSource.indexOf('export async function boot()'), appSource.indexOf('\nfunction applyBootstrap')).replace('export ', '');
const routeSource = appSource.slice(appSource.indexOf('async function route('), appSource.indexOf('\nasync function loadProjects'));
const startupSource = readFileSync(new URL('../static/js/startup.js', import.meta.url), 'utf8').replace('import("./app.js")', 'importApp()');
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

function bootContext(overrides = {}) {
  const events = [], calls = [];
  const context = vm.createContext({
    state: { user: null }, location: { hash: '' },
    api: async () => ({ user: { id: 1 } }),
    applyBootstrap(data) { context.state.user = data.user; },
    route: async (options) => { calls.push(options); },
    window: { addEventListener: (...args) => events.push(args) },
    setInterval: () => { calls.push('poll'); }, poll() {}, toast() {}, ...overrides,
  });
  vm.runInContext(bootSource, context);
  return { context, events, calls };
}

test('bootstrap failure is surfaced instead of silently pretending logged out', async () => {
  const failure = Object.assign(new Error('unavailable'), { status: 503 });
  const { context, calls } = bootContext({ api: async () => { throw failure; } });
  await assert.rejects(context.boot(), failure);
  assert.equal(calls.length, 0);
});

test('401 renders login and establishes one navigation listener and polling interval', async () => {
  const { context, calls, events } = bootContext({ api: async () => { throw { status: 401 }; } });
  await context.boot();
  assert.equal(context.state.user, null);
  assert.equal(calls[0].useBootstrap, true);
  assert.equal(events.length, 1);
  assert.deepEqual(calls.slice(1), ['poll']);
});

test('hash changed during bootstrap navigation is caught up', async () => {
  const { context, events } = bootContext();
  let routes = 0;
  context.route = async () => { if (++routes === 1) context.location.hash = '#/account'; };
  await context.boot();
  assert.equal(routes, 2);
  assert.equal(events.length, 1);
});

test('failed catch-up navigation still installs recovery listener', async () => {
  const { context, events } = bootContext();
  let routes = 0;
  context.route = async () => {
    if (++routes === 1) context.location.hash = '#/account';
    else throw new Error('second route failed');
  };
  await assert.rejects(context.boot(), /second route failed/);
  assert.equal(events.length, 1);
});

test('projects reuse is initial-only; later and archived views refresh', async () => {
  let loads = 0, renders = 0;
  const context = vm.createContext({ state: { user: {}, showArchived: false }, location: { hash: '#/projects' },
    loadProjects: async () => { loads++; }, render: () => { renders++; } });
  vm.runInContext(routeSource, context);
  await context.route({ useBootstrap: true });
  assert.equal(loads, 0);
  await context.route();
  context.state.showArchived = true;
  await context.route({ useBootstrap: true });
  assert.equal(loads, 2);
  assert.equal(renders, 3);
});

function startupContext({ imported, autoLoad = true } = {}) {
  const callbacks = {}, timers = new Map();
  const message = { textContent: 'loading', setAttribute: (key, value) => { message[key] = value; } };
  const anchor = { addEventListener: (name, fn) => { anchor[name] = fn; } };
  const fallback = { querySelector: () => anchor };
  const styles = {
    sheet: {}, media: 'print', addEventListener: (name, fn) => { callbacks[name] = fn; },
    set href(value) {
      this.requestedHref = value;
      if (autoLoad) queueMicrotask(() => callbacks.load());
    },
  };
  const app = { replaceChildren: (node) => { app.child = node; } };
  const head = [];
  let boots = 0, reloads = 0;
  const context = vm.createContext({
    document: {
      getElementById: (id) => ({ 'app-styles': styles, 'startup-message': message, app })[id],
      querySelector: () => fallback,
      createElement: () => ({}), head: { append: node => head.push(node) },
    },
    location: { reload: () => reloads++ },
    importApp: () => imported || Promise.resolve({ boot: async () => { boots++; } }),
    setTimeout: fn => { const id = timers.size + 1; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
  });
  vm.runInContext(startupSource, context);
  return { message, styles, callbacks, timers, app, fallback, anchor, head, boots: () => boots, reloads: () => reloads };
}

test('stylesheet activates on load and fonts load only after boot', async () => {
  const ctx = startupContext();
  await flush();
  assert.equal(ctx.styles.media, 'all');
  assert.equal(ctx.styles.requestedHref, '/static/css/app.css');
  assert.equal(ctx.boots(), 1);
  assert.equal(ctx.head.length, 1);
  assert.equal(ctx.timers.size, 0);
});

test('failed asset restores visible fallback and never boots', async () => {
  const ctx = startupContext({ imported: Promise.reject(new Error('asset failed')) });
  await flush();
  assert.equal(ctx.message.role, 'alert');
  assert.equal(ctx.message.textContent, 'asset failed');
  assert.equal(ctx.app.child, ctx.fallback);
  assert.equal(ctx.boots(), 0);
});

test('stylesheet failure does not render unstyled application', async () => {
  const ctx = startupContext({ autoLoad: false });
  await flush();
  assert.equal(ctx.styles.media, 'print');
  assert.equal(ctx.boots(), 0);
  ctx.callbacks.error();
  await flush();
  assert.equal(ctx.message.role, 'alert');
  assert.equal(ctx.boots(), 0);
});

test('resource timeout ignores late import and keeps fallback', async () => {
  let resolve;
  const imported = new Promise(r => { resolve = r; });
  const ctx = startupContext({ imported });
  [...ctx.timers.values()][0]();
  await flush();
  let lateBoots = 0;
  resolve({ boot: async () => lateBoots++ });
  await flush();
  assert.match(ctx.message.textContent, /超时/);
  assert.equal(lateBoots, 0);
  assert.equal(ctx.app.child, ctx.fallback);
});

test('boot route error restores fallback even after it was detached', async () => {
  const ctx = startupContext({ imported: Promise.resolve({ boot: async () => { throw new Error('route failed'); } }) });
  await flush();
  assert.equal(ctx.app.child, ctx.fallback);
  assert.equal(ctx.message.textContent, 'route failed');
});

test('reload uses location.reload to preserve a deep-link hash', async () => {
  const ctx = startupContext();
  let prevented = false;
  ctx.anchor.click({ preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(ctx.reloads(), 1);
  await flush();
});

test('obsolete initial route rejection still reconciles a newer hash', async () => {
  const { context, events } = bootContext();
  let routes = 0;
  context.location.hash = '#/board/1';
  context.route = async () => {
    if (++routes === 1) {
      context.location.hash = '#/projects';
      throw new Error('obsolete board failed');
    }
  };
  await context.boot();
  assert.equal(routes, 2);
  assert.equal(events.length, 1);
});
