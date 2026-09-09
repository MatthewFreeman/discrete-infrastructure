import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
const root='/opt/discrete-pay-qualification',pay=root+'/pay-merged-4d2f069';
const h=JSON.parse(await readFile(root+'/gui-v0.9.8/session-private.json','utf8'));
assert.equal(h.dir,pay+'/build/gui-qualification/run-8Gqvfk');
const config=JSON.parse(await readFile(h.dir+'/state/gui-worker.json','utf8'));
assert.deepEqual(config.webhookDestinations,[{url:'https://merchant.test:46411/webhook',address:'127.0.0.1'}]);
assert.equal(h.controlPort,18911);
const invoke=async(action)=>{const r=await fetch('http://127.0.0.1:'+h.controlPort+'/'+action,{method:'POST',headers:{authorization:'Bearer '+h.token,'content-type':'application/json'},body:'{}',signal:AbortSignal.timeout(120000)});const b=await r.json();assert.equal(r.status,200);return b;};
const result={guiTransactionHash:'6d83898b5efdfe3208104ac13e028faa03ceddf412a023ae6ab0eacbecff2131',invoiceId:'inv_95608cfeff3b4e61913b0dc769e6fe48',amountAtomic:'10',routingT:10002,checks:[]};
let delivered=0,idle=false;const started=Date.now();
for(let n=0;n<240;n++){const batch=await invoke('scan');assert(batch.delivered.every(k=>k==='delivered'||k==='idle'));delivered+=batch.delivered.filter(k=>k==='delivered').length;if(n%20===0)console.log('Outbox progress',JSON.stringify({batches:n+1,delivered,elapsedMs:Date.now()-started}));if(batch.delivered.includes('idle')){idle=true;break;}}
assert(idle,'bounded historical outbox drain');
const status=await invoke('status');assert.equal(status.invoice.id,result.invoiceId);assert.equal(status.invoice.status,'confirmed');assert.equal(status.invoice.confirmedAtomic,'10');
assert(status.receipts.some(r=>r.valid&&r.payload.invoice_id===result.invoiceId&&r.payload.confirmed_atomic==='10'));
result.checks.push({check:'GUI payment projected confirmed and signed HTTPS delivered',invoiceStatus:status.invoice.status,confirmedAtomic:status.invoice.confirmedAtomic,targetReceiptCount:status.receipts.length,drainedDeliveries:delivered,elapsedMs:Date.now()-started});
const publicResponse=await fetch('http://127.0.0.1:18910/v1/public/invoices/'+status.invoice.publicToken);assert.equal(publicResponse.status,200);const publicInvoice=(await publicResponse.json()).invoice;assert.equal(publicInvoice.status,'confirmed');result.checks.push({check:'public HTTP confirmed',status:publicInvoice.status});
for(let i=0;i<3;i++){const again=await invoke('scan');assert.equal(again.scan.eventsCreated,0);assert.deepEqual(again.delivered,['idle']);}
assert.equal((await invoke('status')).receipts.length,status.receipts.length);
result.checks.push({check:'three repeat native scans create no new events or deliveries'});
result.result='PASS';await writeFile(h.dir+'/gui-payment-verification.json',JSON.stringify(result,null,2),{mode:0o600});console.log(JSON.stringify(result));
