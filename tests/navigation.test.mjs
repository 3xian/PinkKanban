import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/js/app.js', import.meta.url), 'utf8');
const navigation = source.slice(source.indexOf('function handleBack()'), source.indexOf('\nasync function saveCard'));

test('Escape and native back share overlay priority and report whether handled', () => {
  let filterOpen = true;
  let listener;
  const actions = [];
  const state = { modal: {}, cardId: 1, sidebar: true };
  const window = {};
  vm.runInNewContext(navigation, {
    state, window,
    document: {
      querySelector: () => filterOpen,
      addEventListener: (_, callback) => { listener = callback; },
    },
    closeFilterPops() { filterOpen = false; actions.push('filter'); },
    paintModal() { actions.push('modal'); },
    closeDrawer() { state.cardId = null; actions.push('card'); },
    render() { actions.push('sidebar'); },
  });
  assert.equal(window.kanbanNavigation.handleBack(), true);
  listener({ key: 'Escape' });
  assert.equal(window.kanbanNavigation.handleBack(), true);
  listener({ key: 'Escape' });
  assert.equal(window.kanbanNavigation.handleBack(), false);
  assert.deepEqual(actions, ['filter', 'modal', 'card', 'sidebar']);
  listener({ key: 'Enter' });
  assert.equal(actions.length, 4);
});
