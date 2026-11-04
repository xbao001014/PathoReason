import assert from 'node:assert/strict';
import {createRefreshScheduler} from '../src/refreshScheduler.ts';
const tick=()=>new Promise(r=>setTimeout(r,0));
let releases=[],reads=0,active=0,max=0;
const s=createRefreshScheduler(async()=>{reads++;active++;max=Math.max(max,active);await new Promise(r=>releases.push(r));active--;});
const a=s.request();for(let i=0;i<10;i++)s.poll();assert.equal(reads,1);for(let i=0;i<20;i++)s.request();releases.shift()();await tick();assert.equal(reads,2);assert.equal(max,1);releases.shift()();await a;assert.equal(reads,2);
let failures=0;const e=createRefreshScheduler(async()=>{if(++failures===1)throw Error('offline');});await assert.rejects(e.request(),/offline/);await e.request();assert.equal(failures,2);
const last=s.request();s.request();s.dispose();releases.shift()();await last;assert.equal(reads,3);await s.request();assert.equal(reads,3);
console.log('PASS: serial reads, timer coalescing, queued invalidation, failure recovery, disposal');
