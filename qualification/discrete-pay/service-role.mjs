// Disposable qualification services only, never a production service launcher.
import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';
import {existsSync, createWriteStream} from 'node:fs';
import {spawn} from 'node:child_process';
import {createServer} from 'node:https';
import {createHash, createHmac} from 'node:crypto';
import {join} from 'node:path';
const paged=process.env.DISCRETE_PAY_QUALIFICATION_MODE==='paged';
assert([undefined,'paged'].includes(process.env.DISCRETE_PAY_QUALIFICATION_MODE));
const pay='/opt/discrete-pay-qualification/'+(paged?'pay-merged-4d2f069':'pay');
const [file,role]=process.argv.slice(2);
assert((paged?file.startsWith(pay+'/build/native-ops/run-'):(file.startsWith(pay+'/build/native-test/run-') || file.startsWith(pay+'/build/native-test/current/run-'))) && file.endsWith('/service-handoff.json'));
const h=JSON.parse(await readFile(file,'utf8'));
assert.equal(file,join(h.dir,'service-handoff.json'));
if(role==='edge') {
  const {cert,key}=await import(pay+'/test/worker-runtime/tls-fixture.ts');
  await writeFile(join(h.dir,'edge-cert.pem'),cert,{mode:0o600});
  await writeFile(join(h.dir,'edge-key.pem'),key,{mode:0o600});
  const config=`pid ${h.dir}/edge.pid;
error_log /dev/null crit;
events { worker_connections 128; }
http {
 access_log off;
 client_body_temp_path ${h.dir}/edge-body;
 proxy_temp_path ${h.dir}/edge-proxy;
 fastcgi_temp_path ${h.dir}/edge-fastcgi;
 uwsgi_temp_path ${h.dir}/edge-uwsgi;
 scgi_temp_path ${h.dir}/edge-scgi;
 limit_req_zone $binary_remote_addr zone=payqual:1m rate=5r/s;
 server {
  listen 127.0.0.1:18443 ssl;
  server_name merchant.test;
  ssl_certificate ${h.dir}/edge-cert.pem;
  ssl_certificate_key ${h.dir}/edge-key.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  client_max_body_size 16k;
  client_body_timeout 5s;
  client_header_timeout 5s;
  limit_req zone=payqual burst=10 nodelay;
  limit_req_status 429;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header Host $host;
  proxy_connect_timeout 5s;
  proxy_read_timeout 10s;
  location /pay/ { proxy_pass http://127.0.0.1:${h.publicEnv.DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT}; }
  location /v1/public/ { proxy_pass http://127.0.0.1:${h.publicEnv.DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT}; }
  location /v1/invoices { proxy_pass http://127.0.0.1:${h.gatewayEnv.DISCRETE_PAY_GATEWAY_LISTEN_PORT}; }
  location / { return 404; }
 }
}`;
  const configFile=join(h.dir,'edge-nginx.conf');await writeFile(configFile,config,{mode:0o600});
  const child=spawn('/usr/sbin/nginx',['-p',h.dir+'/', '-c',configFile,'-g','daemon off;'],{stdio:'ignore'});
  process.on('SIGTERM',()=>child.kill('SIGQUIT'));
  child.on('exit',code=>{process.exitCode=code??1;});
  child.on('error',()=>{process.exitCode=1;});
} else if(role==='receiver') {
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
  if(native) {
    const binaries=paged?'paged-bin':file.startsWith(pay+'/build/native-test/current/run-')?'current-bin':'bin';
    assert([join(pay,'build/native-test',binaries,'src/discreted'),join(pay,'build/native-test',binaries,'src/walletd')].includes(native.executable));
  }
  const log=createWriteStream(join(h.dir,'service-'+role+'.log'),{flags:'a',mode:0o600});
  const child=spawn(spec?process.execPath:native.executable,spec?[join(pay,spec[0])]:native.args,
    {cwd:pay,env:{...process.env,...(spec?spec[1]:{})},stdio:['ignore','pipe','pipe']});
  child.stdout.pipe(log);child.stderr.pipe(log,{end:false});
  if(role==='worker') child.stderr.pipe(process.stderr);
  let stopping=false;
  process.on('SIGTERM',()=>{stopping=true;child.kill('SIGTERM');});
  child.on('exit',(code,signal)=>{log.end();process.exitCode=stopping?0:(signal?1:code);});
  child.on('error',()=>{log.end();process.exitCode=1;});
}
