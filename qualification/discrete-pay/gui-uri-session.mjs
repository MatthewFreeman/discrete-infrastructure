// Browser -> native wallet URI preview only, on copies of the paid GUI fixture.
// No funding, mining, signing or payment submission is performed by this helper.
import assert from 'node:assert/strict';
import {mkdtemp,cp,mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawn,execFileSync} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {stopChild} from './bounded-child.mjs';
assert.equal(process.env.DISCRETE_PAY_GUI_URI,'copied-private-preview-only');
const root='/opt/discrete-pay-qualification',pay=root+'/pay-merged-4d2f069';
const source=pay+'/build/gui-qualification/run-8Gqvfk',image=root+'/gui-v0.9.8/wallet.AppImage';
const sha=data=>createHash('sha256').update(data).digest('hex');
assert.equal(sha(await readFile(image)),'f90ddac3b033492c878623f6608095363314640e95039fa3d168b4d2327f72cf');
const dir=await mkdtemp(root+'/gui-uri-'),profile=dir+'/profile';
await cp(source+'/gui-profile',profile,{recursive:true,errorOnExist:true});
await mkdir(dir+'/state');await cp(source+'/state/node-a',dir+'/state/node-a',{recursive:true,errorOnExist:true});await cp(source+'/state/node-c',dir+'/state/node-c',{recursive:true,errorOnExist:true});
await cp(source+'/state/gateway.sqlite3',dir+'/state/gateway.sqlite3',{errorOnExist:true});
execFileSync(image,['--appimage-extract'],{cwd:dir,stdio:'ignore',timeout:30000});
const app=dir+'/squashfs-root',native=root+'/pay-paged-tail/build/native-test/paged-bin/src/discreted';
assert.equal(sha(await readFile(native)),'fb9408fb76ab54eebd7016c8d997ad9ece39399b4851e8308e86e6fc3725cfb5');
const cfg=JSON.parse(await readFile(profile+'/Discretewallet.cfg','utf8'));
cfg.walletFile=profile+'/gui.wallet';cfg.connectionMode='local';cfg.daemonPort=18971;cfg.remoteNodes=[];
await writeFile(profile+'/Discretewallet.cfg',JSON.stringify(cfg),{mode:0o600});
const {DiscretePayStore}=await import(pay+'/dist/src/persistence/store.js');
const {startPublicWebRuntime}=await import(pay+'/dist/apps/public-web/src/runtime.js');
const store=new DiscretePayStore(dir+'/state/gateway.sqlite3');
const invoice=store.getInvoiceById('inv_95608cfeff3b4e61913b0dc769e6fe48');
assert(invoice&&invoice.depositAccount==='28-1-GHT6-10002-T'&&invoice.amountAtomic===10n&&invoice.confirmedAtomic===10n);store.close();
const publicEnv={DISCRETE_PAY_PUBLIC_WEB_ENABLED:'true',DISCRETE_PAY_PUBLIC_WEB_DATABASE_PATH:dir+'/state/gateway.sqlite3',DISCRETE_PAY_PUBLIC_WEB_LISTEN_PORT:'18978',DISCRETE_PAY_PUBLIC_WEB_BRIDGE_BASE_URL:'https://discrete.cash/pay/#'};
const url='http://127.0.0.1:18978/pay/'+invoice.publicToken;
const environment={...process.env,HOME:profile,XDG_CONFIG_HOME:profile+'/config',XDG_DATA_HOME:profile+'/data',XDG_CACHE_HOME:profile+'/cache',DISPLAY:':101'};
for(const p of [environment.XDG_CONFIG_HOME,environment.XDG_DATA_HOME+'/applications',environment.XDG_CACHE_HOME,dir+'/browser'])await mkdir(p,{recursive:true,mode:0o700});
const walletEnvironment={...environment,LD_LIBRARY_PATH:app+'/usr/lib',QT_PLUGIN_PATH:app+'/usr/plugins',QT_QPA_PLATFORM_PLUGIN_PATH:app+'/usr/plugins/platforms'};
const desktop=(await readFile(app+'/discretewallet.desktop','utf8')).replace(/^Exec=.*$/m,`Exec=env LD_LIBRARY_PATH=${app}/usr/lib QT_PLUGIN_PATH=${app}/usr/plugins QT_QPA_PLATFORM_PLUGIN_PATH=${app}/usr/plugins/platforms ${app}/usr/bin/DiscreteWallet --testnet --data-dir ${profile} %U`);
await writeFile(environment.XDG_DATA_HOME+'/applications/discretewallet-test.desktop',desktop,{mode:0o600});
execFileSync('/usr/bin/xdg-mime',['default','discretewallet-test.desktop','x-scheme-handler/discrete'],{env:environment,stdio:'ignore',timeout:10000});
assert.equal(execFileSync('/usr/bin/xdg-mime',['query','default','x-scheme-handler/discrete'],{env:environment,encoding:'utf8',timeout:10000}).trim(),'discretewallet-test.desktop');
const children=new Set();let web;let done;const wait=new Promise(r=>{done=r;});process.once('SIGTERM',done);process.once('SIGINT',done);
function launch(exe,args,env=environment){const c=spawn(exe,args,{cwd:dir,env,stdio:'ignore'});children.add(c);c.once('exit',()=>children.delete(c));return c;}
async function ready(){for(let i=0;i<100;i++){try{const r=await fetch('http://127.0.0.1:18971/json_rpc',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'getlastblockheader',params:{}}),signal:AbortSignal.timeout(1000)});if((await r.json()).result?.status==='OK')return;}catch{}await delay(200);}throw new Error('copied node startup failed');}
try{
 for(const [name,r,p,peer]of [['node-a',18971,18972,18974],['node-c',18973,18974,18972]])launch(native,['--testnet','--data-dir',dir+'/state/'+name,'--no-console','--rpc-bind-ip','127.0.0.1','--rpc-bind-port',String(r),'--p2p-bind-ip','127.0.0.1','--p2p-bind-port',String(p),'--add-exclusive-node','127.0.0.1:'+peer,'--allow-local-ip','--hide-my-port','--log-file',dir+'/'+name+'.log']);
 await ready();web=await startPublicWebRuntime(publicEnv);assert.equal((await fetch(url)).status,200);
 launch('/usr/bin/Xvfb',[':101','-screen','0','1280x900x24','-nolisten','tcp']);await delay(1000);
 launch('/usr/bin/x11vnc',['-display',':101','-rfbport','5901','-localhost','-nopw','-forever','-shared']);
 launch('/usr/bin/websockify',['--web','/usr/share/novnc','127.0.0.1:18891','127.0.0.1:5901']);
 const wallet=launch(app+'/usr/bin/DiscreteWallet',['--testnet','--data-dir',profile],walletEnvironment);await delay(5000);assert.equal(wallet.exitCode,null);
 const browser=launch('/usr/bin/firefox-esr',['--no-remote','--profile',dir+'/browser','--new-window',url]);await delay(3000);assert.equal(browser.exitCode,null);
 await writeFile(dir+'/preview.json',JSON.stringify({scope:'copied GUI/browser URI preview; not a payment',guiSourceTag:'55a582db54d329fc9988bd88209129d2c8ac0a0b',url,expectedAddress:invoice.depositAccount,expectedAmount:'0.10',registration:'temporary XDG profile, original %U route with isolated testnet data directory',dir},null,2),{mode:0o600});
 console.log('GUI_URI_READY '+dir);await wait;
}finally{await web?.close();const cleanup=await Promise.allSettled([...children].map(c=>stopChild(c,3000)));await writeFile(dir+'/cleanup.json',JSON.stringify(cleanup),{mode:0o600});console.log('GUI_URI_STOPPED '+dir);}
