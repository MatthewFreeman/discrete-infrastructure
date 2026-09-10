// Disposable PRIVATE installation only. No payment, mining, signing or public-network calls.
import assert from 'node:assert/strict';
import {readFile, writeFile, lstat} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {createServer} from 'node:https';
import {createHash, createHmac} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
const dir='/opt/discrete-pay/private';
const release='/opt/discrete-pay/releases/120f2b9478d4474d9cb27456aeb9b83d24febadaebdfb1ba887ba1e856f6f589';
const {DiscretePayStore}=await import(release+'/pay/dist/src/persistence/store.js');
const action=process.argv[2];
const read=async name=>JSON.parse(await readFile(dir+'/'+name,'utf8'));
const h=await read('qualification-private.json');
const saved=async(name,value)=>writeFile(dir+'/'+name,JSON.stringify(value),{mode:0o600,flag:'wx'});
const store=action==='receiver'?null:new DiscretePayStore(dir+'/gateway.sqlite3');
const base='http://127.0.0.1:17880';
async function until(fn){const end=Date.now()+90000;while(Date.now()<end){try{if(await fn())return;}catch{}await delay(250);}throw new Error('bounded gate timeout');}
async function request(method,path,token,body,key){
 const r=await fetch(base+path,{method,signal:AbortSignal.timeout(15000),headers:{...(token?{authorization:'Bearer '+token}:{}),
  ...(body?{'content-type':'application/json','idempotency-key':key}:{})},...(body?{body:JSON.stringify(body)}:{})});
 return {code:r.status,data:await r.json()};
}
function operator(file,webhook=false){
 return JSON.parse(execFileSync(release+'/bin/node',[release+'/pay/dist/apps/operator/src/'+(webhook?'webhook-main':'main')+'.js','--config',dir+'/'+file],
  {env:{...process.env,DISCRETE_PAY_OPERATOR_ENABLED:'true'},encoding:'utf8',timeout:30000,stdio:['ignore','pipe','pipe']}));
}
function original(){const row=store.getInvoiceById(h.invoiceId);return {amount:row.confirmedAtomic.toString(),status:row.status,
 events:store.listInvoiceEvents(h.invoiceId).map(e=>e.eventId),tip:store.getCanonicalTip()};}
try {
 if(action==='operator'){
  const before=original();assert.equal(before.amount,'12346');assert.equal(before.status,'overpaid');
  await saved('shop-request.json',{operation:'provision',databasePath:dir+'/gateway.sqlite3',merchantId:'standalone-shop',
   scopes:['invoices:create','invoices:read'],credentialPath:dir+'/shop-key.json',initializeDatabase:false});
  const first=operator('shop-request.json');assert.equal(first.replayed,false);
  const replay=operator('shop-request.json');assert.equal(replay.replayed,true);assert.equal(replay.keyId,first.keyId);
  await saved('hook-request.json',{databasePath:dir+'/gateway.sqlite3',merchantId:'standalone-shop',endpointId:'standalone-hook',
   url:'https://merchant.test:19443/webhook',secretKeyId:h.keyId,workerConfigPath:dir+'/worker.json',credentialPath:dir+'/shop-hook.json'});
  const hook=operator('hook-request.json',true);assert.equal(hook.replayed,false);
  assert.equal(operator('hook-request.json',true).replayed,true);
  for(const name of ['shop-key.json','shop-hook.json'])assert.equal((await lstat(dir+'/'+name)).mode&0o777,0o600);
  await saved('operator-proof.json',{before,keyId:first.keyId});
  console.log('PASS: actual merchant and webhook CLIs provision/replay; private credential files');
 }else if(action==='receiver'){
  const {secretHex}=await read('shop-hook.json');const rows=[];
  const server=createServer({cert:h.certificate,key:h.certificateKey},async(req,res)=>{
   try{
    assert.equal(req.method,'POST');assert.equal(req.url,'/webhook');
    let size=0;const chunks=[];for await(const part of req){size+=part.length;assert(size<=65536);chunks.push(part);}
    const body=Buffer.concat(chunks);const headers=req.headers;
    const id=headers['x-discrete-pay-delivery-id'],event=headers['x-discrete-pay-event-id'];
    const digest=createHash('sha256').update(body).digest('hex');
    const signature=createHmac('sha256',Buffer.from(secretHex,'hex')).update(`v1\n${headers['x-discrete-pay-timestamp-ms']}\n${id}\n${event}\n${digest}\n`).update(body).digest('hex');
    assert.equal(headers['x-discrete-pay-signature'],'v1='+signature);assert.equal(headers['x-discrete-pay-idempotency-key'],id);
    const value=JSON.parse(body);let rejected=true;
    try{await readFile(dir+'/allow-delivery');rejected=false;}catch{}
    rows.push({id,event,digest,body:body.toString('base64'),valid:true,rejected,status:value.status});
    await writeFile(dir+'/standalone-receipts.json',JSON.stringify(rows),{mode:0o600});res.writeHead(rejected?503:204).end();
   }catch{res.writeHead(400).end();}
  });
  server.listen(19443,'127.0.0.1');process.once('SIGTERM',()=>server.close());
  await new Promise(resolve=>server.once('close',resolve));
 }else if(action==='invoice'){
  const token=(await read('shop-key.json')).token;const body={amount_atomic:'17',expires_in_seconds:2,required_confirmations:2};
  const key='standalone-operator-acceptance';
  const created=await request('POST','/v1/invoices',token,body,key);assert.equal(created.code,201);
  const id=created.data.invoice.id;const row=store.getInvoiceById(id);assert.equal(row.depositT,1002);
  const replay=await request('POST','/v1/invoices',token,body,key);assert.equal(replay.code,200);assert.equal(replay.data.invoice.id,id);
  assert.equal((await request('POST','/v1/invoices',token,{...body,amount_atomic:'18'},key)).code,409);
  assert.equal((await request('GET','/v1/invoices/'+id)).code,401);
  // The prior merchant remains valid but cannot access this merchant's invoice.
  assert.equal((await request('GET','/v1/invoices/'+id,h.merchantToken)).code,404);
  const url='http://127.0.0.1:17882/pay/'+row.publicToken;
  const page=await fetch(url);assert.equal(page.status,200);
  assert((await page.text()).includes('discrete:'+row.depositAccount));
  await saved('invoice-proof.json',{id,key,body,publicToken:row.publicToken,depositT:row.depositT,account:row.depositAccount});
  await until(async()=>{const rows=await read('standalone-receipts.json');return rows.some(r=>r.rejected);});
  console.log('PASS: native T1002 allocation, replay200/conflict409/auth401/ownership404; first signed delivery503');
 }else if(action==='retained'){
  const proof=await read('invoice-proof.json');const token=(await read('shop-key.json')).token;
  await until(()=>store.getInvoiceById(proof.id).status==='expired');
  await until(async()=>{const rows=await read('standalone-receipts.json');return rows.some(r=>!r.rejected&&r.id===rows[0].id);});
  const rows=await read('standalone-receipts.json');const failed=rows.find(r=>r.rejected);const good=rows.find(r=>!r.rejected&&r.id===failed.id);
  assert(failed.valid&&good.valid);assert.equal(failed.body,good.body);assert.equal(failed.digest,good.digest);
  const r=await request('POST','/v1/invoices',token,proof.body,proof.key);assert.equal(r.code,200);assert.equal(r.data.invoice.id,proof.id);
  assert.equal(store.getInvoiceById(proof.id).depositAccount,proof.account);
  assert.deepEqual(original(),(await read('operator-proof.json')).before);
  console.log('PASS: signed identical retry delivered, expiry and invoice identity retained; original paid invoice unchanged');
 }else if(action==='revoke'){
  const {keyId}=await read('operator-proof.json');await saved('revoke-request.json',{operation:'revoke',databasePath:dir+'/gateway.sqlite3',keyId});
  operator('revoke-request.json');operator('revoke-request.json');
  const token=(await read('shop-key.json')).token;const proof=await read('invoice-proof.json');
  assert.equal((await request('GET','/v1/invoices/'+proof.id,token)).code,401);
  assert.throws(()=>operator('shop-request.json'));
  console.log('PASS: live API rejects revoked key; retained intent cannot reactivate it');
 }else throw new Error('unknown action');
}catch(error){console.error('FAILED: standalone gate '+action+' ('+error.name+')');process.exitCode=1;}
finally{store?.close();}
