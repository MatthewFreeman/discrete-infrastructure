// Read-only RPC diagnosis on a COPY of the failed disposable run. No mining/sending.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdtemp,cp} from 'node:fs/promises';
import {createWriteStream} from 'node:fs';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {setTimeout as delay} from 'node:timers/promises';
const root='/opt/discrete-pay-qualification',pay=root+'/pay';
assert.equal(process.env.DISCRETE_PAY_SCAN_DIAGNOSTIC,'copy-failed-current-run');
const source=pay+'/build/native-test/current/run-Mi8zwp';
const dir=(await mkdtemp(root+'/scan-diagnostic-'))+'/state';
await cp(source,dir,{recursive:true,force:false,errorOnExist:true});
const cfg=JSON.parse(await readFile(dir+'/worker.json','utf8'));
const result={sourceRun:'run-Mi8zwp',scope:'copied disposable state, read-only RPC, no mining/sending',checks:[]};
const record=(check,value)=>{result.checks.push({check,value});console.log(check,JSON.stringify(value));};
const children=new Set();
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
function launch(name,exe,args){const log=createWriteStream(dir+'/'+name+'.diagnostic.log',{mode:0o600});const child=spawn(exe,args,{cwd:dir,stdio:['ignore','pipe','pipe']});children.add(child);child.stdout.pipe(log);child.stderr.pipe(log,{end:false});child.once('exit',()=>{children.delete(child);log.end();});return child;}
async function raw(endpoint,method,params={},wallet=false){const response=await fetch(endpoint,{method:'POST',headers:{'content-type':'application/json',...(wallet?{authorization:'Basic '+Buffer.from(cfg.walletUsername+':'+cfg.walletPassword).toString('base64')}:{})},body:JSON.stringify({jsonrpc:'2.0',id:77,method,params}),signal:AbortSignal.timeout(5000)});return {status:response.status,type:response.headers.get('content-type'),body:await response.json()};}
async function until(fn){const end=Date.now()+60000;while(Date.now()<end){try{if(await fn())return;}catch{}await delay(500);}throw new Error('diagnostic startup timeout');}
let store;
try{
 const [na,nc,pa,pc,wp]=await Promise.all([port(),port(),port(),port(),port()]);
 for(const [name,rpc,p2p,peer] of [['node-a',na,pa,pc],['node-c',nc,pc,pa]])launch(name,root+'/pay/build/native-test/current-bin/src/discreted',['--testnet','--data-dir',dir+'/'+name,'--no-console','--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p2p),'--add-exclusive-node','127.0.0.1:'+peer,'--allow-local-ip','--hide-my-port','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(rpc),'--log-file',dir+'/'+name+'.new.log']);
 cfg.nodeEndpoint='http://127.0.0.1:'+na+'/json_rpc';cfg.walletEndpoint='http://127.0.0.1:'+wp+'/json_rpc';
 await until(async()=>!!(await raw(cfg.nodeEndpoint,'getlastblockheader')).body.result);
 let conf=await readFile(dir+'/merchant-tracking.conf','utf8');
 conf=conf.replaceAll(source,dir).replace(/^bind-port=.*$/m,'bind-port='+wp).replace(/^daemon-port=.*$/m,'daemon-port='+na);
 await writeFile(dir+'/diagnostic-wallet.conf',conf,{mode:0o600});
 launch('wallet',root+'/current-attestation-binaries/walletd',['--config',dir+'/diagnostic-wallet.conf','--testnet']);
 await until(async()=>!!(await raw(cfg.walletEndpoint,'getStatus',{},true)).body.result);
 const {ReadRpcClient}=await import(pay+'/dist/apps/worker/src/rpc-client.js');
 const {DiscreteScannerRpc}=await import(pay+'/dist/apps/worker/src/discrete-rpc.js');
 const {DiscretePayStore}=await import(pay+'/dist/src/persistence/store.js');
 store=new DiscretePayStore(dir+'/gateway.sqlite3');
 class Trace extends ReadRpcClient{
  constructor(endpoint,credentials){super(endpoint,credentials);this.endpoint=endpoint;this.wallet=!!credentials;}
  async call(method,params={}){try{return await super.call(method,params);}catch(error){const r=await raw(this.endpoint,method,params,this.wallet);const unsafe=[];const visit=(v,p)=>{if(typeof v==='number'&&!Number.isSafeInteger(v))unsafe.push(p);if(v&&typeof v==='object')for(const[k,x]of Object.entries(v))visit(x,p+'.'+k);};visit(r.body,'rpc');record('RPC transport refusal',{method,status:r.status,type:r.type,envelopeKeys:Object.keys(r.body),rpcCode:r.body.error?.code,applicationCode:r.body.error?.data?.application_code,unsafeNumberPaths:unsafe});throw error;}}
 }
 const wallet=new Trace(cfg.walletEndpoint,{username:cfg.walletUsername,password:cfg.walletPassword}),node=new Trace(cfg.nodeEndpoint);
 const scanner=new DiscreteScannerRpc({wallet,node,accountNumber:cfg.accountNumber,genesisHash:cfg.genesisHash,network:cfg.network,invoices:()=>store.listAssignedInvoices()});
 await delay(3000);
 const status=(await raw(cfg.walletEndpoint,'getStatus',{},true)).body.result;
 const balance=(await raw(cfg.walletEndpoint,'getBalance',{},true)).body.result;
 record('wallet sync fields',{blockCount:status.blockCount,knownBlockCount:status.knownBlockCount,localDaemonBlockCount:status.localDaemonBlockCount,peerCount:status.peerCount,lastBlockHash:status.lastBlockHash,scannedHeight:balance.scannedHeight,enabled:balance.enabled});
 record('retained invoice totals',store.listAssignedInvoices().map(i=>({status:i.status,receivedAtomic:String(i.receivedAtomic),confirmedAtomic:String(i.confirmedAtomic)})));
 try{const tip=await scanner.getTip();record('direct scanner tip',tip);record('retained checkpoint',store.getCanonicalTip());for(let height=Math.max(0,tip.height-3);height<=tip.height;height++){try{const b=await scanner.getBlock(height);record('direct block read',{height,payments:b.payments});}catch(e){record('direct block failure',{height,message:e.message});break;}}try{record('direct mempool read',await scanner.getMempool());}catch(e){record('direct mempool failure',e.message);}}catch(e){record('direct tip failure',e.message);}
 result.result='DIAGNOSTIC_CAPTURED';
}catch(e){result.result='DIAGNOSTIC_FAILED';result.error=e.message;process.exitCode=1;console.error(e.message);}
finally{store?.close();await Promise.all([...children].map(async c=>{const exited=once(c,'exit');c.kill('SIGTERM');await exited;}));await writeFile(dir+'/diagnostic-evidence.json',JSON.stringify(result,null,2),{mode:0o600});console.log('Diagnostic evidence:',dir+'/diagnostic-evidence.json');}
