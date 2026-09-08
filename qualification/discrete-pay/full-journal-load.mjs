// Bounded real gateway HTTP + SQLite load with an explicitly fake wallet port.
// This does not mine, sign, submit native payments, or prove native100000.
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile} from 'node:fs/promises';
import {createServer} from 'node:net';
import {once} from 'node:events';
import {randomBytes} from 'node:crypto';
const pay='/opt/discrete-pay-qualification/pay-merged-4d2f069';
assert.equal(process.env.DISCRETE_PAY_JOURNAL_LOAD,'fake-wallet-real-http-sqlite');
const {FakeWalletd}=await import(pay+'/test/walletd-facade/helpers.ts');
const {DepositAllocator}=await import(pay+'/dist/services/walletd-facade/src/allocator.js');
const {AllocationJournal}=await import(pay+'/dist/services/walletd-facade/src/journal.js');
const {startFacadeServer}=await import(pay+'/dist/services/walletd-facade/src/server.js');
const {startGatewayRuntime}=await import(pay+'/dist/apps/gateway-api/src/runtime.js');
const {DiscretePayStore}=await import(pay+'/dist/src/persistence/store.js');
const {MerchantApiKeyAuthority}=await import(pay+'/dist/src/auth/merchant-api-key.js');
const {DatabaseSync}=await import('node:sqlite');
class PagedWallet extends FakeWalletd {
 async listDepositAddressesPage(request){const a=await this.getAccountStatus();assert.equal(request.expectedAccountNumber,a.accountNumber);assert.equal(request.expectedDepositCount,this.registry.length);return {...await this.getDepositScheme(),accountNumber:a.accountNumber,offset:request.offset,addresses:this.registry.slice(request.offset,request.offset+request.limit),indices:this.registry.slice(request.offset,request.offset+request.limit).map((_,i)=>request.offset+i+1)};}
}
await mkdir(pay+'/build/full-journal-load',{recursive:true});const dir=await mkdtemp(pay+'/build/full-journal-load/run-');
const result={payCommit:'4d2f06952e2a566df4e92e9ee82b9f38601e0427',scope:'10000 real merchant HTTP creations and durable SQLite invoice/allocation records; fake wallet port, test rate configuration10000/minute; no native sends or production SLA',checks:[]};
const record=(check,value=true)=>{result.checks.push({check,value});console.log(check,JSON.stringify(value));};
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
const wallet=new PagedWallet(),facadeToken=randomBytes(32).toString('hex'),databasePath=dir+'/gateway.sqlite3',journalPath=dir+'/allocations.sqlite3';
let journal,store,facade,gateway,merchantToken;const fp=await port(),gp=await port();
async function open(){journal=new AllocationJournal(journalPath);store=new DiscretePayStore(databasePath);const allocator=new DepositAllocator({walletd:wallet,journal,registryMode:'paged-v1'});await allocator.initialize();facade=await startFacadeServer({allocator,bearerToken:facadeToken,host:'127.0.0.1',port:fp});gateway=await startGatewayRuntime({DISCRETE_PAY_GATEWAY_ENABLED:'true',DISCRETE_PAY_GATEWAY_LISTEN_PORT:String(gp),DISCRETE_PAY_GATEWAY_DATABASE_PATH:databasePath,DISCRETE_PAY_GATEWAY_NETWORK:'xds-testnet',DISCRETE_PAY_GATEWAY_DETECTION_GRACE_SECONDS:'60',DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT:'http://127.0.0.1:'+fp+'/v1/deposits',DISCRETE_PAY_GATEWAY_FACADE_BEARER_TOKEN:facadeToken,DISCRETE_PAY_GATEWAY_RATE_LIMIT_PER_MINUTE:'10000'});}
async function close(){await gateway?.close();gateway=undefined;await facade?.close();facade=undefined;store?.close();store=undefined;journal?.close();journal=undefined;}
async function create(i,expected=201,amount='12345'){const started=performance.now();const r=await fetch('http://127.0.0.1:'+gp+'/v1/invoices',{method:'POST',headers:{authorization:'Bearer '+merchantToken,'content-type':'application/json','idempotency-key':'full-journal-load-'+String(i).padStart(5,'0')},body:JSON.stringify({amount_atomic:amount,expires_in_seconds:3600,required_confirmations:2}),signal:AbortSignal.timeout(20000)});assert.equal(r.status,expected,'merchant HTTP status at journal index '+i);const body=await r.json();return {id:body.invoice?.id,ms:Math.round(performance.now()-started)};}
try{
 await open();store.createMerchant('load-merchant',Date.now());merchantToken=new MerchantApiKeyAuthority({store}).issue({merchantId:'load-merchant',scopes:['invoices:create','invoices:read'],createdAtMs:Date.now()}).token;
 const ids=new Map(),latencies=[];let next=0,completed=0;const started=performance.now();
 const settled=await Promise.allSettled(Array.from({length:8},async()=>{while(next<10000){const i=next++;const r=await create(i);ids.set(i,r.id);latencies.push(r.ms);completed++;if(completed%1000===0)record('real gateway and full journal progress',{completed,elapsedMs:Math.round(performance.now()-started),latestLatencyMs:r.ms});}}));
 if(settled.some(r=>r.status==='rejected'))record('failed caller diagnostics',{completed,nativeCreateCalls:wallet.createCalls,errors:settled.filter(r=>r.status==='rejected').map(r=>r.reason.message)});
 assert(settled.every(r=>r.status==='fulfilled'),'load request failed; no ambiguous create retry');assert.equal(ids.size,10000);assert.equal(new Set(ids.values()).size,10000);assert.equal(wallet.createCalls,10000);assert.equal(wallet.maxActiveCreates,1);
 const rows=store.listAssignedInvoices(),records=journal.list();assert.equal(rows.length,10000);assert.equal(records.length,10000);assert(records.every(r=>r.state==='committed'));assert.equal(new Set(rows.map(r=>r.depositT)).size,10000);assert.equal(new Set(rows.map(r=>r.depositAccount)).size,10000);assert(rows.every(r=>r.observedAtomic===0n&&r.confirmedAtomic===0n));
 const sorted=[...latencies].sort((a,b)=>a-b);record('10000 HTTP invoices and allocation journal rows with eight callers',{elapsedMs:Math.round(performance.now()-started),p50Ms:sorted[4999],p95Ms:sorted[9499],p99Ms:sorted[9899],maxMs:sorted.at(-1),maxConcurrentNativeCreates:wallet.maxActiveCreates});
 await close();const reopen=performance.now();await open();record('full journal cold reopen',{elapsedMs:Math.round(performance.now()-reopen)});
 const samples=[0,1,999,1000,4999,9997,9998,9999];for(const i of samples)assert.equal((await create(i,200)).id,ids.get(i));await create(9999,409,'12346');assert.equal(wallet.createCalls,10000);assert.equal(journal.list().length,10000);assert.equal(store.listAssignedInvoices().length,10000);record('eight payload-bound replays and conflicting retry retain all10000 allocations');
 await close();for(const path of [databasePath,journalPath]){const db=new DatabaseSync(path,{readOnly:true});assert.equal(Object.values(db.prepare('PRAGMA integrity_check').get())[0],'ok');assert.equal(db.prepare('PRAGMA foreign_key_check').all().length,0);db.close();}record('both durable SQLite files integrity and foreign-key checks');
 result.result='PASS';
}catch(e){result.result='FAIL';result.error=e.message;console.error(e.message);process.exitCode=1;}
finally{await close();await writeFile(dir+'/evidence.json',JSON.stringify(result,null,2),{mode:0o600});console.log('Evidence:',dir+'/evidence.json');}
