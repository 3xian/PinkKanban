import test from 'node:test';
import assert from 'node:assert/strict';
import { groupActivity } from '../static/js/activity.js';

test('only adjacent operations by the same known user collapse; comments break groups', () => {
  const items = [
    [1, 'card.updated'], [1, 'card.moved'],
    [1, 'comment.added'], [1, 'comment.added'],
    [1, 'card.updated'], [2, 'card.updated'], [1, 'card.updated'],
    [null, 'card.updated'], [null, 'card.updated'],
  ].map(([id, action], index) => ({ id: index, action, user: id ? {id} : null }));
  const groups = groupActivity(items);
  assert.deepEqual(groups.map(group => group.length), [2, 1, 1, 1, 1, 1, 1, 1]);
  assert.deepEqual(groups.flat(), items);
  assert.deepEqual(groupActivity([]), []);
});
