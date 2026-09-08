// Disposable GUI qualification only; no public network or production wallets.
import assert from 'node:assert/strict';
import {mkdtemp,cp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:http';
import {createServer as tlsServer} from 'node:https';
import {createHash,createHmac,randomBytes} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
assert.equal(process.env.DISCRETE_PAY_GUI,'private-disposable-only');
const root='/opt/discrete-pay-qualification',pay=root+'/pay-merged-4d2f069';
const source=pay+'/build/native-combined/run-OjCKl5/state';
const bin=root+'/pay-paged-tail/build/native-test/paged-bin/src/';
const sha=data=>createHash('sha256').update(data).digest('hex');
for(const [path,digest] of [
 [source+'/../evidence.json','f72d2238205512c5e88a9d5cc8290884551099ae9d939e8ff33237546ab5e02d'],
 [bin+'walletd','630a033e0b41ebb01d666886948bd9a4affa4c44a299474bc125c3284afc15d1'],
 [bin+'discreted','fb9408fb76ab54eebd7016c8d997ad9ece39399b4851e8308e86e6fc3725cfb5'],
 [root+'/gui-v0.9.8/wallet.AppImage','f90ddac3b033492c878623f6608095363314640e95039fa3d168b4d2327f72cf'],
]) assert.equal(sha(await readFile(path)),digest,'immutable fixture prerequisite');
await mkdir(pay+'/build/gui-qualification',{recursive:true});
const dir=await mkdtemp(pay+'/build/gui-qualification/run-'),state=dir+'/state',profile=dir+'/gui-profile';
await cp(source,state,{recursive:true,force:false,errorOnExist:true});await mkdir(profile,{mode:0o700});
const rewrite=s=>s.replaceAll(root+'/pay-paged-tail/build/native-test/paged/run-NFdcs1',state).replaceAll(pay+'/build/native-load/run-mku6hq/state',state).replaceAll(source,state);
const h=JSON.parse(rewrite(await readFile(state+'/service-handoff.json','utf8')));
const {DiscretePayStore}=await import(pay+'/dist/src/persistence/store.js');
const {startPublicWebRuntime}=await import(pay+'/dist/apps/public-web/src/runtime.js');
const {startFacadeRuntime}=await import(pay+'/dist/services/walletd-facade/src/runtime.js');
const {startGatewayRuntime}=await import(pay+'/dist/apps/gateway-api/src/runtime.js');
const {openWorkerRuntime}=await import(pay+'/dist/apps/worker/src/runtime.js');
const {cert,key}=await import(pay+'/test/worker-runtime/tls-fixture.ts');
const children=new Set(),receipts=[],checks=[];let worker,facade,gateway,web,receiver,control,store,mining=false,invoice;
const token=randomBytes(32).toString('hex');
const record=(check,value=true)=>{checks.push({check,value});console.log(check,JSON.stringify(value));};
function launch(exe,args,extra={}){const c=spawn(exe,args,{cwd:dir,stdio:'ignore',...extra});children.add(c);c.once('exit',()=>children.delete(c));return c;}
async function until(label,fn,ms=90000){const end=Date.now()+ms;while(Date.now()<end){try{const v=await fn();if(v)return v;}catch{}await delay(300);}throw new Error('timeout '+label);}
async function rpc(p,method,params={},auth=false,path='/json_rpc'){
 const r=await fetch('http://127.0.0.1:'+p+path,{method:'POST',headers:{'content-type':'application/json',...(auth?{authorization:'Basic '+Buffer.from(h.rpcUser+':'+h.rpcPassword).toString('base64')}:{})},body:JSON.stringify(path==='/json_rpc'?{jsonrpc:'2.0',id:1,method,params}:params),signal:AbortSignal.timeout(15000)});
 assert.equal(r.status,200);const b=await r.json();assert(!b.error,'RPC '+method+' rejected');return path==='/json_rpc'?b.result:b;
}
const na=18901,wp=18902,sp=18903,mp=18904;
const height=async()=>(await rpc(na,'getlastblockheader')).block_header.height;
async function wallet(name,p){const conf=rewrite(await readFile(state+'/'+name+'.conf','utf8')).replace(/^bind-port=.*$/m,'bind-port='+p).replace(/^daemon-port=.*$/m,'daemon-port='+na);const f=state+'/gui-'+name+'.conf';await writeFile(f,conf,{mode:0o600});return launch(bin+'walletd',['--config',f,'--testnet']);}
let spendKey;
async function mine(blocks){assert(Number.isInteger(blocks)&&blocks>=1&&blocks<=12);const before=await height();await rpc(na,'start_mining',{miner_spend_key:spendKey,miner_view_key:'',threads_count:1},false,'/start_mining');mining=true;try{await until('bounded mining',async()=>await height()>=before+blocks);}finally{await rpc(na,'stop_mining',{},false,'/stop_mining');mining=false;}return height();}
let stopped;const done=new Promise(r=>{stopped=r;});process.once('SIGTERM',stopped);process.once('SIGINT',stopped);
try{
 for(const [name,p,peer,r]of [['node-a',18905,18906,na],['node-c',18906,18905,18907]])launch(bin+'discreted',['--testnet','--data-dir',state+'/'+name,'--no-console','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(r),'--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p),'--add-exclusive-node','127.0.0.1:'+peer,'--allow-local-ip','--hide-my-port','--log-file',state+'/'+name+'-gui.log']);
 await until('node',()=>rpc(na,'getlastblockheader'));await wallet('merchant-tracking',wp);await wallet('miner-sender',sp);await wallet('merchant-setup',mp);
 await until('tracking',async()=>{const s=await rpc(wp,'getDepositScheme',{},true);return s.tracking===true&&s.depositCount===10001;});
 await until('setup',async()=>(await rpc(mp,'getBalance',{},true)).scannedHeight>=await height());
 spendKey=(await rpc(mp,'getSpendKeys',{address:(await rpc(mp,'getAddresses',{},true)).addresses[0]},true)).spendSecretKey;
 facade=await startFacadeRuntime({...h.facadeEnv,DISCRETE_PAY_FACADE_REGISTRY_MODE:'paged-v1',DISCRETE_PAY_FACADE_LISTEN_PORT:'18908',DISCRETE_PAY_WALLETD_ENDPOINT:'http://127.0.0.1:'+wp+'/json_rpc'});
 gateway=await startGatewayRuntime({...h.gatewayEnv,DISCRETE_PAY_GATEWAY_LISTEN_PORT:'18909',DISCRETE_PAY_GATEWAY_FACADE_ENDPOINT:'http://127.0.0.1:18908/v1/deposits'});
 web=await startPublicWebRuntime({...h.publicEnv,DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT:'18910'});
 store=new DiscretePayStore(h.gatewayEnv.DISCRETE_PAY_GATEWAY_DATABASE_PATH);
 receiver=tlsServer({cert,key},async(req,res)=>{try{const chunks=[];for await(const c of req)chunks.push(c);const body=Buffer.concat(chunks),hd=req.headers,digest=createHash('sha256').update(body).digest('hex'),expected=createHmac('sha256',Buffer.from(h.receiver.secret,'hex')).update(`v1\n${hd['x-discrete-pay-timestamp-ms']}\n${hd['x-discrete-pay-delivery-id']}\n${hd['x-discrete-pay-event-id']}\n${digest}\n`).update(body).digest('hex');assert.equal(hd['x-discrete-pay-signature'],'v1='+expected);receipts.push({digest,payload:JSON.parse(body),valid:true});res.writeHead(204).end();}catch{res.writeHead(400).end();}});receiver.listen(h.receiver.port,'127.0.0.1');await once(receiver,'listening');
 const cfg=JSON.parse(rewrite(await readFile(state+'/worker.json','utf8')));cfg.walletEndpoint='http://127.0.0.1:'+wp+'/json_rpc';cfg.nodeEndpoint='http://127.0.0.1:'+na+'/json_rpc';await writeFile(state+'/gui-worker.json',JSON.stringify(cfg),{mode:0o600});
 worker=await openWorkerRuntime({DISCRETE_PAY_WORKER_ENABLED:'true',DISCRETE_PAY_WORKER_CONFIG_PATH:state+'/gui-worker.json'});
 // Manual control serializes scans; no overlapping background scans.
 await writeFile(profile+'/Discretewallet.cfg',JSON.stringify({connectionMode:'local',daemonPort:na,remoteNodes:[]}),{mode:0o600});
 launch('/usr/bin/Xvfb',[':99','-screen','0','1280x900x24','-nolisten','tcp']);await delay(1200);
 launch('/usr/bin/x11vnc',['-display',':99','-rfbport','5901','-localhost','-nopw','-forever','-shared']);
 launch('/usr/bin/websockify',['--web','/usr/share/novnc','127.0.0.1:18891','127.0.0.1:5901']);
 const app=root+'/gui-v0.9.8/squashfs-root';
 const gui=launch(app+'/usr/bin/DiscreteWallet',['--testnet','--data-dir',profile],{env:{...process.env,HOME:profile,XDG_CONFIG_HOME:profile,XDG_CACHE_HOME:profile,DISPLAY:':99',LD_LIBRARY_PATH:app+'/usr/lib',QT_PLUGIN_PATH:app+'/usr/plugins',QT_QPA_PLATFORM_PLUGIN_PATH:app+'/usr/plugins/platforms'}});
 await delay(2000);assert.equal(gui.exitCode,null,'GUI exited');
 let busy=false,funded=false;
 control=createServer(async(req,res)=>{if(req.headers.authorization!=='Bearer '+token){res.writeHead(401).end();return;}if(busy){res.writeHead(409).end();return;}busy=true;try{let body='';for await(const c of req){body+=c;assert(body.length<16384);}const input=body?JSON.parse(body):{};let out;
  if(req.url==='/status'){out={height:await height(),guiRunning:gui.exitCode===null,profile,invoice:invoice?JSON.parse(JSON.stringify(store.getInvoiceById(invoice.id),(_,v)=>typeof v==='bigint'?v.toString():v)):null,receipts:receipts.filter(x=>x.payload.invoice_id===invoice?.id)};}
  else if(req.url==='/invoice'){assert(!invoice);const r=await fetch('http://127.0.0.1:18909/v1/invoices',{method:'POST',headers:{authorization:'Bearer '+h.merchantToken,'content-type':'application/json','idempotency-key':'ordinary-gui-wallet-qualification'},body:JSON.stringify({amount_atomic:'10',expires_in_seconds:3600,required_confirmations:2})});assert.equal(r.status,201);invoice=(await r.json()).invoice;const saved=store.getInvoiceById(invoice.id);out={id:saved.id,address:saved.depositAccount,amountAtomic:'10',routingT:saved.depositT};record('ordinary GUI invoice created',out);}
  else if(req.url==='/fund'){assert(!funded);assert(typeof input.address==='string'&&input.address.length>100);funded=true;const tx=await rpc(mp,'sendTransaction',{transfers:[{address:input.address,amount:1000}],fee:1,unlockHeight:0},true);record('disposable GUI funding submitted once',{transactionHash:tx.transactionHash,amountAtomic:'1000'});await mine(12);out={transactionHash:tx.transactionHash,height:await height()};}
  else if(req.url==='/mine'){out={height:await mine(input.blocks)};}
  else if(req.url==='/scan'){const scan=await worker.scanOnce();const delivered=[];for(let i=0;i<50;i++){const d=await worker.deliverOnce();delivered.push(d.kind);if(d.kind==='idle')break;}out={scan,delivered};}
  else {res.writeHead(404).end();return;}res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify(out,(_,v)=>typeof v==='bigint'?v.toString():v));
 }catch(e){res.writeHead(500).end(JSON.stringify({error:e.message}));}finally{busy=false;}});control.listen(18911,'127.0.0.1');await once(control,'listening');
 await writeFile(root+'/gui-v0.9.8/session-private.json',JSON.stringify({dir,token,controlPort:18911}),{mode:0o600});record('GUI session ready',{dir,profile,nodePort:na,webPort:18891});await done;
}catch(e){record('fixture failure',e.message);process.exitCode=1;}
finally{if(mining)await rpc(na,'stop_mining',{},false,'/stop_mining').catch(()=>{});await worker?.close();await gateway?.close();await facade?.close();await web?.close();control?.close();receiver?.close();store?.close();for(const c of children)c.kill('SIGTERM');await Promise.allSettled([...children].map(c=>once(c,'exit')));await writeFile(dir+'/evidence.json',JSON.stringify({checks,receipts,scope:'isolated GUI fixture; only recorded interactions prove acceptance'},null,2),{mode:0o600});}
