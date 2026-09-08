/* Persistence/settlement edges; no network, identity, or provider fixture. */
import assert from 'node:assert/strict';
import { createPaidReceipts } from '../../web/static/js/paid_receipts.js';
const key = 'paid-request-unconfirmed-v1';
for (const order of [false, true]) {
  const values = new Map();
  const store = {getItem:k => values.get(k) ?? null, setItem:(k,v) => values.set(k,v), removeItem:k => values.delete(k)};
  const journal = createPaidReceipts(() => store);
  const first = journal.begin(), second = journal.begin();
  assert.equal(journal.acknowledge(), false);
  first(order); first(true); // Double settlement cannot release the second.
  assert.equal(journal.state().active, 1);
  assert.equal(values.size, 1);
  second(!order);
  assert.equal(journal.state().uncertain, true, 'One success cannot erase a peer uncertainty');
  assert.throws(() => journal.begin(), {code:'paid_receipt_pending'});
  assert.equal(createPaidReceipts(() => store).state().uncertain, true);
  journal.acknowledge(); const third = journal.begin();
  first(true); second(true);
  assert.equal(journal.state().active, 1, 'Old callbacks cannot remove new intent');
  third(true); assert.equal(values.size, 0);
}
for (const raw of ['unconfirmed', '', '{}', 'null', 'invalid fixture']) {
  const j = createPaidReceipts(() => ({getItem:()=>raw, removeItem(){}}));
  assert.equal(j.state().uncertain, true, 'Malformed/nonempty presence is not a clean history');
}
for (const fault of ['getItem', 'setItem', 'removeItem']) {
  const values = new Map();
  const s = {getItem:k=>values.get(k)??null, setItem:(k,v)=>values.set(k,v), removeItem:k=>values.delete(k)};
  const j = createPaidReceipts(() => s);
  s[fault] = () => {throw Error('fixture denial')};
  const fresh = createPaidReceipts(() => s);
  const done = fresh.begin(); done(true);
  assert.equal(fresh.state().unavailable, true);
  assert.equal(fresh.state().active, 0);
  assert.equal(fresh.state().uncertain, false, 'A delivered result stays delivered when optional removal fails');
  if (fault === 'removeItem') assert.equal(createPaidReceipts(() => s).state().uncertain, true,
    'A stale marker may over-warn on reload; it must never claim verified absence');
  assert.equal(j.state().active, 0);
}
console.log('PASS paid receipt settlement and storage boundaries');
