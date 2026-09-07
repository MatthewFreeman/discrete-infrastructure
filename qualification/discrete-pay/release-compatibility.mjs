// Official binary compatibility check: isolated, no mining, registration or payment.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {randomBytes,createHash} from 'node:crypto';
import {mkdtemp,writeFile,readFile,mkdir} from 'node:fs/promises';
import {createWriteStream} from 'node:fs';
import {join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
const root='/opt/discrete-pay-qualification';
const pay=root+'/pay',bin=root+'/release-v0.9.10';
assert.equal(process.env.DISCRETE_PAY_RELEASE_CHECK,'isolated-official-v0.9.10');
const {parseWalletAttestation}=await import(pay+'/dist/services/walletd-facade/src/contracts.js');
const {startFacadeRuntime}=await import(pay+'/dist/services/walletd-facade/src/runtime.js');
const {DiscreteScannerRpc}=await import(pay+'/dist/apps/worker/src/discrete-rpc.js');
const {ReadRpcClient}=await import(pay+'/dist/apps/worker/src/rpc-client.js');
const dir=await mkdtemp(root+'/release-compat-run-');
const password=randomBytes(32).toString('hex'),user='release-qualification';
const children=new Set();
const result={release:'v.0.9.10',coreCommit:'3e8ef0bad719c6ac6304674f76df52cc5aecbea7',
  archiveSha256:'1cb78a160963c0f69c92a8718c2dbd5da7cbfccb0a693f1ed68f52632408d04c',
  scope:'fresh disposable wallets and loopback native node; no funds or public peers',checks:[]};
const record=(name,value=true)=>{result.checks.push({name,value});console.log(name,JSON.stringify(value));};
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
async function until(fn){const end=Date.now()+90000;while(Date.now()<end){try{if(await fn())return;}catch{}await delay(500);}throw new Error('bounded official release startup timed out');}
function launch(name,exe,args){const log=createWriteStream(join(dir,name+'.log'),{mode:0o600});const c=spawn(join(bin,exe),args,{cwd:dir,stdio:['ignore','pipe','pipe']});children.add(c);c.stdout.pipe(log);c.stderr.pipe(log,{end:false});c.on('exit',()=>{children.delete(c);log.end();});return c;}
async function rpc(p,method,params={},wallet=true){const response=await fetch('http://127.0.0.1:'+p+'/json_rpc',{method:'POST',headers:{'content-type':'application/json',...(wallet?{authorization:'Basic '+Buffer.from(user+':'+password).toString('base64')}:{})},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params}),signal:AbortSignal.timeout(5000)});assert.equal(response.status,200);const body=await response.json();if(body.error)throw new Error('RPC rejected '+method+' code '+body.error.code);return body.result;}
async function wallet(name,p,node,tracking){const config=join(dir,name+'.conf');const base=`container-file=${dir}/${name}.wallet\ncontainer-password=${password}\nbind-address=127.0.0.1\nbind-port=${p}\nrpc-user=${user}\nrpc-password=${password}\ndaemon-address=127.0.0.1\ndaemon-port=${node}\nlog-level=1\nlog-file=${dir}/${name}-internal.log\n`;await writeFile(config,base+'generate-container=\nsingle-key-index=\n'+(tracking?'view-key='+tracking+'\n':''),{mode:0o600});const c=launch(name+'-generate','walletd',['--config',config,'--testnet','--generate-container','--single-key-index']);assert.equal((await once(c,'exit'))[0],0,'fresh release wallet generation');await writeFile(config,base,{mode:0o600});launch(name,'walletd',['--config',config,'--testnet']);await until(()=>rpc(p,'getStatus'));}
try {
  for(const name of ['discreted','walletd'])result[name+'Sha256']=createHash('sha256').update(await readFile(join(bin,name))).digest('hex');
  const [node,p2p,unused,spendPort,viewPort,facadePort]=await Promise.all(Array.from({length:6},port));
  await mkdir(join(dir,'node'));
  launch('node','discreted',['--testnet','--data-dir',join(dir,'node'),'--no-console','--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p2p),'--add-exclusive-node','127.0.0.1:'+unused,'--allow-local-ip','--hide-my-port','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(node),'--log-level','0','--log-file',join(dir,'node-internal.log')]);
  await until(()=>rpc(node,'getlastblockheader',{},false));
  await wallet('spending-empty',spendPort,node);
  const scheme=await rpc(spendPort,'getDepositScheme');
  record('official spending-wallet getDepositScheme fields',Object.keys(scheme).sort());
  const tracking=(await rpc(spendPort,'getTrackingKey')).trackingKey;
  assert.equal(typeof tracking,'string');assert(tracking.startsWith('pqview1:'));
  await wallet('view-only-empty',viewPort,node,tracking);
  const viewScheme=await rpc(viewPort,'getDepositScheme');
  const account=await rpc(viewPort,'getAccountStatus');
  record('official view-only-wallet getDepositScheme fields',Object.keys(viewScheme).sort());
  assert.equal(viewScheme.scheme,'single-key-index');
  assert.equal(Object.hasOwn(viewScheme,'tracking'),false);
  assert.throws(()=>parseWalletAttestation(viewScheme,account),{code:'invalid_response'});
  record('Pay exact attestation parser rejects official view-only response without tracking');
  await assert.rejects(()=>startFacadeRuntime({DISCRETE_PAY_FACADE_ENABLED:'true',DISCRETE_PAY_FACADE_LISTEN_HOST:'127.0.0.1',DISCRETE_PAY_FACADE_LISTEN_PORT:String(facadePort),DISCRETE_PAY_FACADE_JOURNAL_PATH:join(dir,'facade.sqlite3'),DISCRETE_PAY_FACADE_BEARER_TOKEN:randomBytes(32).toString('hex'),DISCRETE_PAY_WALLETD_ENDPOINT:'http://127.0.0.1:'+viewPort+'/json_rpc',DISCRETE_PAY_WALLETD_USERNAME:user,DISCRETE_PAY_WALLETD_PASSWORD:password}),{code:'invalid_response'});
  record('Pay facade startup fails closed with official view-only walletd');
  const genesis=(await rpc(node,'getblockheaderbyheight',{height:0},false)).block_header.hash;
  const scanner=new DiscreteScannerRpc({wallet:new ReadRpcClient('http://127.0.0.1:'+viewPort+'/json_rpc',{username:user,password}),node:new ReadRpcClient('http://127.0.0.1:'+node+'/json_rpc'),accountNumber:'1-1-0000-0',genesisHash:genesis,network:'testnet',invoices:()=>[]});
  await assert.rejects(()=>scanner.getTip(),{code:'invalid_response'});
  record('Pay scanner refuses official view-only wallet before checkpoint');
  result.result='INCOMPATIBLE_CONFIRMED';
}catch(error){result.result='CHECK_FAILED';result.error=error.message;process.exitCode=1;console.error(error.message);}
finally {
  await Promise.all([...children].map(async c=>{const done=once(c,'exit');c.kill('SIGTERM');await done;}));
  await writeFile(join(dir,'evidence.json'),JSON.stringify(result,null,2),{mode:0o600});
  console.log('Secret-free release compatibility evidence:',join(dir,'evidence.json'));
}
