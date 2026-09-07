// Independent identity read from the unmodified official daemon. No wallet.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'node:net';
import {mkdtemp,readFile,writeFile} from 'node:fs/promises';
import {createWriteStream} from 'node:fs';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
const root='/opt/discrete-pay-qualification';
assert.equal(process.env.DISCRETE_PAY_GENESIS_CHECK,'official-testnet');
const exe=root+'/release-v0.9.10/discreted';
const sha=createHash('sha256').update(await readFile(exe)).digest('hex');
assert.equal(sha,'21766e4ec530d882ddf59f7ec5569de198e08f4774d38668af5a0ffea2e351b5');
async function port(){const s=createServer();s.listen(0,'127.0.0.1');await once(s,'listening');const p=s.address().port;await new Promise(r=>s.close(r));return p;}
const [rpc,p2p,unused]=await Promise.all([port(),port(),port()]);
const dir=await mkdtemp(root+'/official-genesis-');
const log=createWriteStream(dir+'/daemon.log',{mode:0o600});
const child=spawn(exe,['--testnet','--data-dir',dir,'--no-console','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(rpc),'--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p2p),'--add-exclusive-node','127.0.0.1:'+unused,'--allow-local-ip','--hide-my-port','--log-file',dir+'/native.log'],{cwd:dir,stdio:['ignore','pipe','pipe']});
child.stdout.pipe(log);child.stderr.pipe(log,{end:false});
try{
 let header;
 const deadline=Date.now()+60000;
 while(Date.now()<deadline){try{const r=await fetch('http://127.0.0.1:'+rpc+'/json_rpc',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'getblockheaderbyheight',params:{height:0}}),signal:AbortSignal.timeout(3000)});const b=await r.json();header=b.result?.block_header;if(header)break;}catch{}await delay(500);}
 assert(header,'official daemon startup timeout');assert.equal(header.height,0);
 const result={coreCommit:'3e8ef0bad719c6ac6304674f76df52cc5aecbea7',discretedSha256:sha,network:'testnet',height:0,genesisHash:header.hash,result:'OFFICIAL_GENESIS_READ'};
 await writeFile(dir+'/evidence.json',JSON.stringify(result,null,2),{mode:0o600});
 console.log(JSON.stringify(result));console.log('Evidence:',dir+'/evidence.json');
}finally{const exited=once(child,'exit');child.kill('SIGTERM');await exited;log.end();}
