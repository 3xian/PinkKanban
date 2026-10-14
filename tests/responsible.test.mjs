import test from 'node:test';
import assert from 'node:assert/strict';
import { cardFaces, faceNode, participantMembers, responsibleField } from '../static/js/format.js';

class Node {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.className = '';
    this.textContent = '';
    this.children = [];
    this.attributes = {};
    this.style = { setProperty: (key, value) => { this.style[key] = value; } };
  }

  setAttribute(key, value) {
    this.attributes[key] = String(value);
  }

  append(...nodes) {
    for (const node of nodes) this.children.push(node);
  }

  get title() {
    return this.attributes.title || '';
  }

  set title(value) {
    this.attributes.title = value;
  }
}

globalThis.document = { createElement: (tag) => new Node(tag) };

const members = [
  { id: 1, display_name: '甲', avatar_color: '#D63A56' },
  { id: 2, display_name: '乙', avatar_color: '#3D6B8A' },
  { id: 3, display_name: '丙', avatar_color: '#5C6B52' },
  { id: 4, display_name: '丁', avatar_color: '#C47B2B' },
];

test('board faces keep the old assignee row when nobody is responsible', () => {
  const faces = cardFaces({ assignee_ids: [4, 1, 2, 3], responsible_user_id: null }, members);
  assert.deepEqual(faces.map((face) => [face.person.id, face.lead]), [[1, false], [2, false], [3, false]]);
});

test('board shows the responsible avatar once and marks only that person', () => {
  const faces = cardFaces({ assignee_ids: [2, 1, 3], responsible_user_id: 2 }, members);
  assert.deepEqual(faces.map((face) => face.person.id), [2, 1, 3]);
  assert.deepEqual(faces.map((face) => face.lead), [true, false, false]);
  assert.equal(new Set(faces.map((face) => face.person.id)).size, faces.length);
  const lead = faceNode(faces[0]);
  const other = faceNode(faces[1]);
  assert.equal(lead.className, 'avatar is-lead');
  assert.equal(lead.title, '主负责人 乙');
  assert.equal(lead.textContent, '乙');
  assert.equal(other.className, 'avatar');
  assert.equal(other.title, '甲');
});

test('drawer field shows unset or the selected member and hides that member from participants', () => {
  const empty = responsibleField({ responsible_user_id: null }, members, true);
  const emptySelect = empty.children.find((node) => node.tagName === 'SELECT');
  assert.equal(empty.children.some((node) => node.className.includes('avatar')), false);
  assert.equal(emptySelect.attributes['aria-label'], '主负责人');
  assert.equal(emptySelect.attributes.disabled, undefined);
  assert.equal(emptySelect.children[0].textContent, '未指定');
  assert.equal(emptySelect.children[0].attributes.selected, 'true');
  assert.deepEqual(participantMembers({ responsible_user_id: null }, members).map((person) => person.id), [1, 2, 3, 4]);

  const chosen = responsibleField({ responsible_user_id: 2, assignee_ids: [2, 1] }, members, false);
  const avatar = chosen.children.find((node) => node.className.includes('avatar'));
  const select = chosen.children.find((node) => node.tagName === 'SELECT');
  assert.equal(avatar.textContent, '乙');
  assert.equal(select.attributes.disabled, 'true');
  assert.equal(select.children.find((option) => option.attributes.value === '2').attributes.selected, 'true');
  assert.equal(select.children[0].attributes.selected, undefined);
  assert.deepEqual(participantMembers({ responsible_user_id: 2 }, members).map((person) => person.id), [1, 3, 4]);
});
