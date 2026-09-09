import assert from 'node:assert/strict';
import test from 'node:test';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {stopChild} from './bounded-child.mjs';

const child=async(code)=>{const c=spawn(process.execPath,['-e',code],{stdio:['ignore','pipe','ignore']});await once(c.stdout,'data');return c;};
test('normally terminates a fixture child',async()=>{
 const c=await child('console.log("ready");setInterval(()=>{},1000)');
 assert.deepEqual(await stopChild(c),{forced:false,alreadyExited:false});
 assert.deepEqual(await stopChild(c),{forced:false,alreadyExited:true});
});
test('forces an owned child that ignores SIGTERM within the bound',{skip:process.platform==='win32'},async()=>{
 const c=await child('process.on("SIGTERM",()=>{});console.log("ready");setInterval(()=>{},1000)');
 const start=Date.now();assert.equal((await stopChild(c,150)).forced,true);
 assert.equal(c.signalCode,'SIGKILL');assert(Date.now()-start<3000);
});
