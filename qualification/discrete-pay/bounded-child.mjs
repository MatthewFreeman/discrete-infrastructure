import {once} from 'node:events';

// Owned disposable fixture processes only. Record forced termination explicitly.
export async function stopChild(child,graceMs=5000) {
 if(child.exitCode!==null||child.signalCode!==null)return {forced:false,alreadyExited:true};
 let forced=false;
 const exited=once(child,'exit');
 const timer=setTimeout(()=>{forced=true;child.kill('SIGKILL');},graceMs);
 try{child.kill('SIGTERM');await exited;return {forced,alreadyExited:false};}
 finally{clearTimeout(timer);}
}
