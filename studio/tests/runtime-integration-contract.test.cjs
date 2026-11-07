'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const Runtime=require('../shared/runtime.js');
test('creator validation follows the factory slug contract before sending a request',()=>{
  for (const slug of ['UPPER','has.dot','under_score','x'.repeat(42)]) {
    assert.throws(()=>Runtime.createCharacterRequest(slug,'검증 브리프'), /slug/);
  }
  assert.equal(Runtime.createCharacterRequest('a'.repeat(41),'검증 브리프').slug.length,41);
});
test('job identity accepts the actual JobManager response field',()=>{
  assert.equal(Runtime.jobIdentity({jobId:'job-real'}),'job-real');
  assert.equal(Runtime.jobIdentity({id:'normalized'}),'normalized');
});
test('factory scene groups workstations by the server lanes and keeps readable bounds',()=>{
  const g=Runtime.buildGraph({stages:[{id:'s3',name:'기획'},{id:'s7',name:'특질'},{id:'s8',name:'프롬프트'}],gates:[],lanes:[{id:'plan',label:'기획',stages:['s3']},{id:'persona',label:'페르소나',stages:['s7','s8']}]});
  const scene=Runtime.sceneLayout(g);
  assert.equal(scene.byId.get('s7').y,scene.byId.get('s8').y);
  assert.notEqual(scene.byId.get('s3').y,scene.byId.get('s7').y);
  assert(scene.width<1000);
  assert(scene.lanes.some(l=>l.label==='페르소나'));
});
