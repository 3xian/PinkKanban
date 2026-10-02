import test from 'node:test';
import assert from 'node:assert/strict';
import { allowsPullRefresh, canPullRefreshAt } from '../static/js/refresh.js';

globalThis.getComputedStyle = (node) => ({ overflowY: node.overflowY ?? 'visible' });

function element(selector = '', parentElement = null, properties = {}) {
  return {
    parentElement, scrollHeight: 100, clientHeight: 100,
    matches: (selectors) => selectors.split(',').map((s) => s.trim()).includes(selector),
    ...properties,
  };
}

test('card, drag handle, drop column and interactive ancestors block refresh', () => {
  for (const selector of ['[data-drag]', '[data-drop-column]', '[draggable=true]',
    'button', 'a', 'input', 'textarea', 'select', 'label']) {
    assert.equal(allowsPullRefresh(element('', element(selector)), null), false, selector);
  }
  assert.equal(allowsPullRefresh(element('', element('', null, { isContentEditable: true })), null), false);
  assert.equal(allowsPullRefresh(null, null), false);
});

test('nested vertical scrollers block refresh but the root scroller allows it', () => {
  for (const overflowY of ['auto', 'scroll']) {
    const scroller = element('', null, { scrollHeight: 300, overflowY });
    assert.equal(allowsPullRefresh(element('', scroller), null), false);
    assert.equal(allowsPullRefresh(element('', scroller), scroller), true);
  }
  assert.equal(allowsPullRefresh(element('', null, { overflowY: 'auto' }), null), true);
  assert.equal(allowsPullRefresh(element('', null, { scrollHeight: 300 }), null), true);
});

test('native coordinates resolve the visible viewport and default viewport', () => {
  const hits = [];
  globalThis.document = {
    scrollingElement: null,
    elementFromPoint: (x, y) => { hits.push([x, y]); return element(); },
  };
  globalThis.window = { innerWidth: 400, innerHeight: 800 };
  assert.equal(canPullRefreshAt(0.5, 0.25), true);
  window.visualViewport = { width: 200, height: 400, offsetLeft: 20, offsetTop: 60 };
  assert.equal(canPullRefreshAt(0.5, 0.25), true);
  assert.deepEqual(hits, [[200, 200], [120, 160]]);
  delete globalThis.document;
  delete globalThis.window;
});
