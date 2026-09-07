import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root='/opt/discrete-pay-qualification';
const hash=async p=>createHash('sha256').update(await readFile(p)).digest('hex');
const result={coreCommit:'3e8ef0bad719c6ac6304674f76df52cc5aecbea7',qualification:'private difficulty-1 node; walletd has mode overlay only; not production',patchSha256:await Promise.all([root+'/imports/current-walletd-attestation.patch',root+'/pay/test/worker-runtime/native-core-loopback.patch',root+'/pay/test/worker-runtime/native-core-difficulty.patch'].map(hash))};
for(const bin of ['walletd','discreted'])result[bin+'Sha256']=await hash(root+'/pay/build/native-test/current-bin/src/'+bin);
await writeFile(root+'/pay/build/native-test/current/build-manifest.json',JSON.stringify(result,null,2),{mode:0o600});
console.log(JSON.stringify(result));
