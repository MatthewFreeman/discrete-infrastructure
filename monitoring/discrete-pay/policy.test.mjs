import test from 'node:test';
import assert from 'node:assert/strict';
import {cycle, fromJournal, issues, observe, tick, validateState} from './policy.mjs';

const now = 1_000_000;
const sample = (component, ok = true, code = 'success', at = now) => ({component, ok, code, at});
const snapshot = () => ({version: 1, at: now, active: true,
  samples: {scanner: sample('scanner'), webhook: sample('webhook')}});

test('malformed persistence fails closed, valid queued state survives restart', () => {
  for (const bad of [null, [], {secret: 'value'}, {count: '3'}, {failures: 99},
    {nextAttemptAt: now + 999_999}, {queue: {}}, {queue: [{id: 'fake', at: now, issues: []}]},
    {candidate: 'unknown'}, {initialized: 'yes'}]) assert.throws(() => validateState(bad, now));
  const state = {};
  for (let i = 0; i < 3; i++) observe(state, ['scanner_stale'], now + i);
  assert.deepEqual(validateState(JSON.parse(JSON.stringify(state)), now + 3), state);
});

test('redacts journal entries and excludes prior worker invocations', () => {
  const entry = (invocation, component, timestamp_ms) => JSON.stringify({_SYSTEMD_INVOCATION_ID: invocation,
    MESSAGE: JSON.stringify({event: 'worker_cycle', component, ok: true, code: 'success', timestamp_ms, secret: 'never-export'})});
  const result = fromJournal([entry('previous', 'scanner', now), entry('current', 'scanner', now - 100),
    entry('current', 'scanner', now), entry('current', 'webhook', now + 60_000), 'invalid'].join('\n'), 'current', now);
  assert.deepEqual(result, {scanner: sample('scanner'), webhook: null});
  assert(!JSON.stringify(result).includes('secret'));
  assert.deepEqual(fromJournal(entry('current', 'scanner', now), '', now), {scanner: null, webhook: null});
});

test('invalid cycle records cannot claim success', () => {
  for (const patch of [{ok: true, code: 'rpc_unavailable'}, {ok: false, code: 'success'}, {component: 'wallet'},
    {timestamp_ms: -1}, {timestamp_ms: 1.5}, {code: 'unknown'}, {ok: 'true'}]) {
    assert.equal(cycle({event: 'worker_cycle', component: 'scanner', ok: true, code: 'success', timestamp_ms: now, ...patch}), null);
  }
});

test('good snapshot, inactive worker, missing signals, stalls and reported failures', () => {
  assert.deepEqual(issues(snapshot(), now), []);
  const inactive = snapshot(); inactive.active = false;
  assert.deepEqual(issues(inactive, now), ['worker_inactive']);
  const stale = snapshot(); stale.samples.scanner.at -= 180_001; stale.samples.webhook = null;
  assert.deepEqual(issues(stale, now), ['scanner_stale', 'webhook_stale']);
  const failed = snapshot(); failed.samples.scanner = sample('scanner', false, 'deep_reorg');
  assert.deepEqual(issues(failed, now), ['scanner_deep_reorg']);
});

test('stale, future and malformed snapshots fail closed', () => {
  for (const value of [null, {}, {...snapshot(), at: now - 30_001}, {...snapshot(), at: now + 5_001},
    {...snapshot(), active: 'yes'}, {...snapshot(), samples: {}}, {...snapshot(), version: 2}]) {
    assert.throws(() => issues(value, now));
  }
});

test('short failures are suppressed and initial good baseline does not send recovery', () => {
  const state = {};
  observe(state, [], now); observe(state, [], now + 1);
  assert.equal(state.queue, undefined);
  observe(state, ['snapshot_unavailable'], now + 2); observe(state, ['snapshot_unavailable'], now + 3);
  observe(state, [], now + 4); observe(state, [], now + 5);
  assert.equal(state.queue, undefined);
});

test('failure opens after three polls and recovery after two; preserves both while receiver is down', () => {
  const state = {};
  for (let i = 0; i < 3; i++) observe(state, ['scanner_stale'], now + i);
  assert.deepEqual(state.queue[0].issues, ['scanner_stale']);
  observe(state, [], now + 3);
  assert.equal(state.queue.length, 1);
  observe(state, [], now + 4);
  assert.deepEqual(state.queue.map(entry => entry.issues), [['scanner_stale'], []]);
});

test('bounded notification queue fails closed instead of silently losing incidents', () => {
  const state = {initialized: true, confirmed: '', queue: Array.from({length: 32}, () => ({}))};
  observe(state, ['worker_inactive'], now); observe(state, ['worker_inactive'], now + 1);
  assert.throws(() => observe(state, ['worker_inactive'], now + 2), /queue full/);
  assert.equal(state.confirmed, '');
});

test('retry, persistence, restart and recovery preserve notification order and ids', async () => {
  let clock = now; let stored; const sent = []; let unavailable = true; let reject = true;
  const ports = {now: () => clock, save: async state => { stored = structuredClone(state); },
    snapshot: async () => { if (unavailable) throw new Error('SSH down'); return {...snapshot(), at: clock}; },
    send: async entry => { assert(stored.queue.some(item => item.id === entry.id));
      if (reject) throw new Error('Telegram down'); sent.push(structuredClone(entry)); }};
  let state = {};
  for (let i = 0; i < 3; i++) { await tick(state, ports); clock += 10_000; }
  assert.equal(state.queue.length, 1); assert.equal(sent.length, 0);
  const id = state.queue[0].id;
  state = structuredClone(stored); // process restart
  unavailable = false;
  await tick(state, ports); clock += 10_000; await tick(state, ports);
  assert.equal(state.queue.length, 2);
  clock += 300_000; reject = false;
  // Fresh worker signals after recovery, not old records refreshed by exporter.
  ports.snapshot = async () => ({...snapshot(), at: clock,
    samples: {scanner: sample('scanner', true, 'success', clock), webhook: sample('webhook', true, 'success', clock)}});
  await tick(state, ports); clock += 10_000; await tick(state, ports);
  assert.equal(sent[0].id, id);
  assert.deepEqual(sent.map(entry => entry.issues), [['snapshot_unavailable'], []]);
  assert.equal(state.queue.length, 0);
});

test('local state failure prevents sending an unrecorded alert', async () => {
  const state = {candidate: 'snapshot_unavailable', count: 2}; let sent = false;
  await assert.rejects(tick(state, {now: () => now, snapshot: async () => { throw new Error(); },
    save: async () => { throw new Error('disk full'); }, send: async () => { sent = true; }}));
  assert.equal(sent, false);
});
