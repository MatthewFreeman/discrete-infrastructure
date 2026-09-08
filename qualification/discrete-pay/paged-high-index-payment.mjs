// Private-chain disposable-copy qualification. Never a production payment tool.
import assert from 'node:assert/strict';
import {mkdtemp,cp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {createServer as httpsServer} from 'node:https';
import {createHash,createHmac} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
assert.equal(process.env.DISCRETE_PAY_HIGH_INDEX,'copied-private-chain-only');
const root='/opt/discrete-pay-qualification',pay=root+'/pay-merged-4d2f069';
const source=pay+'/build/native-load/run-mku6hq/state';
const original=root+'/pay-paged-tail/build/native-test/paged/run-NFdcs1';
const bin=root+'/pay-paged-tail/build/native-test/paged-bin/src/';
const sha=data=>createHash('sha256').update(data).digest('hex');
for(const [name,hash]of [['walletd','630a033e0b41ebb01d666886948bd9a4affa4c44a299474bc125c3284afc15d1'],['discreted','fb9408fb76ab54eebd7016c8d997ad9ece39399b4851e8308e86e6fc3725cfb5']])assert.equal(sha(await readFile(bin+name)),hash);
assert.equal(sha(await readFile(source+'/../evidence.json')),'337bbdac87d62a00085b48cfdd25da152a24868ae4f1707d6f59ec0224b642a0');
await mkdir(pay+'/build/native-high-index',{recursive:true});
const dir=await mkdtemp(pay+'/build/native-high-index/run-'),state=dir+'/state';
await cp(source,state,{recursive:true,force:false,errorOnExist:true});
const rewrite=text=>text.replaceAll(original,state).replaceAll(source,state);
const h=JSON.parse(rewrite(await readFile(state+'/service-handoff.json','utf8')));
const {DiscretePayStore}=await import(pay+'/dist/src/persistence/store.js');
const {startPublicWebRuntime}=await import(pay+'/dist/apps/public-web/src/runtime.js');
const {openWorkerRuntime}=await import(pay+'/dist/apps/worker/src/runtime.js');
const {cert,key}=await import(pay+'/test/worker-runtime/tls-fixture.ts');
const result={payCommit:'4d2f06952e2a566df4e92e9ee82b9f38601e0427',walletdCommit:'8703c16fa40ffc8456e3d71696b6220b32b4d74a',scope:'native T=10000 payment on copied private testchain; no real funds or production; small invoice journal',checks:[]};
const record=(check,value=true)=>{result.checks.push({check,value});console.log(check,JSON.stringify(value));};
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
async function until(label,fn,ms=90000){const end=Date.now()+ms;let last;while(Date.now()<end){try{const v=await fn();if(v)return v;}catch(e){last=e.name;}await delay(300);}throw new Error('fixture timeout: '+label+' '+(last??''));}
const children=new Set();let worker,web,receiver,store,mining=false;
function launch(name,args){const c=spawn(bin+name,args,{cwd:state,stdio:'ignore'});children.add(c);c.once('exit',()=>children.delete(c));return c;}
async function stop(c){if(c.exitCode!==null||c.signalCode!==null)return;const p=once(c,'exit');c.kill('SIGTERM');await p;}
const [na,nc,pa,pc,wp,sp,mp,pp]=await Promise.all(Array.from({length:8},port));
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
 let tracking=await wallet('merchant-tracking',wp);await until('tracking10000',async()=>{const s=await rpc(wp,'getDepositScheme',{},true);return s.tracking===true&&s.depositCount===10000;});
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
 const targets=store.listAssignedInvoices().filter(r=>r.depositT===10000);assert.equal(targets.length,1);
 const target=targets[0],old=store.getInvoiceById(h.invoiceId),oldEvents=store.listInvoiceEvents(h.invoiceId);
 assert.equal(target.amountAtomic,12345n);assert.equal(target.receivedAtomic,0n);assert.equal(old.confirmedAtomic,12345n);
 const neighbors=store.listAssignedInvoices().filter(r=>r.depositT>=9997&&r.depositT<10000);assert.equal(neighbors.length,3);assert(neighbors.every(r=>r.receivedAtomic===0n));
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
 worker=await openWorkerRuntime(workerEnv);await until('baseline scanner caught up',async()=>(await worker.scanOnce()).caughtUp);await drain();
 await until('payer synced before send',async()=>{const b=await rpc(sp,'getBalance',{},true);return b.availableBalance>=12346&&b.scannedHeight>=await height();});
 const payment=await rpc(sp,'sendTransaction',{transfers:[{address:target.depositAccount,amount:12345}],fee:1,unlockHeight:0},true);
 record('native payment to T10000 submitted once',{transactionHash:payment.transactionHash,amountAtomic:'12345'});
 await writeFile(dir+'/submitted-payment.json',JSON.stringify({transactionHash:payment.transactionHash,routingIndex:10000}),{mode:0o600});
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
 assert.equal((await rpc(wp,'getDepositScheme',{},true)).depositCount,10000);assert.equal(store.getInvoiceById(target.id).confirmedAtomic,12345n);assert.equal((await publicInvoice()).status,paid.status);
 assert.equal(store.getInvoiceById(h.invoiceId).confirmedAtomic,old.confirmedAtomic);assert.deepEqual(store.listInvoiceEvents(h.invoiceId),oldEvents);
 assert(neighbors.every(r=>{const v=store.getInvoiceById(r.id);return v.receivedAtomic===0n&&v.confirmedAtomic===0n&&v.observedAtomic===0n;}));
 record('T10000 wallet outage and wallet/worker reopen preserve payment without duplicate events or wrong-invoice credits',{registryCount:10000,unpaidNeighbors:3,originalConfirmedAtomic:'12345',targetEventCount:events.length});
 result.result='PASS';
}catch(e){result.result='FAIL';result.error=e.message;console.error(e.message);process.exitCode=1;}
finally{if(mining)await stopMine().catch(()=>{});await worker?.close();await web?.close();if(receiver?.listening)await new Promise(r=>receiver.close(r));store?.close();await Promise.allSettled([...children].map(stop));await writeFile(dir+'/evidence.json',JSON.stringify(result,null,2),{mode:0o600});console.log('Evidence:',dir+'/evidence.json');}
