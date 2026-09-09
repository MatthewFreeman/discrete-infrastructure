import {mkdtemp,cp,readFile,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';
import {stopChild} from './bounded-child.mjs';
const root='/opt/discrete-pay-qualification';
const source=root+'/pay-merged-4d2f069/build/gui-qualification/run-8Gqvfk/gui-profile';
const dir=await mkdtemp(root+'/gui-v0.9.8/stop-check-');
await cp(source,dir+'/profile',{recursive:true,errorOnExist:true});
const cfg=JSON.parse(await readFile(dir+'/profile/Discretewallet.cfg','utf8'));
cfg.walletFile=dir+'/profile/gui.wallet';
await writeFile(dir+'/profile/Discretewallet.cfg',JSON.stringify(cfg),{mode:0o600});
const xvfb=spawn('/usr/bin/Xvfb',[':100','-screen','0','1280x900x24','-nolisten','tcp'],{stdio:'ignore'});let gui;
try{await delay(1000);const app=root+'/gui-v0.9.8/squashfs-root';
gui=spawn(app+'/usr/bin/DiscreteWallet',['--testnet','--data-dir',dir+'/profile'],{stdio:'ignore',env:{...process.env,HOME:dir+'/profile',XDG_CONFIG_HOME:dir+'/profile',XDG_CACHE_HOME:dir+'/profile',DISPLAY:':100',LD_LIBRARY_PATH:app+'/usr/lib',QT_PLUGIN_PATH:app+'/usr/plugins',QT_QPA_PLATFORM_PLUGIN_PATH:app+'/usr/plugins/platforms'}});
await delay(4000);assert.equal(gui.exitCode,null);const start=Date.now();const stopped=await stopChild(gui,3000);const elapsedMs=Date.now()-start;assert(elapsedMs<10000);
const result={result:'PASS',scope:'real released GUI process bounded termination on a copied post-payment wallet profile; not GUI-visible reopen acceptance',...stopped,elapsedMs};await writeFile(dir+'/evidence.json',JSON.stringify(result,null,2),{mode:0o600});console.log(JSON.stringify(result));console.log('Evidence:',dir+'/evidence.json');
}finally{if(gui)await stopChild(gui,1000);await stopChild(xvfb,1000);}
