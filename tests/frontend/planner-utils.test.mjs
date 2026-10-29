import test from 'node:test';
import assert from 'node:assert/strict';
import {
  calculateBudget, readSavedPlans, toggleTask, updateVendor, upsertPlan, validateEventForm,
} from '../../src/planner-utils.js';

test('event form validation rejects missing dates, invalid guests and nonpositive budgets', () => {
  assert.match(validateEventForm({ date: '', guests: 10, budget: 1000 }), /date/);
  assert.match(validateEventForm({ date: '2027-01-01', guests: '1.5', budget: 1000 }), /whole number/);
  assert.match(validateEventForm({ date: '2027-01-01', guests: 50001, budget: 1000 }), /50,000/);
  assert.match(validateEventForm({ date: '2027-01-01', guests: 1, budget: 0 }), /greater than zero/);
  assert.equal(validateEventForm({ date: '2027-01-01', guests: '24', budget: '25000' }), null);
});

test('budget totals and remaining amount reflect every category', () => {
  assert.deepEqual(calculateBudget({ Venue: 5000, Food: 8000, Gifts: 500 }, 20000), {
    spent: 13500, remaining: 6500,
  });
  assert.deepEqual(calculateBudget({ Venue: 12000, Food: 10000 }, 20000), {
    spent: 22000, remaining: -2000,
  });
});

test('checklist toggle changes only the selected task and can be reversed', () => {
  const tasks = [{ title: 'Book venue', done: false }, { title: 'Send invites', done: false }];
  const checked = toggleTask(tasks, 1);
  assert.deepEqual(checked, [{ title: 'Book venue', done: false }, { title: 'Send invites', done: true }]);
  assert.deepEqual(toggleTask(checked, 1), tasks);
  assert.equal(tasks[1].done, false, 'updates are immutable');
});

test('vendor edits target the selected category without changing other vendors', () => {
  const vendors = [{ category: 'Venue', name: '', price: 0 }, { category: 'Food', name: '', price: 0 }];
  assert.deepEqual(updateVendor(vendors, 'Food', { name: 'Community kitchen', price: 6500 }), [
    vendors[0], { category: 'Food', name: 'Community kitchen', price: 6500 },
  ]);
});

test('saved plan storage upserts by id and tolerates empty or malformed local data', () => {
  const existing = [{ id: 'old', name: 'Old' }, { id: 'keep', name: 'Keep' }];
  assert.deepEqual(upsertPlan(existing, { id: 'old', name: 'Edited' }), [
    { id: 'old', name: 'Edited' }, { id: 'keep', name: 'Keep' },
  ]);
  assert.deepEqual(upsertPlan(existing, { id: 'new', name: 'New' }), [
    { id: 'new', name: 'New' }, ...existing,
  ]);
  assert.deepEqual(readSavedPlans({ getItem: () => null }), []);
  assert.deepEqual(readSavedPlans({ getItem: () => 'not json' }), []);
  assert.deepEqual(readSavedPlans({ getItem: () => '[{"id":"saved"}]' }), [{ id: 'saved' }]);
});
