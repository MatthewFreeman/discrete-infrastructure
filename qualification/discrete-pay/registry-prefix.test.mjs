import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createHash} from 'node:crypto';
import {registryPrefixes} from './registry-prefix.mjs';
const reference=entries=>createHash('sha256').update(JSON.stringify(entries.map(({routingT,address})=>[routingT,address]))).digest('hex');
test('all bounded prefixes match existing canonical serialization',()=>{
 const entries=Array.from({length:1000},(_,i)=>({routingT:i+1,address:`test-${i}-\"-\\-\n-ю`}));
 const prefixes=[...registryPrefixes(entries)];assert.equal(prefixes.length,1000);
 for(let i=0;i<1000;i++)assert.equal(prefixes[i],reference(entries.slice(0,i)));
 assert.deepEqual([...registryPrefixes([])],[]);
});
test('100000 prefix fixture remains exact at high boundaries',()=>{
 const entries=Array.from({length:100000},(_,i)=>({routingT:i+1,address:'fixture-'+i}));
 const prefixes=[...registryPrefixes(entries)];assert.equal(prefixes.length,100000);
 for(const i of [0,999,9999,99998,99999])assert.equal(prefixes[i],reference(entries.slice(0,i)));
});
test('unordered or malformed fixture entries are refused',()=>{
 for(const entries of [[{routingT:2,address:'test'}],[{routingT:1,address:null}],[{routingT:1,address:'a'},{routingT:1,address:'b'}]])assert.throws(()=>[...registryPrefixes(entries)]);
});
