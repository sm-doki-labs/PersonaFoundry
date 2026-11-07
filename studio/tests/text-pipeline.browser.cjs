'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require('/tmp/cfshot/node_modules/puppeteer-core');
const base = process.env.STUDIO_URL || 'http://127.0.0.1:8776';
(async () => {
  const browser = await puppeteer.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  const output = {screens:[],errors:[]};
  try {
    for (const width of [1512,1280]) {
      const p = await browser.newPage();
      await p.setViewport({width,height:982});
      p.on('pageerror',e=>output.errors.push(e.message));
      await p.goto(base+'/studio/d-ops.html?mode=demo#job/seoha-new/floor',{waitUntil:'networkidle2'});
      await p.waitForFunction(()=>window.__ops && window.FactoryTextPipeline);
      const count = await p.evaluate(()=>window.__ops.TASKS.find(t=>t.id==='r2').calls);
      assert.equal(count,0,'deterministic prompt assembly has no simulated model calls');
      const root = await p.$('[data-text-pipeline-root]');
      assert(root);
      await p.click('[data-text-pipeline-open]');
      await p.waitForSelector('[data-ftp-dialog]',{visible:true});
      await p.waitForFunction(()=>document.querySelector('[data-ftp-config]').textContent.includes('개발 확인'));
      const observed = await p.evaluate(()=>{
        const dialog=document.querySelector('[data-ftp-dialog]');
        const rect=dialog.getBoundingClientRect();
        const test=document.querySelector('[data-ftp-kind="route"][value="test"]');
        return {left:rect.left,right:rect.right,width:rect.width,scrollWidth:dialog.scrollWidth,
          clientWidth:dialog.clientWidth,disabledTest:test?.disabled,text:dialog.textContent};
      });
      assert(observed.left>=0 && observed.right<=width+1,'dialog fits viewport');
      assert(observed.scrollWidth<=observed.clientWidth+1,'dialog does not overflow horizontally');
      assert.equal(observed.disabledTest,true);
      assert(observed.text.includes('실제'));
      assert(observed.text.includes('기본 프로필') || observed.text.includes('기본 설정'));
      await p.keyboard.press('h');
      assert.equal(await p.evaluate(()=>window.CF_FLOOR.guiding()),false,'dialog shortcut cannot open simulator guide');
      for(let i=0;i<28;i++) {
        await p.keyboard.press('Tab');
        assert(await p.evaluate(()=>document.querySelector('[data-ftp-dialog]').contains(document.activeElement)),'focus remains inside dialog');
      }
      const image=path.resolve(__dirname,`../previews/text-pipeline-${width}.png`);
      await p.screenshot({path:image});
      output.screens.push({width,image,dialogWidth:observed.width});
      await p.keyboard.press('Escape');
      assert.equal(await p.evaluate(()=>document.activeElement.hasAttribute('data-text-pipeline-open')),true,'focus returns to opener');
      await p.close();
    }
    const direct = await browser.newPage();
    await direct.setViewport({width:1512,height:982});
    await direct.goto(base+'/studio/d-ops.html?mode=demo&panel=text#job/seoha-new/floor',{waitUntil:'networkidle2'});
    await direct.waitForSelector('[data-ftp-dialog]',{visible:true});
    await direct.waitForFunction(()=>document.querySelectorAll('.ftp-role').length===9);
    assert(await direct.$eval('[data-ftp-dialog]',n=>n.textContent.includes('기본 설정 정리')));
    await direct.close();
    assert.deepEqual(output.errors,[]);
    fs.writeFileSync(path.resolve(__dirname,'../plans/integration-work/browser-results.json'),JSON.stringify(output,null,2));
    console.log(JSON.stringify(output));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
