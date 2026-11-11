'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../shared/chat.js');
const CID = 'cf-history-test';
const base = '/api/characters/' + CID + '/chat';
function storage(seed) {
  const map = new Map(seed ? [['cf-chat:' + CID, JSON.stringify(seed)]] : []);
  return {getItem: k => map.get(k) || null, setItem: (k,v) => map.set(k,v), removeItem: k => map.delete(k)};
}
function server() {
  const sessions = new Map();
  const posts = [];
  let fail = false, dropAck = false;
  const json = (status, body) => ({ok: status < 400, status, json: async () => structuredClone(body)});
  async function fetch(url, init = {}) {
    const method = init.method || 'GET';
    const body = init.body && JSON.parse(init.body);
    if (url === base + '/meta') return json(200, {ready:true, scenarios:[{id:'s', turns:['연습']}]});
    if (url === base + '/sessions') return fail ? json(503,{}) : json(200, {sessions:[...sessions.values()].reverse()});
    if (url.startsWith(base + '/sessions/')) {
      if (fail) return json(503, {detail:'합성 저장 실패'});
      const id = url.split('/').pop();
      const old = sessions.get(id);
      if (method === 'GET') return old ? json(200, old) : json(404, {});
      if (old && JSON.stringify(old.messages) === JSON.stringify(body.messages)) return json(200, old);
      if ((old ? old.revision : 0) !== body.revision) return json(409, {});
      const saved = {id, revision:body.revision + 1, messages:body.messages, title:body.messages[0]?.content || '새 대화', updatedAt:'2026-11-11T00:00:00Z', messageCount:body.messages.length};
      sessions.set(id, saved);
      if (dropAck) { dropAck = false; throw Error('lost acknowledgement'); }
      return json(200, saved);
    }
    if (url === base && method === 'POST') { posts.push(body); return json(200,{reply:'합성 답',ms:10}); }
    return json(404, {});
  }
  return {fetch,sessions,posts,set fail(v){fail=v;},set dropAck(v){dropAck=v;}};
}
async function open(s, cache = storage()) {
  const chat = C.createChat({fetch:s.fetch,storage:cache,characterId:CID,gap:0});
  await chat.load();
  return chat;
}

test('legacy temporary messages migrate intact and reload from server without storage', async () => {
  const s = server();
  const cache = storage({v:1,messages:[{role:'user',content:'이관할 말'},{role:'assistant',content:'기존 답',ms:12}]});
  const chat = await open(s,cache);
  assert.equal(s.sessions.size,1);
  assert.equal(chat.state.messages[1].ms,12);
  const again = await open(s);
  assert.deepEqual(again.history(),chat.history());
  assert.equal(s.posts.length,0);
});

test('new conversation and scenario retain old sessions; selection restores exact messages', async () => {
  const s=server(), chat=await open(s);
  await chat.send('첫 말');
  const first=chat.state.sessionId;
  assert.equal(await chat.reset(),true);
  assert.equal(chat.state.messages.length,0);
  await chat.send('둘째 말');
  assert.equal(await chat.selectSession(first),true);
  assert.equal(chat.history()[0].content,'첫 말');
  await chat.play('s');
  assert.equal(s.sessions.get(first).messages[0].content,'첫 말');
  assert.ok(chat.state.sessions.length>=3);
  for (const body of s.posts) assert.deepEqual(Object.keys(body),['messages']);
});

test('failed migration survives reload; retry saves without invoking a model', async () => {
  const s=server(), cache=storage({v:1,messages:[{role:'user',content:'남겨야 할 말'}]});
  s.fail=true;
  const chat=await open(s,cache);
  assert.ok(chat.state.saveError);
  assert.equal(await chat.reset(),false);
  assert.equal(chat.history()[0].content,'남겨야 할 말');
  const again=await open(s,cache);
  assert.equal(again.history()[0].content,'남겨야 할 말');
  s.fail=false;
  assert.equal(await again.retrySave(),true);
  assert.equal(again.state.saveError,'');
  assert.equal(s.sessions.size,1);
  assert.equal(s.posts.length,0);
});

test('two tabs diverging from one revision fork instead of overwriting', async () => {
  const s=server(), a=await open(s);
  await a.send('공통');
  const original=a.state.sessionId;
  const b=await open(s);
  await a.send('A의 말');
  await b.send('B의 말');
  assert.notEqual(b.state.sessionId,original);
  assert.equal(s.sessions.get(original).messages[2].content,'A의 말');
  assert.equal(s.sessions.get(b.state.sessionId).messages[2].content,'B의 말');
  assert.ok(b.state.historyNotice);
});

test('lost save acknowledgement retries same id without duplicating a session', async () => {
  const s=server(), chat=await open(s);
  s.dropAck=true;
  await chat.send('중복 금지');
  assert.equal(await chat.retrySave(),true);
  assert.equal(s.sessions.size,1);
  assert.equal([...s.sessions.values()][0].messages.length,2);
});

test('save failure prevents switching away and leaves messages available for retry', async () => {
  const s=server(), chat=await open(s);
  await chat.send('이전');
  const first=chat.state.sessionId;
  await chat.reset();
  s.fail=true;
  await chat.send('저장 실패 중에도 받은 답');
  assert.equal(await chat.selectSession(first),false);
  assert.equal(chat.history()[0].content,'저장 실패 중에도 받은 답');
  assert.ok(chat.state.saveError);
  s.fail=false;
  assert.equal(await chat.retrySave(),true);
  assert.equal(await chat.selectSession(first),true);
});

test('unacknowledged save survives refresh and does not fork a duplicate', async () => {
  const s=server(), cache=storage();
  const chat=await open(s,cache);
  // Fail every response after committing, then reload with the same temporary cache.
  const fetch=s.fetch;
  const flaky=async (url, init) => {
    const response=await fetch(url,init);
    if (init?.method==='PUT') throw Error('response lost');
    return response;
  };
  const original=C.createChat({fetch:flaky,storage:cache,characterId:CID,gap:0});
  await original.load();
  await original.send('새로고침 뒤에도 한 대화');
  assert.ok(original.state.saveError);
  original.destroy();
  const again=await open(s,cache);
  assert.equal(s.sessions.size,1);
  assert.equal(again.history()[1].content,'합성 답');
  assert.equal(again.state.saveError,'');
});

test('a malformed temporary cache is never replaced by a blank conversation', async () => {
  const s=server(), cache=storage();
  cache.setItem('cf-chat:'+CID,'{invalid');
  const chat=await open(s,cache);
  assert.equal(await chat.reset(),false);
  assert.equal(cache.getItem('cf-chat:'+CID),'{invalid');
  assert.ok(chat.state.storageError);
});

test('history UI exposes selection, persistent failure feedback and a working retry action', async () => {
  const fs=require('node:fs'), vm=require('node:vm');
  const listeners={};
  const history={hidden:false,innerHTML:''};
  const doc={nodeType:9,documentElement:{removeAttribute(){}},activeElement:null,
    querySelector:sel=>sel==='[data-history]'?history:null,querySelectorAll:()=>[],
    addEventListener:(type,fn)=>{listeners[type]=fn;}};
  const win={document:doc,location:{hash:'#c/'+CID},crypto:globalThis.crypto,
    addEventListener(){},setInterval,clearInterval};
  vm.runInNewContext(fs.readFileSync(require.resolve('../shared/chat.js'),'utf8'),{window:win,setTimeout,clearTimeout});
  const s=server();
  const mounted=win.CharacterChat.mount({root:doc,fetch:s.fetch,storage:storage()});
  for(let i=0;i<10;i++) await new Promise(r=>setImmediate(r));
  await mounted.chat.send('선택할 대화');
  const first=mounted.chat.state.sessionId;
  await mounted.chat.reset();
  assert.match(history.innerHTML,/이전 대화/);
  assert.ok(history.innerHTML.includes(first));
  listeners.change({target:{matches:sel=>sel==='[data-history-select]',value:first}});
  for(let i=0;i<10;i++) await new Promise(r=>setImmediate(r));
  assert.equal(mounted.chat.history()[0].content,'선택할 대화');
  s.fail=true;
  await mounted.chat.send('실패 표시');
  assert.match(history.innerHTML,/role="alert"/);
  assert.match(history.innerHTML,/저장 다시 시도/);
  s.fail=false;
  listeners.click({target:{closest:()=>({disabled:false,dataset:{act:'save-history'}})}});
  for(let i=0;i<10;i++) await new Promise(r=>setImmediate(r));
  assert.equal(mounted.chat.state.saveError,'');
  mounted.chat.destroy();
});

test('save timeout leaves a retryable snapshot instead of blocking forever', async () => {
  const s=server();
  let hang=true;
  const fetch=(url,init)=>hang && init?.method==='PUT' ? new Promise(()=>{}) : s.fetch(url,init);
  const chat=C.createChat({fetch,storage:storage(),characterId:CID,historyTimeoutMs:10});
  await chat.load();
  const result=await Promise.race([chat.send('시간 초과'),new Promise(r=>setTimeout(()=>r('hung'),100))]);
  assert.notEqual(result,'hung');
  assert.ok(chat.state.saveError);
  hang=false;
  assert.equal(await chat.retrySave(),true);
  assert.equal([...s.sessions.values()][0].messages.length,2);
});

test('oversized input is rejected before it can poison the saved conversation', async () => {
  const s=server(), chat=await open(s);
  assert.equal(await chat.send('가'.repeat(16001)),false);
  assert.equal(chat.state.messages.length,0);
  assert.ok(chat.state.inputError);
  assert.equal(s.posts.length,0);
  assert.equal(await chat.send('짧은 말'),true);
  assert.equal(chat.state.inputError,'');
  assert.equal(await chat.reset(),true);
});

test('saved history remains visible when the model prompt is not ready', async () => {
  const fs=require('node:fs'), vm=require('node:vm');
  const list={hidden:true,innerHTML:'',scrollHeight:0,scrollTop:0,clientHeight:0};
  const doc={nodeType:9,documentElement:{removeAttribute(){}},activeElement:null,
    querySelector:sel=>sel==='[data-list]'?list:null,querySelectorAll:()=>[],addEventListener(){}};
  const win={document:doc,location:{hash:'#c/'+CID},crypto:globalThis.crypto,addEventListener(){},setInterval,clearInterval};
  vm.runInNewContext(fs.readFileSync(require.resolve('../shared/chat.js'),'utf8'),{window:win,setTimeout,clearTimeout});
  const s=server(), saved=await open(s); await saved.send('다시 읽을 말');
  const fetch=(url,init)=>url===base+'/meta' ? Promise.resolve({ok:true,json:async()=>({ready:false,reason:'합성 프롬프트 없음'})}) : s.fetch(url,init);
  const mounted=win.CharacterChat.mount({root:doc,fetch,storage:storage()});
  for(let i=0;i<10;i++)await new Promise(r=>setImmediate(r));
  assert.equal(list.hidden,false);
  assert.match(list.innerHTML,/다시 읽을 말/);
  assert.equal(mounted.chat.canSend(),false);
  mounted.chat.destroy();
});

test('conversation capacity is checked before adding an unsaveable turn and old history stays selectable', async () => {
  const s=server();
  const many=Array.from({length:100},(_,i)=>({role:i%2?'assistant':'user',content:'합성 '+i}));
  const chat=await open(s,storage({v:1,messages:many}));
  const id=chat.state.sessionId;
  assert.equal(await chat.send('101번째'),false);
  assert.equal(chat.state.messages.length,100);
  assert.equal(await chat.reset(),true);
  assert.equal(await chat.selectSession(id),true);
  assert.equal(chat.state.messages.length,100);
  const large=Array.from({length:50},(_,i)=>({role:i%2?'assistant':'user',content:'가'.repeat(12000)}));
  const second=await open(server(),storage({v:1,messages:large}));
  assert.equal(await second.send('용량 한도'),false);
  assert.equal(second.state.messages.length,50);
  assert.equal(await second.reset(),true);
});

test('legacy oversized temporary input can be archived, replaced, reset and selected without truncation', async () => {
  const s=server(), content='보존'.repeat(9000);
  const cache=storage({v:1,messages:[{role:'user',content}]});
  const chat=await open(s,cache);
  const original=chat.state.sessionId;
  assert.equal(s.sessions.get(original).messages[0].content,content);
  assert.equal(await chat.retry(),false,'do not submit an oversized legacy turn to the model');
  assert.equal(s.posts.length,0);
  assert.equal(await chat.send('짧은 대체 메시지'),true);
  assert.notEqual(chat.state.sessionId,original);
  assert.equal(s.sessions.get(original).messages[0].content,content);
  assert.equal(await chat.reset(),true);
  assert.equal(await chat.selectSession(original),true);
  assert.equal(chat.history()[0].content,content);
});

test('composer preserves rejected oversized text for editing', async () => {
  const fs=require('node:fs'), vm=require('node:vm');
  const events={};
  const input={value:'',disabled:false,style:{},scrollHeight:30,addEventListener(){},focus(){}};
  const form={hidden:false,addEventListener:(name,fn)=>{events[name]=fn;}};
  const send={dataset:{mode:'send'},setAttribute(){}};
  const error={hidden:true,textContent:''};
  const nodes={'[data-input]':input,'[data-composer]':form,'[data-send]':send,'[data-input-error]':error};
  const doc={nodeType:9,documentElement:{removeAttribute(){}},activeElement:null,
    querySelector:sel=>nodes[sel]||null,querySelectorAll:()=>[],addEventListener(){}};
  const win={document:doc,location:{hash:'#c/'+CID},crypto:globalThis.crypto,addEventListener(){},setInterval,clearInterval};
  vm.runInNewContext(fs.readFileSync(require.resolve('../shared/chat.js'),'utf8'),{window:win,setTimeout,clearTimeout});
  const s=server(), mounted=win.CharacterChat.mount({root:doc,fetch:s.fetch,storage:storage()});
  for(let i=0;i<10;i++) await new Promise(r=>setImmediate(r));
  input.value='가'.repeat(16001);
  events.submit({preventDefault(){}});
  assert.equal(input.value.length,16001);
  assert.equal(error.hidden,false);
  assert.equal(mounted.chat.state.messages.length,0);
  assert.equal(s.posts.length,0);
  mounted.chat.destroy();
});
