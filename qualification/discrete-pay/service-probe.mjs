import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
const pay='/opt/discrete-pay-qualification/pay';
const {DiscretePayStore}=await import(pay+'/dist/src/persistence/store.js');
const [file,action]=process.argv.slice(2);
const h=JSON.parse(await readFile(file,'utf8'));
assert.equal(file,join(h.dir,'service-handoff.json'));
async function until(fn,ms=120000){const deadline=Date.now()+ms;while(Date.now()<deadline){try{if(await fn())return;}catch{}await delay(500);}throw new Error('qualification condition timed out: '+action);}
async function rpc(port,method,params={},wallet=true,path='/json_rpc'){
  const r=await fetch(`http://127.0.0.1:${port}${path}`,{method:'POST',headers:{'content-type':'application/json',...(wallet?{authorization:'Basic '+Buffer.from(h.rpcUser+':'+h.rpcPassword).toString('base64')}:{})},
    body:JSON.stringify(path==='/json_rpc'?{jsonrpc:'2.0',id:1,method,params}:params),signal:AbortSignal.timeout(10000)});
  assert.equal(r.status,200);const b=await r.json();assert(!b.error,'native fixture RPC rejected');return path==='/json_rpc'?b.result:b;
}
const publicStatus=async()=>{const r=await fetch(`http://127.0.0.1:${h.publicEnv.DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT}/v1/public/invoices/${h.publicToken}`);assert.equal(r.status,200);return(await r.json()).invoice;};
const store=new DiscretePayStore(h.gatewayEnv.DISCRETE_PAY_GATEWAY_DATABASE_PATH);
try {
  if(action==='baseline' || action==='restored') {
    await until(async()=>{const scheme=await rpc(h.trackingPort,'getDepositScheme');return scheme.tracking===true && scheme.depositCount===1000 && (await publicStatus()).status===(action==='restored'?'overpaid':'confirmed');});
    const before=store.getInvoiceById(h.invoiceId);
    assert.equal(before.confirmedAtomic,action==='restored'?12346n:12345n);
    const response=await fetch(`http://127.0.0.1:${h.gatewayEnv.DISCRETE_PAY_GATEWAY_LISTEN_PORT}/v1/invoices`,{method:'POST',headers:{authorization:'Bearer '+h.merchantToken,'content-type':'application/json','idempotency-key':'native-test-order'},body:JSON.stringify({amount_atomic:'12345',expires_in_seconds:3600,required_confirmations:2})});
    assert.equal(response.status,200);assert.equal((await response.json()).invoice.id,h.invoiceId);
    assert.equal((await rpc(h.trackingPort,'getDepositScheme')).depositCount,1000);
    assert.equal(store.getInvoiceById(h.invoiceId).depositAccount,before.depositAccount);
    if(action==='baseline')assert.deepEqual(store.listInvoiceEvents(h.invoiceId).map(e=>e.invoiceStatus),h.expectedEvents);
    if(action==='restored') {
      const snap=JSON.parse(await readFile(join(h.dir,'service-snapshot.json'),'utf8'));
      assert.deepEqual(store.listInvoiceEvents(h.invoiceId).map(e=>e.invoiceStatus),snap.events);
      assert.deepEqual(store.getCanonicalTip(),snap.tip);
    }
  } else if(action==='outage') {
    await delay(1500);
    assert.equal((await publicStatus()).status,'confirmed');
    assert.deepEqual(store.getCanonicalTip(),h.expectedTip);
    assert.deepEqual(store.listInvoiceEvents(h.invoiceId).map(e=>e.invoiceStatus),h.expectedEvents);
  } else if(action==='pay') {
    await until(async()=>{const b=await rpc(h.signerPort,'getBalance');return b.availableBalance>=2;});
    const row=store.getInvoiceById(h.invoiceId);
    // One explicitly disposable testnet transfer; never retry an ambiguous send.
    const sent=await rpc(h.signerPort,'sendTransaction',{transfers:[{address:row.depositAccount,amount:1}],fee:1,unlockHeight:0});
    await writeFile(join(h.dir,'service-payment.json'),JSON.stringify({transactionHash:sent.transactionHash}),{mode:0o600});
    const addr=(await rpc(h.signerPort,'getAddresses')).addresses[0];
    const spend=await rpc(h.signerPort,'getSpendKeys',{address:addr});
    const start=(await rpc(h.nodePort,'getlastblockheader',{},false)).block_header.height;
    await rpc(h.nodePort,'start_mining',{miner_spend_key:spend.spendSecretKey,miner_view_key:'',threads_count:1},false,'/start_mining');
    try {await until(async()=>(await rpc(h.nodePort,'getlastblockheader',{},false)).block_header.height>=start+3,30000);}
    finally {await rpc(h.nodePort,'stop_mining',{},false,'/stop_mining');}
    await until(async()=>(await publicStatus()).status==='overpaid');
    assert.equal(store.getInvoiceById(h.invoiceId).confirmedAtomic,12346n);
    await until(async()=>JSON.parse(await readFile(join(h.dir,'service-receipts.json'),'utf8')).some(r=>r.rejected&&r.status==='overpaid'));
  } else if(action==='retry') {
    await until(async()=>{const rows=JSON.parse(await readFile(join(h.dir,'service-receipts.json'),'utf8'));return rows.some(r=>!r.rejected&&r.status==='overpaid');});
    const rows=JSON.parse(await readFile(join(h.dir,'service-receipts.json'),'utf8'));
    const failed=rows.find(r=>r.rejected&&r.status==='overpaid');
    const success=rows.find(r=>!r.rejected&&r.id===failed.id);
    assert(success && success.valid && failed.valid);assert.equal(success.body,failed.body);assert.equal(success.digest,failed.digest);
    assert.equal(store.getInvoiceById(h.invoiceId).confirmedAtomic,12346n);
  } else if(action==='snapshot') {
    await store.backupTo(join(h.dir,'gateway-online-backup.sqlite3'));
    const backup=new DiscretePayStore(join(h.dir,'gateway-online-backup.sqlite3'));
    try {assert.deepEqual(backup.getInvoiceById(h.invoiceId),store.getInvoiceById(h.invoiceId));assert.deepEqual(backup.getCanonicalTip(),store.getCanonicalTip());}finally{backup.close();}
    await writeFile(join(h.dir,'service-snapshot.json'),JSON.stringify({tip:store.getCanonicalTip(),events:store.listInvoiceEvents(h.invoiceId).map(e=>e.invoiceStatus)}),{mode:0o600});
  } else throw new Error('unknown action');
  console.log('PASS: service probe '+action);
} finally {store.close();}
