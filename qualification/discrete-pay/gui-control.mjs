import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const h=JSON.parse(await readFile('/opt/discrete-pay-qualification/gui-v0.9.8/session-private.json','utf8'));
const action=process.argv[2];assert(['status','invoice','fund','mine','scan'].includes(action));
const input=action==='fund'?{address:process.argv[3]}:action==='mine'?{blocks:Number(process.argv[3])}:{};
const r=await fetch('http://127.0.0.1:'+h.controlPort+'/'+action,{method:'POST',headers:{authorization:'Bearer '+h.token,'content-type':'application/json'},body:JSON.stringify(input),signal:AbortSignal.timeout(120000)});
const data=await r.json();assert.equal(r.status,200,JSON.stringify(data));
if(action==='status') console.log(JSON.stringify({dir:h.dir,height:data.height,guiRunning:data.guiRunning,invoice:data.invoice?{id:data.invoice.id,status:data.invoice.status,routingT:data.invoice.depositT,confirmedAtomic:data.invoice.confirmedAtomic}:null,receiptCount:data.receipts.length}));
else console.log(JSON.stringify(data));
