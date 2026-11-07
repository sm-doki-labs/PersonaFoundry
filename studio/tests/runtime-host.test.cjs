const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const read = f => fs.readFileSync(path.join(__dirname,'..',f),'utf8');
test('studio defaults to real renderer and simulator requires explicit demo mode',()=>{
 const html = read('d-ops.html'), ops=read('shared/ops.js');
 assert(html.includes('shared/runtime.js'));
 assert(html.includes('shared/runtime.css'));
 assert(html.indexOf('shared/runtime.js') < html.indexOf('shared/ops.js'));
 assert(ops.slice(0,500).includes("get('mode') !== 'demo'"));
 assert(html.includes('FactoryRuntime.mount'));
});
