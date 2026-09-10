// Combined native wallet and full journal fixture. Never a production tool.
// Missing invoice/journal rows are seeded via persistence APIs from validated
// native addresses, not claimed as end-to-end native merchant allocations.
import assert from 'node:assert/strict';
import {mkdtemp,cp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {createServer as httpsServer} from 'node:https';
import {createHash,createHmac,randomBytes} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {registryPrefixes} from './registry-prefix.mjs';
import {stopChild} from './bounded-child.mjs';
assert.equal(process.env.DISCRETE_PAY_COMBINED,'copied-private-chain-full-journal');
const root='/opt/discrete-pay-qualification',pay=root+'/pay-merged-4d2f069';
const candidate=process.env.DISCRETE_PAY_COMBINED_PAY;
assert([undefined,'94995a7c8d7215d1261b79abb83ae7fdda181c58'].includes(candidate));
const runtime=candidate?root+'/bundles/pay-94995a7-core-8703c16/pay':pay;
const large=process.env.DISCRETE_PAY_COMBINED_COUNT==='100000';
assert([undefined,'100000'].includes(process.env.DISCRETE_PAY_COMBINED_COUNT));
const count=large?100000:10000;
const source=large?process.env.DISCRETE_PAY_COMBINED_SOURCE:pay+'/build/native-load/run-mku6hq/state';
if(large)assert(new RegExp('^'+pay+'/build/native-load/run-[A-Za-z0-9_-]+/state$').test(source),'explicit native source required');
const original=root+'/pay-paged-tail/build/native-test/paged/run-NFdcs1';
const bin=root+'/pay-paged-tail/build/native-test/paged-bin/src/';
const sha=data=>createHash('sha256').update(data).digest('hex');
if(candidate){
 const manifestBytes=await readFile(runtime+'/../manifest.json');
 assert.equal(sha(manifestBytes),'120f2b9478d4474d9cb27456aeb9b83d24febadaebdfb1ba887ba1e856f6f589');
 const manifest=JSON.parse(manifestBytes);assert.equal(manifest.payCommit,candidate);
 for(const [file,digest] of Object.entries(manifest.files))if(file.startsWith('pay/'))assert.equal(sha(await readFile(runtime+'/../'+file)),digest);
}
for(const [name,hash]of [['walletd','630a033e0b41ebb01d666886948bd9a4affa4c44a299474bc125c3284afc15d1'],['discreted','fb9408fb76ab54eebd7016c8d997ad9ece39399b4851e8308e86e6fc3725cfb5']])assert.equal(sha(await readFile(bin+name)),hash);
const sourceProof=await readFile(source+'/../evidence.json');
assert.equal(sha(sourceProof),large?process.env.DISCRETE_PAY_COMBINED_SOURCE_SHA256:'337bbdac87d62a00085b48cfdd25da152a24868ae4f1707d6f59ec0224b642a0');
if(large){const proof=JSON.parse(sourceProof);assert.equal(proof.result,'PASS');assert.equal(proof.target,100000);assert.equal(proof.payCommit,'4d2f06952e2a566df4e92e9ee82b9f38601e0427');}
await mkdir(pay+'/build/native-combined',{recursive:true});
const dir=await mkdtemp(pay+'/build/native-combined/run-'),state=dir+'/state';
await cp(source,state,{recursive:true,force:false,errorOnExist:true});
const rewrite=text=>text.replaceAll(original,state).replaceAll(source,state);
const h=JSON.parse(rewrite(await readFile(state+'/service-handoff.json','utf8')));
const {DiscretePayStore}=await import(runtime+'/dist/src/persistence/store.js');
const {startPublicWebRuntime}=await import(runtime+'/dist/apps/public-web/src/runtime.js');
const {openWorkerRuntime}=await import(runtime+'/dist/apps/worker/src/runtime.js');
const {cert,key}=await import(pay+'/test/worker-runtime/tls-fixture.ts');
const {AllocationJournal}=await import(runtime+'/dist/services/walletd-facade/src/journal.js');
const {WalletdAllocationClient}=await import(runtime+'/dist/services/walletd-facade/src/walletd-client.js');
const {readPagedRegistry}=await import(runtime+'/dist/services/walletd-facade/src/paged-registry.js');
const {parseWalletAttestation,registryHash}=await import(runtime+'/dist/services/walletd-facade/src/contracts.js');
const {startFacadeRuntime}=await import(runtime+'/dist/services/walletd-facade/src/runtime.js');
const {startGatewayRuntime}=await import(runtime+'/dist/apps/gateway-api/src/runtime.js');
const result={payCommit:'4d2f06952e2a566df4e92e9ee82b9f38601e0427',walletdCommit:'8703c16fa40ffc8456e3d71696b6220b32b4d74a',scope:'native10000 addresses plus seeded10000 invoice/allocation rows; real payment and RPC/HTTP/HMAC; bounded combined cycles, not native100000 or production SLA',checks:[]};
if(large)result.scope='native100000 addresses plus seeded full invoice/allocation journal; native payment/HTTP/HMAC and10-minute mixed cycles; no production SLA';
if(candidate){result.payCommit=candidate;result.sourcePayCommit='4d2f06952e2a566df4e92e9ee82b9f38601e0427';}
const record=(check,value=true)=>{if(large)check=check.replace(/10000|10001/g,n=>String(Number(n)+90000));result.checks.push({check,value});console.log(check,JSON.stringify(value));};
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
async function until(label,fn,ms=90000){const end=Date.now()+ms;let last;while(Date.now()<end){try{const v=await fn();if(v)return v;}catch(e){last=e.name;}await delay(300);}throw new Error('fixture timeout: '+label+' '+(last??''));}
const children=new Set();let worker,web,receiver,store,facade,gateway,mining=false;
function launch(name,args){const c=spawn(bin+name,args,{cwd:state,stdio:'ignore'});children.add(c);c.once('exit',()=>children.delete(c));return c;}
async function stop(c){if(large)return stopChild(c,30000);if(c.exitCode!==null||c.signalCode!==null)return;const p=once(c,'exit');c.kill('SIGTERM');await p;}
const [na,nc,pa,pc,wp,sp,mp,pp,fp,gp]=await Promise.all(Array.from({length:10},port));
async function rpc(p,method,params={},auth=false,path='/json_rpc'){
 const r=await fetch('http://127.0.0.1:'+p+path,{method:'POST',headers:{'content-type':'application/json',...(auth?{authorization:'Basic '+Buffer.from(h.rpcUser+':'+h.rpcPassword).toString('base64')}:{})},body:JSON.stringify(path==='/json_rpc'?{jsonrpc:'2.0',id:1,method,params}:params),signal:AbortSignal.timeout(10000)});
 assert.equal(r.status,200,'native RPC HTTP '+method);const b=await r.json();assert(!b.error,'native RPC rejected '+method);return path==='/json_rpc'?b.result:b;
}
async function wallet(name,p){let conf=rewrite(await readFile(state+'/'+name+'.conf','utf8')).replace(/^bind-port=.*$/m,'bind-port='+p).replace(/^daemon-port=.*$/m,'daemon-port='+na);const file=state+'/high-'+name+'.conf';await writeFile(file,conf,{mode:0o600});return launch('walletd',['--config',file,'--testnet']);}
const height=async()=>(await rpc(na,'getlastblockheader')).block_header.height;
const stopMine=async()=>{await rpc(na,'stop_mining',{},false,'/stop_mining');mining=false;};
const receipts=[];let reject=false;
try {
 for(const [name,p,peer,r]of [['node-a',pa,pc,na],['node-c',pc,pa,nc]])launch('discreted',['--testnet','--data-dir',state+'/'+name,'--no-console','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(r),'--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p),'--add-exclusive-node','127.0.0.1:'+peer,'--allow-local-ip','--hide-my-port','--log-file',state+'/'+name+'-high.log']);
 await until('node ready',()=>rpc(na,'getlastblockheader'));
 let tracking=await wallet('merchant-tracking',wp);await until('tracking registry',async()=>{const s=await rpc(wp,'getDepositScheme',{},true);return s.tracking===true&&s.depositCount===count;});
 await wallet('miner-sender',sp);const setup=await wallet('merchant-setup',mp);
 await until('setup synchronized',async()=>{const b=await rpc(mp,'getBalance',{},true);return b.availableBalance>=14001&&b.scannedHeight>=await height();});
 const spend=await rpc(mp,'getSpendKeys',{address:(await rpc(mp,'getAddresses',{},true)).addresses[0]},true);
 const mine=async()=>{await rpc(na,'start_mining',{miner_spend_key:spend.spendSecretKey,miner_view_key:'',threads_count:1},false,'/start_mining');mining=true;};
 await until('payer synchronized',async()=>(await rpc(sp,'getBalance',{},true)).scannedHeight>=await height());
 if((await rpc(sp,'getBalance',{},true)).availableBalance<12346){
  const address=(await rpc(sp,'getAddresses',{},true)).addresses[0];
  const funding=await rpc(mp,'sendTransaction',{transfers:[{address,amount:14000}],fee:1,unlockHeight:0},true);
  record('disposable payer funding submitted once',{transactionHash:funding.transactionHash});
  // Bound mining by node height, then let wallet scanners catch the stopped tip.
  // Continuous difficulty-one mining can outrun their balance projection.
  const before=await height();await mine();await until('bounded funding blocks',async()=>(await height())>=before+12);await stopMine();
  await until('payer funding maturity',async()=>(await rpc(sp,'getBalance',{},true)).availableBalance>=12346);
  record('funding scanner caught stopped private-chain tip',{height:await height()});
 }
 await rpc(mp,'save',{},true);await stop(setup);
 store=new DiscretePayStore(h.gatewayEnv.DISCRETE_PAY_GATEWAY_DATABASE_PATH);
 const nativeClient=new WalletdAllocationClient({endpoint:'http://127.0.0.1:'+wp+'/json_rpc',username:h.rpcUser,password:h.rpcPassword});
 const attest=parseWalletAttestation(await nativeClient.getDepositScheme(),await nativeClient.getAccountStatus());
 const registry=await readPagedRegistry(nativeClient,attest);assert.equal(registry.length,count);
 const existing=store.listAssignedInvoices(),assigned=new Set(existing.map(r=>r.depositT)),merchant=existing[0].merchantId;
 const seedStart=performance.now(),journal=new AllocationJournal(h.facadeEnv.DISCRETE_PAY_FACADE_JOURNAL_PATH);
 const prefixes=large?registryPrefixes(registry):undefined;
 try{for(const entry of registry){const baselineHash=prefixes?.next().value;if(large&&[1,1000,10000,99999,100000].includes(entry.routingT))assert.equal(baselineHash,registryHash(registry.slice(0,entry.routingT-1)));if(assigned.has(entry.routingT))continue;const t=entry.routingT,now=Date.now(),requestId='combined_seed_request_'+String(t).padStart(8,'0');
  const created=store.createInvoice({id:'combined-seed-invoice-'+t,merchantId:merchant,publicToken:'pay_'+randomBytes(24).toString('base64url'),idempotencyKey:'combined-seeded-'+t,network:'xds-testnet',amountAtomic:1n,expiresInSeconds:3600,requiredConfirmations:2,expiresAtMs:now+3600000,detectionGraceEndsAtMs:now+3660000,facadeRequestId:requestId,createdAtMs:now});
  assert.equal(created.kind,'created');journal.prepare(requestId,large?baselineHash:registryHash(registry.slice(0,t-1)),t-1,attest.accountNumber,now);journal.commit(requestId,entry,now);
  store.assignInvoiceDeposit(created.invoice.id,requestId,t,entry.address,now);
 }
 assert.equal(journal.list().length,count);assert(journal.list().every(r=>r.state==='committed'));
 }finally{journal.close();}
 assert.equal(store.listAssignedInvoices().length,count);
 record('seeded full invoice and allocation journals using validated native addresses',{seeded:count-existing.length,retainedOriginal:existing.length,elapsedMs:Math.round(performance.now()-seedStart),nativeAllocationsDuringSeeding:0});
 const startApps=async()=>{const start=performance.now();facade=await startFacadeRuntime({...h.facadeEnv,DISCRETE_PAY_FACADE_REGISTRY_MODE:'paged-v1',DISCRETE_PAY_FACADE_LISTEN_PORT:String(fp),DISCRETE_PAY_WALLETD_ENDPOINT:'http://127.0.0.1:'+wp+'/json_rpc'});gateway=await startGatewayRuntime({...h.gatewayEnv,DISCRETE_PAY_GATEWAY_LISTEN_PORT:String(gp),DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT:'http://127.0.0.1:'+fp+'/v1/deposits'});return Math.round(performance.now()-start);};
 const closeApps=async()=>{await gateway?.close();gateway=undefined;await facade?.close();facade=undefined;};
 record('native facade and gateway open full10000 journals',{elapsedMs:await startApps()});
 const targets=store.listAssignedInvoices().filter(r=>r.depositT===count);assert.equal(targets.length,1);
 const target=targets[0],old=store.getInvoiceById(h.invoiceId),oldEvents=store.listInvoiceEvents(h.invoiceId);
 assert.equal(target.amountAtomic,12345n);assert.equal(target.receivedAtomic,0n);assert.equal(old.confirmedAtomic,12345n);
 const neighbors=store.listAssignedInvoices().filter(r=>r.depositT>=count-3&&r.depositT<count);assert.equal(neighbors.length,3);assert(neighbors.every(r=>r.receivedAtomic===0n));
 record('native tracking10000 and unique unpaid last invoice',{routingIndex:target.depositT,requiredConfirmations:target.requiredConfirmations,expiredAtBaseline:Date.now()>target.expiresAtMs,invoiceRows:store.listAssignedInvoices().length});
 web=await startPublicWebRuntime({...h.publicEnv,DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT:String(pp)});
 const publicInvoice=async()=>{const r=await fetch('http://127.0.0.1:'+web.address.port+'/v1/public/invoices/'+target.publicToken);assert.equal(r.status,200);return(await r.json()).invoice;};
 receiver=httpsServer({cert,key},async(req,res)=>{try{assert.equal(req.method,'POST');assert.equal(req.url,'/webhook');const chunks=[];let size=0;for await(const c of req){size+=c.length;assert(size<=65536);chunks.push(c);}const body=Buffer.concat(chunks),headers=req.headers,id=headers['x-discrete-pay-delivery-id'],event=headers['x-discrete-pay-event-id'],digest=sha(body);
  const expected=createHmac('sha256',Buffer.from(h.receiver.secret,'hex')).update(`v1\n${headers['x-discrete-pay-timestamp-ms']}\n${id}\n${event}\n${digest}\n`).update(body).digest('hex');
  const valid=headers['x-discrete-pay-signature']==='v1='+expected&&headers['x-discrete-pay-idempotency-key']===id;assert(valid);
  receipts.push({id,event,digest,valid,rejected:reject,payload:JSON.parse(body)});res.writeHead(reject?503:204).end();
 }catch{res.writeHead(400).end();}});receiver.listen(h.receiver.port,'127.0.0.1');await once(receiver,'listening');
 const config=JSON.parse(rewrite(await readFile(state+'/worker.json','utf8')));config.walletEndpoint='http://127.0.0.1:'+wp+'/json_rpc';config.nodeEndpoint='http://127.0.0.1:'+na+'/json_rpc';
 const workerEnv={DISCRETE_PAY_WORKER_ENABLED:'true',DISCRETE_PAY_WORKER_CONFIG_PATH:state+'/high-worker.json'};await writeFile(workerEnv.DISCRETE_PAY_WORKER_CONFIG_PATH,JSON.stringify(config),{mode:0o600});
 const drain=async()=>{for(let i=0;i<50;i++){const d=await worker.deliverOnce();if(d.kind==='idle')return;assert.equal(d.kind,'delivered');}throw new Error('outbox drain exceeded bound');};
 worker=await openWorkerRuntime(workerEnv);record('worker opened before baseline scan',{heapUsed:process.memoryUsage().heapUsed});await until('baseline scanner caught up',async()=>(await worker.scanOnce()).caughtUp);record('baseline scanner caught up',{heapUsed:process.memoryUsage().heapUsed});await drain();
 await until('payer synced before send',async()=>{const b=await rpc(sp,'getBalance',{},true);return b.availableBalance>=12346&&b.scannedHeight>=await height();});
 const payment=await rpc(sp,'sendTransaction',{transfers:[{address:target.depositAccount,amount:12345}],fee:1,unlockHeight:0},true);
 record('native payment to T10000 submitted once',{transactionHash:payment.transactionHash,amountAtomic:'12345'});
 await writeFile(dir+'/submitted-payment.json',JSON.stringify({transactionHash:payment.transactionHash,routingIndex:count}),{mode:0o600});
 await until('high index mempool detection',async()=>{await worker.scanOnce();return store.getInvoiceById(target.id).observedAtomic===12345n;});
 record('high index native mempool detected',{publicStatus:(await publicInvoice()).status});
 reject=true;assert.equal((await worker.deliverOnce()).kind,'retry_scheduled');const failed=receipts.at(-1);assert.equal(failed.payload.invoice_id,target.id);assert(failed.valid&&failed.rejected);
 await worker.close();worker=undefined;reject=false;await delay(1100);worker=await openWorkerRuntime(workerEnv);assert.equal((await worker.deliverOnce()).kind,'delivered');const retried=receipts.at(-1);assert.equal(retried.id,failed.id);assert.equal(retried.digest,failed.digest);assert(retried.valid&&!retried.rejected);
 record('T10000 HTTPS HMAC 503 and exact durable retry across worker reopen');
 const beforePaymentMining=await height();await mine();await until('bounded payment blocks',async()=>(await height())>=beforePaymentMining+3);await stopMine();
 await until('high index transaction mined with two confirmations',async()=>{const tx=(await rpc(wp,'getTransaction',{transactionHash:payment.transactionHash},true)).transaction;return tx.blockIndex<2147483647&&(await height())>=tx.blockIndex+1;});
 await until('high index confirmed projection',async()=>{await worker.scanOnce();return store.getInvoiceById(target.id).confirmedAtomic===12345n;});
 const paid=store.getInvoiceById(target.id),publicPaid=await publicInvoice();assert(['confirmed','paid_late'].includes(paid.status));assert.equal(publicPaid.status,paid.status);
 await drain();assert(receipts.some(r=>r.payload.invoice_id===target.id&&r.payload.confirmed_atomic==='12345'&&r.valid&&!r.rejected));
 record('native T10000 fully paid through public HTTP and signed webhook',{status:paid.status,confirmedAtomic:paid.confirmedAtomic.toString(),requiredConfirmations:paid.requiredConfirmations});
 const events=store.listInvoiceEvents(target.id),tip=store.getCanonicalTip();await stop(tracking);await assert.rejects(()=>worker.scanOnce());assert.deepEqual(store.getCanonicalTip(),tip);assert.equal(store.getInvoiceById(target.id).confirmedAtomic,12345n);
 tracking=await wallet('merchant-tracking',wp);await until('fresh tracking wallet recovery',async()=>{await worker.scanOnce();return true;});
 await worker.close();worker=undefined;worker=await openWorkerRuntime(workerEnv);await worker.scanOnce();await worker.scanOnce();assert.deepEqual(store.listInvoiceEvents(target.id),events);assert.equal((await worker.deliverOnce()).kind,'idle');
 assert.equal((await rpc(wp,'getDepositScheme',{},true)).depositCount,count);assert.equal(store.getInvoiceById(target.id).confirmedAtomic,12345n);assert.equal((await publicInvoice()).status,paid.status);
 assert.equal(store.getInvoiceById(h.invoiceId).confirmedAtomic,old.confirmedAtomic);assert.deepEqual(store.listInvoiceEvents(h.invoiceId),oldEvents);
 assert(neighbors.every(r=>{const v=store.getInvoiceById(r.id);return v.receivedAtomic===0n&&v.confirmedAtomic===0n&&v.observedAtomic===0n;}));
 record('T10000 wallet outage and wallet/worker reopen preserve payment without duplicate events or wrong-invoice credits',{registryCount:count,invoiceRows:count,unpaidNeighbors:3,originalConfirmedAtomic:'12345',targetEventCount:events.length});
 // A distinct native transaction credits twenty seeded high-index invoices.
 const batch=store.listAssignedInvoices().filter(r=>r.depositT>=count-1000&&r.depositT<count-980);assert.equal(batch.length,20);assert(batch.every(r=>r.confirmedAtomic===0n&&r.amountAtomic===1n));
 const paymentBatch=await rpc(sp,'sendTransaction',{transfers:batch.map(r=>({address:r.depositAccount,amount:1})),fee:1,unlockHeight:0},true);
 await writeFile(dir+'/submitted-batch.json',JSON.stringify({transactionHash:paymentBatch.transactionHash,count:20}),{mode:0o600});
 record('one native transaction to20 seeded high-index invoices submitted once',{transactionHash:paymentBatch.transactionHash,outputs:20});
 await until('batch observed at10000 invoices',async()=>{await worker.scanOnce();return batch.every(r=>store.getInvoiceById(r.id).observedAtomic===1n);});
 const batchStart=await height();await mine();await until('bounded batch blocks',async()=>(await height())>=batchStart+3);await stopMine();
 await until('batch confirmed at10000 invoices',async()=>{await worker.scanOnce();return batch.every(r=>store.getInvoiceById(r.id).confirmedAtomic===1n);});
 await drain();assert(batch.every(r=>receipts.some(v=>v.payload.invoice_id===r.id&&v.payload.confirmed_atomic==='1'&&v.valid&&!v.rejected)));
 const retainedEvents=new Map(batch.map(r=>[r.id,store.listInvoiceEvents(r.id).length])),cycleMs=[],steadyStart=performance.now();
 for(let i=0;i<20;i++){const started=performance.now();const cycle=await worker.scanOnce();assert(cycle.caughtUp);assert.equal(cycle.eventsCreated,0);assert.equal((await worker.deliverOnce()).kind,'idle');cycleMs.push(Math.round(performance.now()-started));}
 assert(batch.every(r=>store.listInvoiceEvents(r.id).length===retainedEvents.get(r.id)));
 assert.equal(store.listAssignedInvoices().filter(r=>r.confirmedAtomic>0n).length,22);
 record('20 confirmed native recipients and20 stable full-journal scan cycles',{invoiceRows:count,elapsedMs:Math.round(performance.now()-steadyStart),minCycleMs:Math.min(...cycleMs),maxCycleMs:Math.max(...cycleMs),meanCycleMs:Math.round(cycleMs.reduce((a,b)=>a+b,0)/cycleMs.length),duplicateEvents:0});
 const createNext=async(expected)=>{const started=performance.now();const r=await fetch('http://127.0.0.1:'+gp+'/v1/invoices',{method:'POST',headers:{authorization:'Bearer '+h.merchantToken,'content-type':'application/json','idempotency-key':large?target.idempotencyKey:'combined-native-next-invoice'},body:JSON.stringify({amount_atomic:large?target.amountAtomic.toString():'1',expires_in_seconds:3600,required_confirmations:2}),signal:AbortSignal.timeout(15000)});assert.equal(r.status,expected);return {id:(await r.json()).invoice.id,elapsedMs:Math.round(performance.now()-started)};};
 // The existing paged resource ceiling is100000: do NOT raise it for a test.
 const retainedCount=large?count:count+1;
 if(large){
  for(let i=0;i<2;i++){
   const r=await fetch('http://127.0.0.1:'+gp+'/v1/invoices',{method:'POST',headers:{authorization:'Bearer '+h.merchantToken,'content-type':'application/json','idempotency-key':'combined-over-capacity-0001'},body:JSON.stringify({amount_atomic:'1',expires_in_seconds:3600,required_confirmations:2}),signal:AbortSignal.timeout(15000)});
   assert.equal(r.status,503);assert.equal((await r.json()).error.code,'invoice_unavailable');
  }
  const retainedJournal=new AllocationJournal(h.facadeEnv.DISCRETE_PAY_FACADE_JOURNAL_PATH);
  try{assert.equal(retainedJournal.list().length,count);}finally{retainedJournal.close();}
  record('full native capacity refuses extra allocation and its retry before journal prepare',{registryCount:(await nativeClient.getDepositScheme()).depositCount,expectedCount:count});
 }
 const next=await createNext(large?200:201);assert.equal(store.getInvoiceById(next.id).depositT,retainedCount);assert.equal((await nativeClient.getDepositScheme()).depositCount,retainedCount);assert.equal(store.listAssignedInvoices().length,retainedCount);
 await closeApps();const reopenMs=await startApps();assert.equal((await createNext(200)).id,next.id);assert.equal((await nativeClient.getDepositScheme()).depositCount,retainedCount);
 record(large?'full native capacity retained invoice replay across facade/gateway reopen':'actual native merchant allocation10001 with full journal and cold reopen replay',{allocationMs:next.elapsedMs,reopenMs,invoiceRows:retainedCount});
 if(large){
  const started=performance.now(),mixed=[];let reads=0,replays=0;
  while(performance.now()-started<600000){
   const begin=performance.now();
   const [scan,page,replay,response]=await Promise.all([worker.scanOnce(),publicInvoice(),createNext(200),fetch('http://127.0.0.1:'+gp+'/v1/invoices/'+next.id,{headers:{authorization:'Bearer '+h.merchantToken},signal:AbortSignal.timeout(15000)})]);
   assert(scan.caughtUp);assert.equal(scan.eventsCreated,0);assert.equal(page.status,paid.status);assert.equal(replay.id,next.id);assert.equal(response.status,200);assert.equal((await response.json()).invoice.id,next.id);
   assert.equal((await worker.deliverOnce()).kind,'idle');reads+=2;replays++;
   mixed.push(Math.round(performance.now()-begin));
   if(mixed.length%10===0)record('sustained mixed native scan public/merchant reads and replay progress',{cycles:mixed.length,elapsedMs:Math.round(performance.now()-started)});
   await delay(Math.max(0,2000-(performance.now()-begin)));
  }
  assert(mixed.length>=10);assert.equal((await nativeClient.getDepositScheme()).depositCount,count);assert.equal(store.listAssignedInvoices().length,count);assert.equal(store.getInvoiceById(h.invoiceId).confirmedAtomic,old.confirmedAtomic);assert.deepEqual(store.listInvoiceEvents(target.id),events);assert(batch.every(r=>store.listInvoiceEvents(r.id).length===retainedEvents.get(r.id)));
  const sorted=[...mixed].sort((a,b)=>a-b);
  record('10-minute full-journal native scanner mixed HTTP and replay retained without duplicate credits',{invoiceRows:count,cycles:mixed.length,reads,replays,elapsedMs:Math.round(performance.now()-started),p50Ms:sorted[Math.floor(sorted.length*.5)],p95Ms:sorted[Math.floor(sorted.length*.95)],maxMs:sorted.at(-1)});
 }
 await closeApps();
 result.result='PASS';
}catch(e){result.result='FAIL';result.error=e.message;console.error(e.message);process.exitCode=1;}
finally{if(mining)await stopMine().catch(()=>{});await worker?.close();await gateway?.close();await facade?.close();await web?.close();if(receiver?.listening)await new Promise(r=>receiver.close(r));store?.close();const cleanup=await Promise.allSettled([...children].map(stop));if(large){result.cleanup=cleanup;if(cleanup.some(r=>r.status==='rejected'||r.value?.forced)){result.result='FAIL';result.error='native cleanup required forced termination or failed';process.exitCode=1;}}await writeFile(dir+'/evidence.json',JSON.stringify(result,null,2),{mode:0o600});console.log('Evidence:',dir+'/evidence.json');}
