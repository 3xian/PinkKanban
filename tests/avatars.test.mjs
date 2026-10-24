import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, statSync } from 'node:fs';
import { AVATAR_GROUPS, AVATARS, avatarId, avatarPath } from '../static/js/avatars.js';

test('all four avatar categories have six distinct shipped assets', () => {
  assert.equal(AVATAR_GROUPS.length, 4);
  assert.equal(AVATARS.length, 24);
  assert.equal(new Set(AVATARS.map((item) => item.id)).size, 24);
  for (const group of AVATAR_GROUPS) assert.equal(AVATARS.filter((item) => item.group === group.id).length, 6);
  for (const item of AVATARS) assert.ok(existsSync(new URL(`../static/avatars/${item.id}.webp`, import.meta.url)), item.id);
});

test('saved avatar takes precedence and legacy defaults are stable across users', () => {
  assert.equal(avatarId({ id: 1, avatar_id: 'robot-6' }), 'robot-6');
  assert.equal(avatarId({ id: 1 }), 'male-1');
  assert.equal(avatarId({ id: 24 }), 'robot-6');
  assert.equal(avatarId({ id: 25 }), 'male-1');
  assert.equal(avatarId(null), 'male-1');
});

test('avatar files stay within the delivery size budget', () => {
  let total = 0;
  for (const item of AVATARS) {
    const bytes = statSync(new URL(`../static/avatars/${item.id}.webp`, import.meta.url)).size;
    assert.ok(bytes <= 16 * 1024, `${item.id} exceeds 16 KiB`);
    total += bytes;
  }
  assert.ok(total <= 256 * 1024, 'avatar set exceeds 256 KiB');
});

test('avatar URLs accept only presets and fall back safely', () => {
  for (const invalid of ['../secret', 'https://example.com/a.png', 'pet-7', null]) {
    assert.equal(avatarPath(invalid), '/static/avatars/male-1.webp?v=1');
    assert.equal(avatarId({ id: 2, avatar_id: invalid }), 'male-2');
  }
});
