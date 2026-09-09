// Private-chain service acceptance only. No spending or mining RPCs.
import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
const [file, release, action] = process.argv.slice(2);
assert(/^\/opt\/discrete-pay-qualification\/pay-merged-4d2f069\/build\/native-ops\/run-persistent-[a-z0-9_]+\/service-handoff.json$/.test(file));
assert(/^\/opt\/discrete-pay-test\/releases\/[a-f0-9]{64}$/.test(release));
const h = JSON.parse(await readFile(file, 'utf8'));
assert.equal(file, join(h.dir, 'service-handoff.json'));
const {DiscretePayStore} = await import(release + '/dist/src/persistence/store.js');
const store = new DiscretePayStore(h.gatewayEnv.DISCRETE_PAY_GATEWAY_DATABASE_PATH);
const path = join(h.dir, 'persistent-probe-state.json');
const gateway = `http://127.0.0.1:${h.gatewayEnv.DISCRETE_PAY_GATEWAY_LISTEN_PORT}`;
async function request(method, url, body, key, auth = true) {
  const r = await fetch(url, {method, signal: AbortSignal.timeout(20000),
    headers: {...(auth ? {authorization: 'Bearer ' + h.merchantToken} : {}),
      ...(body ? {'content-type': 'application/json', 'idempotency-key': key} : {})},
    ...(body ? {body: JSON.stringify(body)} : {})});
  return {code: r.status, data: await r.json()};
}
function baseline() {
  const row = store.getInvoiceById(h.invoiceId);
  return {status: row.status, confirmed: row.confirmedAtomic.toString(),
    events: store.listInvoiceEvents(h.invoiceId).map(e => e.invoiceStatus), tip: store.getCanonicalTip()};
}
async function publicOriginal() {
  const r = await request('GET', `http://127.0.0.1:${h.publicEnv.DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT}/v1/public/invoices/${h.publicToken}`, undefined, undefined, false);
  assert.equal(r.code, 200);
  assert.equal(r.data.invoice.status, 'overpaid');
}
try {
  if (action === 'create') {
    const before = baseline();
    assert.equal(before.confirmed, '12346');
    let intent;
    try { intent = JSON.parse(await readFile(path, 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    assert(!intent || intent.phase === 'prepared', 'completed probe must not create another invoice');
    const key = intent?.key ?? ('persistent-test-' + randomUUID());
    const body = intent?.body ?? {amount_atomic: '17', expires_in_seconds: 3600, required_confirmations: 2};
    if (!intent) await writeFile(path, JSON.stringify({phase: 'prepared', key, body, before}), {mode: 0o600, flag: 'wx'});
    const created = await request('POST', gateway + '/v1/invoices', body, key);
    assert([201, ...(intent ? [200] : [])].includes(created.code));
    const id = created.data.invoice.id;
    const row = store.getInvoiceById(id);
    assert.equal(row.amountAtomic, 17n);
    assert.equal(row.depositT, 1002);
    assert.match(row.depositAccount, /^\d+-\d+-[A-Z0-9]+-1002-[A-Z0-9]+$/);
    const replay = await request('POST', gateway + '/v1/invoices', body, key);
    assert.equal(replay.code, 200); assert.equal(replay.data.invoice.id, id);
    assert.equal((await request('POST', gateway + '/v1/invoices', {...body, amount_atomic: '18'}, key)).code, 409);
    assert.equal((await request('GET', gateway + '/v1/invoices/' + id, undefined, undefined, false)).code, 401);
    await publicOriginal();
    assert.deepEqual(baseline(), before);
    await writeFile(path, JSON.stringify({phase: 'created', key, body, id, before}), {mode: 0o600});
    console.log('PASS: native T1002 invoice created; identical retry200, conflicting retry409, unauthenticated401; original payment unchanged');
  } else if (action === 'retained' || action === 'replay') {
    const saved = JSON.parse(await readFile(path, 'utf8'));
    await publicOriginal();
    assert.deepEqual(baseline(), saved.before);
    assert.equal(store.getInvoiceById(saved.id).depositT, 1002);
    if (action === 'replay') {
      const replay = await request('POST', gateway + '/v1/invoices', saved.body, saved.key);
      assert.equal(replay.code, 200); assert.equal(replay.data.invoice.id, saved.id);
    }
    console.log('PASS: original amount/events/checkpoint and new invoice retained' + (action === 'replay' ? '; HTTP replay same invoice' : ' during tracking outage'));
  } else throw new Error('unknown private probe action');
} finally { store.close(); }
