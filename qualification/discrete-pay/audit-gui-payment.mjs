import {readFile,writeFile} from 'node:fs/promises';
import {DatabaseSync} from 'node:sqlite';
import assert from 'node:assert/strict';
const dir='/opt/discrete-pay-qualification/pay-merged-4d2f069/build/gui-qualification/run-8Gqvfk';
const cfg=JSON.parse(await readFile(dir+'/state/gui-worker.json','utf8'));
const db=new DatabaseSync(cfg.databasePath,{readOnly:true});
const tx='6d83898b5efdfe3208104ac13e028faa03ceddf412a023ae6ab0eacbecff2131';
try {
const rows=db.prepare('SELECT invoice_id,transaction_hash,deposit_account,amount_atomic,block_height,canonical,confirmations FROM payments WHERE transaction_hash=?').all(tx);
assert.equal(rows.length,1);const p=rows[0];assert.equal(p.invoice_id,'inv_95608cfeff3b4e61913b0dc769e6fe48');assert.equal(p.deposit_account,'28-1-GHT6-10002-T');assert.equal(p.amount_atomic,10);assert.equal(p.canonical,1);assert(p.confirmations>=2);
const integrity=db.prepare('PRAGMA integrity_check').all();assert.deepEqual(integrity.map(r=>r.integrity_check),['ok']);assert.equal(db.prepare('PRAGMA foreign_key_check').all().length,0);
const counts=db.prepare('SELECT state,count(*) AS count FROM webhook_deliveries GROUP BY state').all();
const result={result:'PASS',payment:p,integrity:'ok',foreignKeyErrors:0,webhookQueueSnapshot:counts};
await writeFile(dir+'/gui-payment-db-audit.json',JSON.stringify(result,null,2),{mode:0o600});console.log(JSON.stringify(result));
}finally{db.close();}
