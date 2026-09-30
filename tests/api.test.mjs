import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

// Import the browser module without changing this Python project's package type.
const source = await readFile(new URL('../static/js/api.js', import.meta.url), 'utf8');
const { api } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const never = () => new Promise(() => {});

function mockFetch(t, implementation) {
  t.mock.method(globalThis, 'fetch', implementation);
}

test('preserves options, JSON encoding, custom headers and successful response', async (t) => {
  mockFetch(t, async (path, options) => {
    assert.equal(path, '/api/test');
    assert.equal(options.credentials, 'include');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.method, 'POST');
    assert.equal(options.body, '{"title":"hello"}');
    assert.equal(options.headers.get('X-Custom'), 'yes');
    assert.equal(options.headers.get('X-Kanban'), '1');
    assert.equal(options.headers.get('Content-Type'), 'application/json');
    assert.equal(options.timeoutMs, undefined);
    return Response.json({ ok: true });
  });
  assert.deepEqual(await api('/api/test', {
    method: 'POST', body: { title: 'hello' }, headers: new Headers({ 'X-Custom': 'yes' }),
    credentials: 'include', cache: 'no-store', timeoutMs: 100,
  }), { ok: true });
});

test('preserves FormData bodies without forcing JSON headers', async (t) => {
  const body = new FormData();
  body.set('file', 'contents');
  mockFetch(t, async (_, options) => {
    assert.equal(options.body, body);
    assert.equal(options.headers.has('Content-Type'), false);
    return Response.json({});
  });
  await api('/upload', { method: 'POST', body });
});

test('preserves HTTP status and server detail', async (t) => {
  mockFetch(t, async () => Response.json({ detail: '登录已过期' }, { status: 401 }));
  await assert.rejects(api('/api/test'), { status: 401, message: '登录已过期' });
});

test('retains fallback for empty or invalid JSON responses', async (t) => {
  mockFetch(t, async () => new Response(null, { status: 204 }));
  assert.deepEqual(await api('/api/test'), {});
  globalThis.fetch = async () => new Response('bad gateway', { status: 502 });
  await assert.rejects(api('/api/test'), { status: 502, message: '请求失败' });
});

test('bounds a stalled fetch and aborts its signal', async (t) => {
  let requestSignal;
  mockFetch(t, (_, options) => { requestSignal = options.signal; return never(); });
  await assert.rejects(api('/api/test', { timeoutMs: 10 }), { name: 'TimeoutError' });
  assert.equal(requestSignal.aborted, true);
});

test('timeout includes response body consumption', async (t) => {
  mockFetch(t, async () => ({ ok: true, json: never }));
  await assert.rejects(api('/api/test', { timeoutMs: 10 }), { name: 'TimeoutError' });
});

test('mutation timeout warns about uncertain outcome and does not retry', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', never);
  await assert.rejects(api('/api/test', { method: 'POST', timeoutMs: 10 }),
    (error) => error.name === 'TimeoutError' && /可能已保存.*刷新/.test(error.message));
  assert.equal(fetch.mock.callCount(), 1);
});

test('uses 15-second read and 30-second mutation defaults and clears timers', async (t) => {
  const delays = [];
  const cleared = [];
  t.mock.method(globalThis, 'setTimeout', (_, delay) => { delays.push(delay); return delays.length; });
  t.mock.method(globalThis, 'clearTimeout', (id) => cleared.push(id));
  mockFetch(t, async () => Response.json({}));
  await api('/api/test');
  await api('/api/test', { method: 'PATCH' });
  assert.deepEqual(delays, [15000, 30000]);
  assert.deepEqual(cleared, [1, 2]);
});

test('honors caller cancellation and removes its listener', async (t) => {
  const controller = new AbortController();
  const remove = t.mock.method(controller.signal, 'removeEventListener');
  mockFetch(t, never);
  const request = api('/api/test', { signal: controller.signal });
  const reason = new Error('cancelled by caller');
  controller.abort(reason);
  await assert.rejects(request, (error) => error === reason);
  assert.equal(remove.mock.callCount(), 1);
});

test('does not fetch when caller signal is already aborted', async (t) => {
  const controller = new AbortController();
  controller.abort();
  const fetch = t.mock.method(globalThis, 'fetch', never);
  await assert.rejects(api('/api/test', { signal: controller.signal }), { name: 'AbortError' });
  assert.equal(fetch.mock.callCount(), 0);
});

test('gives friendly network errors, including mutation uncertainty', async (t) => {
  const cause = new TypeError('Failed to fetch');
  mockFetch(t, async () => { throw cause; });
  await assert.rejects(api('/api/test'), (error) => /网络连接失败/.test(error.message) && error.cause === cause);
  await assert.rejects(api('/api/test', { method: 'DELETE' }), /可能已保存.*刷新/);
});

test('does not mistake response-body transport errors for success', async (t) => {
  mockFetch(t, async () => ({ ok: true, json: async () => { throw new TypeError('connection reset'); } }));
  await assert.rejects(api('/api/test'), /网络连接失败/);
});

test('rejects invalid timeout overrides', async () => {
  for (const timeoutMs of [0, -1, Infinity, NaN]) {
    await assert.rejects(api('/api/test', { timeoutMs }), RangeError);
  }
});
