import assert from 'node:assert/strict';
import {mkdtemp,cp,readFile,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {setTimeout as delay} from 'node:timers/promises';
const root='/opt/discrete-pay-qualification',pay=root+'/pay-paged-tail';
assert.equal(process.env.DISCRETE_PAY_DIAGNOSTIC,'copied-registration');
const source=pay+'/build/native-test/paged/run-efW4Dy';
const dir=(await mkdtemp(root+'/paged-registration-diagnostic-'))+'/state';
await cp(source,dir,{recursive:true,force:false,errorOnExist:true});
const cfg=JSON.parse(await readFile(dir+'/worker.json','utf8'));
const result={scope:'copied failed disposable state; read-only RPC, no mining or sending',checks:[]};
const record=(name,value)=>{result.checks.push({name,value});console.log(name,JSON.stringify(value));};
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
const children=[];
function launch(exe,args){const c=spawn(pay+'/build/native-test/paged-bin/src/'+exe,args,{cwd:dir,stdio:'ignore'});children.push(c);return c;}
async function rpc(p,method,params={},wallet=false){const r=await fetch('http://127.0.0.1:'+p+'/json_rpc',{method:'POST',headers:{'content-type':'application/json',...(wallet?{authorization:'Basic '+Buffer.from(cfg.walletUsername+':'+cfg.walletPassword).toString('base64')}:{})},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params}),signal:AbortSignal.timeout(5000)});return r.json();}
async function until(fn){const end=Date.now()+60000;while(Date.now()<end){try{if(await fn())return;}catch{}await delay(500);}throw new Error('diagnostic startup timeout');}
try {
 const [na,nc,pa,pc,wp]=await Promise.all(Array.from({length:5},port));
 for(const[name,p,peer,r]of[['node-a',pa,pc,na],['node-c',pc,pa,nc]])launch('discreted',['--testnet','--data-dir',dir+'/'+name,'--no-console','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(r),'--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p),'--add-exclusive-node','127.0.0.1:'+peer,'--allow-local-ip','--hide-my-port','--log-file',dir+'/'+name+'.diagnostic.log']);
 await until(async()=>!!(await rpc(na,'getlastblockheader')).result);
 let conf=await readFile(dir+'/miner-sender.conf','utf8');
 conf=conf.replaceAll(source,dir).replace(/^bind-port=.*$/m,'bind-port='+wp).replace(/^daemon-port=.*$/m,'daemon-port='+na).replace(/^log-level=.*$/m,'log-level=4');
 await writeFile(dir+'/diagnostic.conf',conf,{mode:0o600});launch('walletd',['--config',dir+'/diagnostic.conf','--testnet']);
 await until(async()=>!!(await rpc(wp,'getStatus',{},true)).result);await delay(3000);
 const tip=(await rpc(na,'getlastblockheader')).result.block_header.height;
 const status=(await rpc(wp,'getStatus',{},true)).result;
 record('tip and wallet sync',{tip,blockCount:status.blockCount,knownBlockCount:status.knownBlockCount});
 const account=await rpc(wp,'getAccountStatus',{},true);
 record('account publication',{registered:account.result?.registered,rpcCode:account.error?.code,applicationCode:account.error?.data?.application_code});
 const balance=(await rpc(wp,'getBalance',{},true)).result;
 record('payer balance',{available:balance?.availableBalance,locked:balance?.lockedAmount,scannedHeight:balance?.scannedHeight});
 const pool=await rpc(wp,'getUnconfirmedTransactionHashes',{},true);
 record('pending transaction hashes',{hashes:pool.result?.transactionHashes,errorCode:pool.error?.code});
 const logfile=conf.match(/^log-file=(.*)$/m)?.[1];
 if(logfile?.startsWith(dir+'/')){const text=await readFile(logfile.trim(),'utf8');record('publication diagnostic reason',text.split('\n').filter(line=>line.includes('Account number not reported:')).map(line=>line.slice(line.indexOf('Account number not reported:'))));}
 for(let h=48;h<=tip;h++){
   const tx=await rpc(wp,'getTransactions',{firstBlockIndex:h,blockCount:1},true);
   record('transactions at height',{height:h,transactions:tx.result?.items?.flatMap(b=>b.transactions.map(t=>({hash:t.transactionHash,blockIndex:t.blockIndex,fee:t.fee,state:t.state}))),errorCode:tx.error?.code});
 }
 result.result='DIAGNOSTIC_CAPTURED';
}catch(e){result.result='FAIL';result.error=e.message;process.exitCode=1;}
finally{for(const c of children.reverse())if(c.exitCode===null){const done=once(c,'exit');c.kill('SIGTERM');await done;}await writeFile(dir+'/evidence.json',JSON.stringify(result,null,2),{mode:0o600});console.log('Evidence:',dir+'/evidence.json');}
