'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const puppeteer=require('/tmp/cfshot/node_modules/puppeteer-core');
const base=process.env.STUDIO_URL||'http://127.0.0.1:8776';
(async()=>{
 const config=await (await fetch(base+'/api/text-pipeline')).json();
 const browser=await puppeteer.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const reports=[];
 try {
  const p=await browser.newPage();await p.setViewport({width:1280,height:982});
  let selected=structuredClone(config),posts=0;
  const detail={characterId:'cf-fixture',name:'연결 검사 (합성)',stages:[{id:'s8',label:'프롬프트',status:'AWAITING_HUMAN',revision:'pv1'}],gates:[{id:'G6',status:'AWAITING_HUMAN',revision:'pv1'}],calls:[{task:'voice',stage:'s7',model:'google-antigravity/gemini-3.8-flash',profile:'basic_test',route:'opencodex',ok:true,ref:'cf-fixture/tr1'}],artifacts:[{label:'검사 자료',revision:'pv1',text:'<img src=x onerror="window.__artifactInjection=1">',textTruncated:true,sourceModel:'google-antigravity/gemini-3.8-flash',sourceProfile:'basic_test',completionCheck:'NOT_RUN'}],workshopUrl:'/c-glass.html?character=cf-fixture'};
  await p.setRequestInterception(true);
  p.on('request',async r=>{
   const u=new URL(r.url());if(!u.pathname.startsWith('/api/text-pipeline'))return r.continue();
   let data,status=200;
   if(u.pathname.endsWith('/selection')){
    posts++;const body=JSON.parse(r.postData());
    if(body.profile==='pre_demo_completion_check'){status=409;data={detail:'검사 중 설정을 바꿀 수 없어요'};}
    else {selected.profile=body.profile||selected.profile;selected.tasks=selected.tasks.map(t=>({...t,model:['voice','sft_answers','repair'].includes(t.id)?'google-antigravity/gemini-4-argon':t.model}));data=selected;}
   } else if(u.pathname.endsWith('/characters')) data={characters:[{id:'cf-fixture',name:'연결 검사 (합성)'}]};
   else if(u.pathname.endsWith('/characters/cf-fixture'))data=detail;
   else data=selected;
   await r.respond({status,contentType:'application/json',body:JSON.stringify(data)});
  });
  await p.goto(base+'/studio/d-ops.html',{waitUntil:'networkidle2'});
  await p.click('[data-text-pipeline-open]');
  await p.waitForSelector('[data-ftp-kind="profile"][value="demo"]');
  await p.click('label:has([data-ftp-kind="profile"][value="demo"])');
  await p.waitForFunction(()=>document.querySelector('[data-ftp-kind="profile"][value="demo"]')?.checked&&!document.querySelector('[data-ftp-kind="profile"][value="demo"]')?.disabled);
  await p.click('[data-ftp-char="cf-fixture"]');
  await p.waitForSelector('.ftp-artifact');
  const artifact=await p.$eval('.ftp-artifact',n=>n.textContent);
  assert(artifact.includes('google-antigravity/gemini-3.8-flash'));
  assert(artifact.includes('basic_test'));
  assert(!artifact.includes('gemini-4-argon'),'a current Argon choice cannot relabel a Flash artifact');
  assert(artifact.includes('일부만 표시'),'server truncation is shown');
  assert.equal(await p.$eval('.ftp-artifact .ftp-pill',n=>n.textContent.includes('최종 점검 전')),true);
  await p.click('.ftp-artifact-body summary');
  assert.equal(await p.evaluate(()=>window.__artifactInjection),undefined,'artifact text is escaped');
  await p.click('label:has([data-ftp-kind="profile"][value="pre_demo_completion_check"])');
  await p.waitForFunction(()=>document.querySelector('[data-ftp-alert]').textContent.length>0);
  assert.equal(await p.$eval('[data-ftp-kind="profile"][value="demo"]',n=>n.checked),true,'failed selection preserves old choice');
  assert.equal(posts,2);reports.push({case:'selection-and-source',result:'passed',posts});
  await p.close();
  const offline=await browser.newPage();await offline.setViewport({width:1280,height:982});
  await offline.setRequestInterception(true);offline.on('request',r=>new URL(r.url()).pathname.startsWith('/api/text-pipeline')?r.abort('failed'):r.continue());
  await offline.goto(base+'/studio/d-ops.html',{waitUntil:'networkidle2'});await offline.click('[data-text-pipeline-open]');
  await offline.waitForSelector('[data-ftp-retry-config]');
  assert.equal(await offline.$$eval('.ftp-role',n=>n.length),0,'offline does not fabricate role assignments');
  assert(await offline.$eval('[data-ftp-dialog]',n=>n.textContent.includes('연결')));
  reports.push({case:'offline',result:'passed'});await offline.close();
  fs.writeFileSync(path.resolve(__dirname,'../plans/integration-work/browser-states-results.json'),JSON.stringify(reports,null,2));
  console.log(JSON.stringify(reports));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
