import test from 'node:test';
import assert from 'node:assert/strict';
import { createBoardSync } from '../static/js/board-sync.js';

function setup(t, load = async (id) => ({ id })) {
  const previous = { EventSource: globalThis.EventSource, document: globalThis.document };
  const streams = [], applied = [], calls = [], errors = [];
  globalThis.document = { hidden: false };
  globalThis.EventSource = class extends EventTarget {
    static CLOSED = 2;
    readyState = 1;
    constructor(url) { super(); this.url = url; streams.push(this); }
    emit(name) { this.dispatchEvent(new Event(name)); }
    close() { this.readyState = 2; }
  };
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] });
  let busy = false;
  const sync = createBoardSync({
    async load(id) { calls.push(id); return load(id); },
    apply: (board) => applied.push(board), isBusy: () => busy,
    onUnauthorized: () => errors.push(401), onUnavailable: () => errors.push(404),
  });
  t.after(() => { sync.stop(); Object.assign(globalThis, previous); });
  const tick = async (ms = 250) => {
    t.mock.timers.tick(ms);
    for (let i = 0; i < 10; i++) await Promise.resolve();
  };
  return { sync, streams, applied, calls, errors, tick, busy(value) { busy = value; } };
}

test('SSE coalesces bursts and a healthy stream never polls the board', async (t) => {
  const { sync, streams, applied, calls, tick } = setup(t);
  sync.start(1);
  for (let i = 0; i < 20; i++) streams[0].emit('change');
  await tick();
  await tick();
  assert.deepEqual(calls, [1]);
  assert.deepEqual(applied, [{ id: 1 }]);
  await tick(60000);
  assert.deepEqual(calls, [1]);
});

test('a snapshot arriving during an interaction waits until it ends', async (t) => {
  let resolve;
  const { sync, streams, applied, tick, busy } = setup(t, () => new Promise((done) => { resolve = done; }));
  sync.start(1);
  streams[0].emit('ready');
  await tick();
  busy(true);
  resolve({ title: 'Remote update' });
  await tick();
  await tick();
  assert.deepEqual(applied, []);
  busy(false);
  sync.resume();
  await tick();
  assert.deepEqual(applied, [{ title: 'Remote update' }]);
});

test('continuous remote changes apply completed snapshots while requesting a follow-up', async (t) => {
  let resolve;
  const { sync, streams, applied, calls, tick } = setup(t, () => new Promise((done) => { resolve = done; }));
  sync.start(1);
  streams[0].emit('ready');
  await tick();
  for (let revision = 1; revision <= 20; revision++) {
    streams[0].emit('change');
    resolve({ revision });
    await tick(0);
    await tick();
    assert.equal(applied.at(-1).revision, revision);
  }
  assert.equal(calls.length, 21);
});

test('frequent events do not keep pushing the scheduled refresh into the future', async (t) => {
  const { sync, streams, applied, calls, tick } = setup(t);
  sync.start(1);
  for (let i = 0; i < 100; i++) {
    streams[0].emit('change');
    await tick(10);
  }
  assert.ok(calls.length > 0);
  assert.ok(applied.length > 0);
});

test('local writes invalidate an older in-flight snapshot', async (t) => {
  const pending = [];
  const { sync, streams, applied, tick } = setup(t, () => new Promise((resolve) => pending.push(resolve)));
  sync.start(1);
  streams[0].emit('change');
  await tick();
  sync.invalidate();
  pending[0]({ title: 'Stale' });
  await tick();
  await tick();
  pending[1]({ title: 'Saved locally' });
  await tick();
  await tick();
  assert.deepEqual(applied, [{ title: 'Saved locally' }]);
});

test('navigation and backgrounding close streams and discard obsolete snapshots', async (t) => {
  const pending = [];
  const { sync, streams, applied, tick } = setup(t, () => new Promise((resolve) => pending.push(resolve)));
  sync.start(1);
  streams[0].emit('ready');
  await tick();
  sync.start(2);
  assert.equal(streams[0].readyState, 2);
  pending[0]({ id: 1 });
  await tick();
  assert.deepEqual(applied, []);
  document.hidden = true;
  sync.visibilityChanged();
  assert.equal(streams[1].readyState, 2);
  document.hidden = false;
  sync.visibilityChanged();
  assert.equal(streams[2].url, '/api/projects/2/events');
  streams[2].emit('ready');
  await tick();
  pending[1]({ id: 2 });
  await tick();
  await tick();
  assert.deepEqual(applied, [{ id: 2 }]);
});

test('disconnect falls back to slow polling and reconnect catches up once', async (t) => {
  const { sync, streams, calls, tick } = setup(t);
  sync.start(1);
  streams[0].emit('error');
  await tick();
  await tick();
  assert.equal(calls.length, 1);
  await tick(15000);
  await tick();
  assert.equal(calls.length, 2);
  // Repeated native reconnect errors must not turn fallback into rapid polling.
  streams[0].emit('error');
  await tick();
  assert.equal(calls.length, 2);
  streams[0].emit('ready');
  await tick();
  await tick();
  assert.equal(calls.length, 3);
  await tick(60000);
  assert.equal(calls.length, 3);
});

test('revoked access stops synchronization', async (t) => {
  const { sync, streams, calls, errors, tick } = setup(t, async () => { throw { status: 404 }; });
  sync.start(1);
  streams[0].emit('ready');
  await tick();
  await tick(60000);
  assert.deepEqual(errors, [404]);
  assert.equal(streams[0].readyState, 2);
  assert.deepEqual(calls, [1]);
});
