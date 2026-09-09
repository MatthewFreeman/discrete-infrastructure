// Test-fixture seeding only. Matches SHA256(JSON.stringify([[T,address], ...])).
// Hash.copy avoids rebuilding every prefix in a 100000-row journal fixture.
import {createHash} from 'node:crypto';
export function* registryPrefixes(entries){
 const state=createHash('sha256').update('[');let count=0;
 for(const entry of entries){
  if(entry.routingT!==count+1||typeof entry.address!=='string')throw new Error('invalid ordered fixture registry');
  yield state.copy().update(']').digest('hex');
  state.update(count?',':'').update(JSON.stringify([entry.routingT,entry.address]));count++;
 }
}
