// Disposable, bounded native registry/HTTP qualification. No mining or sending.
import assert from 'node:assert/strict';
import {mkdtemp,cp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
const root='/opt/discrete-pay-qualification';
const pay=root+'/pay-merged-4d2f069';
assert.equal(process.env.DISCRETE_PAY_NATIVE_LOAD,'copied-disposable-only');
const target=Number(process.env.DISCRETE_PAY_NATIVE_LOAD_COUNT);
assert([10000,100000].includes(target));
const source=root+'/pay-paged-tail/build/native-test/paged/run-NFdcs1';
const bin=root+'/pay-paged-tail/build/native-test/paged-bin/src/';
for(const [name,sha]of [['walletd','630a033e0b41ebb01d666886948bd9a4affa4c44a299474bc125c3284afc15d1'],['discreted','fb9408fb76ab54eebd7016c8d997ad9ece39399b4851e8308e86e6fc3725cfb5']])
  assert.equal(createHash('sha256').update(await readFile(bin+name)).digest('hex'),sha);
await mkdir(pay+'/build/native-load',{recursive:true});
const dir=await mkdtemp(pay+'/build/native-load/run-');
await cp(source,dir+'/state',{recursive:true,force:false,errorOnExist:true});
const state=dir+'/state';
const h=JSON.parse((await readFile(source+'/service-handoff.json','utf8')).replaceAll(source,state));
const {startFacadeRuntime}=await import(pay+'/dist/services/walletd-facade/src/runtime.js');
const {startGatewayRuntime}=await import(pay+'/dist/apps/gateway-api/src/runtime.js');
const {DiscretePayStore}=await import(pay+'/dist/src/persistence/store.js');
const result={payCommit:'4d2f06952e2a566df4e92e9ee82b9f38601e0427',walletdCommit:'8703c16fa40ffc8456e3d71696b6220b32b4d74a',scope:'copied private native fixture; no sends/mining; not production or sustained load',target,checks:[]};
const record=(check,value=true)=>{result.checks.push({check,value});console.log(check,JSON.stringify(value));};
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
async function until(fn,ms=60000){const end=Date.now()+ms;let last;while(Date.now()<end){try{const v=await fn();if(v)return v;}catch(e){last=e.name;}await delay(300);}throw new Error('fixture wait timeout '+(last??''));}
const children=new Set();let facade,gateway,wallet,store;
function launch(name,args){const c=spawn(bin+name,args,{cwd:state,stdio:'ignore'});children.add(c);c.once('exit',()=>children.delete(c));return c;}
async function stop(c){if(c.exitCode!==null||c.signalCode!==null)return;const p=once(c,'exit');c.kill('SIGTERM');await p;}
const [na,nc,pa,pc,wp,fp,gp]=await Promise.all(Array.from({length:7},port));
async function rpc(p,method,params={},auth=false){const r=await fetch('http://127.0.0.1:'+p+'/json_rpc',{method:'POST',headers:{'content-type':'application/json',...(auth?{authorization:'Basic '+Buffer.from(h.rpcUser+':'+h.rpcPassword).toString('base64')}:{})},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params}),signal:AbortSignal.timeout(10000)});assert.equal(r.status,200);const b=await r.json();assert(!b.error,'native RPC rejected '+method);return b.result;}
const count=async()=>(await rpc(wp,'getDepositScheme',{},true)).depositCount;
async function startApps(){const started=performance.now();facade=await startFacadeRuntime({...h.facadeEnv,DISCRETE_PAY_FACADE_REGISTRY_MODE:'paged-v1',DISCRETE_PAY_FACADE_LISTEN_PORT:String(fp),DISCRETE_PAY_WALLETD_ENDPOINT:'http://127.0.0.1:'+wp+'/json_rpc'});gateway=await startGatewayRuntime({...h.gatewayEnv,DISCRETE_PAY_GATEWAY_LISTEN_PORT:String(gp),DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT:'http://127.0.0.1:'+fp+'/v1/deposits'});return Math.round(performance.now()-started);}
async function closeApps(){await gateway?.close();gateway=undefined;await facade?.close();facade=undefined;}
async function create(key,expected=201){const started=performance.now();const r=await fetch('http://127.0.0.1:'+gp+'/v1/invoices',{method:'POST',headers:{authorization:'Bearer '+h.merchantToken,'content-type':'application/json','idempotency-key':key==='native-test-order'?key:'native-load-test-'+key},body:JSON.stringify({amount_atomic:'12345',expires_in_seconds:3600,required_confirmations:2}),signal:AbortSignal.timeout(15000)});const ms=Math.round(performance.now()-started);assert.equal(r.status,expected,'merchant HTTP status for '+key+' at '+ms+'ms');const body=await r.json();return {id:body.invoice.id,ms};}
try {
 for(const [name,p,peer,r]of [['node-a',pa,pc,na],['node-c',pc,pa,nc]])launch('discreted',['--testnet','--data-dir',state+'/'+name,'--no-console','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(r),'--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p),'--add-exclusive-node','127.0.0.1:'+peer,'--allow-local-ip','--hide-my-port','--log-file',state+'/'+name+'-load.log']);
 await until(()=>rpc(na,'getlastblockheader'));
 let conf=(await readFile(source+'/merchant-tracking.conf','utf8')).replaceAll(source,state).replace(/^bind-port=.*$/m,'bind-port='+wp).replace(/^daemon-port=.*$/m,'daemon-port='+na);
 await writeFile(state+'/load-tracking.conf',conf,{mode:0o600});
 const startWallet=()=>launch('walletd',['--config',state+'/load-tracking.conf','--testnet']);
 wallet=startWallet();await until(async()=>{const s=await rpc(wp,'getDepositScheme',{},true);return s.tracking===true && s.depositCount===1001;});
 store=new DiscretePayStore(h.gatewayEnv.DISCRETE_PAY_GATEWAY_DATABASE_PATH);
 const original=store.getInvoiceById(h.invoiceId),events=store.listInvoiceEvents(h.invoiceId),tip=store.getCanonicalTip();
 assert.equal(original.confirmedAtomic,12345n);
 const cold1001=await startApps();assert.equal((await create('native-test-order',200)).id,h.invoiceId);
 const first=await create('load-first');assert.equal(await count(),1002);
 record('copied1001 cold start and merchant allocation/replay',{coldStartMs:cold1001,allocationMs:first.ms});
 await closeApps();
 const startCount=await count(),prefillTo=target-4;let issued=0,next=startCount;const indices=new Set();const start=performance.now();
 // Native test-only prefill while Pay is stopped; eight concurrent requests,
 // every returned index checked. No ambiguous allocation is retried.
 const settled=await Promise.allSettled(Array.from({length:8},async()=>{while(next<prefillTo){next++;const a=await rpc(wp,'createDepositAddress',{},true);assert(Number.isInteger(a.index)&&a.index>startCount&&a.index<=prefillTo);assert(!indices.has(a.index));indices.add(a.index);issued++;if(issued%1000===0)record('native prefill progress',{issued,total:startCount+issued,elapsedMs:Math.round(performance.now()-start)});}}));
 assert(settled.every(r=>r.status==='fulfilled'),'bounded native prefill failed; no retry');
 assert.equal(indices.size,prefillTo-startCount);assert.equal(await count(),prefillTo);
 record('native concurrent prefill unique and complete',{count:prefillTo,elapsedMs:Math.round(performance.now()-start)});
 const coldLarge=await startApps();
 const requests=await Promise.all(Array.from({length:4},(_,i)=>create('load-burst-'+i)));
 assert.equal(new Set(requests.map(r=>r.id)).size,4);assert.equal(await count(),target);
 record('native large registry merchant four-request burst',{count:target,coldStartMs:coldLarge,latencyMs:requests.map(r=>r.ms)});
 await closeApps();await stop(wallet);
 // A fresh wallet process plus fresh facade cache must recover the same registry.
 wallet=startWallet();await until(async()=>(await count())===target);
 const reopened=await startApps();
 for(let i=0;i<4;i++)assert.equal((await create('load-burst-'+i,200)).id,requests[i].id);
 assert.equal(await count(),target);
 assert.deepEqual(store.getInvoiceById(h.invoiceId),original);assert.deepEqual(store.listInvoiceEvents(h.invoiceId),events);assert.deepEqual(store.getCanonicalTip(),tip);
 record('wallet and facade reopen preserves all issued invoices and original payment',{count:target,coldStartMs:reopened});
 result.result='PASS';
}catch(e){result.result='FAIL';result.error=e.message;console.error(e.message);process.exitCode=1;}
finally{await closeApps();store?.close();await Promise.allSettled([...children].map(stop));await writeFile(dir+'/evidence.json',JSON.stringify(result,null,2),{mode:0o600});console.log('Evidence:',dir+'/evidence.json');}
