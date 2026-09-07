// Disposable qualification services only, never a production service launcher.
import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';
import {existsSync, createWriteStream} from 'node:fs';
import {spawn} from 'node:child_process';
import {createServer} from 'node:https';
import {createHash, createHmac} from 'node:crypto';
import {join} from 'node:path';
const pay='/opt/discrete-pay-qualification/pay';
const [file,role]=process.argv.slice(2);
assert(file.startsWith(pay+'/build/native-test/run-') && file.endsWith('/service-handoff.json'));
const h=JSON.parse(await readFile(file,'utf8'));
assert.equal(file,join(h.dir,'service-handoff.json'));
if(role==='receiver') {
  const {cert,key}=await import(pay+'/test/worker-runtime/tls-fixture.ts');
  const receipt=join(h.dir,'service-receipts.json');
  const rows=existsSync(receipt)?JSON.parse(await readFile(receipt,'utf8')):[];
  let queue=Promise.resolve();
  const server=createServer({cert,key},async(req,res)=>{
    try {
      assert(req.method==='POST' && req.url==='/webhook');
      const chunks=[];let size=0;
      for await(const c of req){size+=c.length;assert(size<=65536);chunks.push(c);}
      const body=Buffer.concat(chunks), headers=req.headers;
      const id=headers['x-discrete-pay-delivery-id'], event=headers['x-discrete-pay-event-id'];
      const digest=createHash('sha256').update(body).digest('hex');
      const expected=createHmac('sha256',Buffer.from(h.receiver.secret,'hex'))
        .update(`v1\n${headers['x-discrete-pay-timestamp-ms']}\n${id}\n${event}\n${digest}\n`).update(body).digest('hex');
      assert.equal(headers['x-discrete-pay-signature'],'v1='+expected);
      assert.equal(headers['x-discrete-pay-idempotency-key'],id);
      const rejected=existsSync(join(h.dir,'receiver-reject'));
      rows.push({id,event,digest,body:body.toString('base64'),valid:true,rejected,status:JSON.parse(body).status});
      queue=queue.then(()=>writeFile(receipt,JSON.stringify(rows),{mode:0o600}));await queue;
      res.writeHead(rejected?503:204).end();
    } catch {res.writeHead(400).end();}
  });
  server.listen(h.receiver.port,'127.0.0.1');
  process.on('SIGTERM',()=>server.close());
} else {
  const configs={facade:['dist/services/walletd-facade/src/main.js',h.facadeEnv],
    gateway:['dist/apps/gateway-api/src/main.js',h.gatewayEnv],public:['dist/apps/public-web/src/main.js',h.publicEnv],
    worker:['dist/apps/worker/src/main.js',h.workerEnv]};
  const native=h.processes.find(p=>p.name===role);
  assert(configs[role] || native,'unknown fixture role');
  const spec=configs[role];
  if(native) assert(native.executable.startsWith(pay+'/build/native-test/bin/src/'));
  const log=createWriteStream(join(h.dir,'service-'+role+'.log'),{flags:'a',mode:0o600});
  const child=spawn(spec?process.execPath:native.executable,spec?[join(pay,spec[0])]:native.args,
    {cwd:pay,env:{...process.env,...(spec?spec[1]:{})},stdio:['ignore','pipe','pipe']});
  child.stdout.pipe(log);child.stderr.pipe(log,{end:false});
  if(role==='worker') child.stderr.pipe(process.stderr);
  process.on('SIGTERM',()=>child.kill('SIGTERM'));
  child.on('exit',(code,signal)=>{log.end();process.exitCode=signal?1:code;});
  child.on('error',()=>{log.end();process.exitCode=1;});
}
