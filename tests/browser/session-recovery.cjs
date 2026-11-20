/* Optional real browser check; use isolated synthetic workspace and browser profile. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||'playwright-core');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'ax-browser-session-'));
 const workspace=path.join(root,'workspace'), python=process.env.PYTHON||'python';
 const crash=spawnSync(python,['-c',`import os, sys
from rehearsal.app import execute_run
from rehearsal.server import execute_persisted
from rehearsal.storage import EvidenceStore
store = EvidenceStore(sys.argv[1])
record = store.record_stage
def checkpoint(attempt, key, stage, state, evidence):
    if stage == 'invocation' and state == 'COMPLETED': os._exit(41)
    record(attempt, key, stage, state, evidence)
store.record_stage = checkpoint
execute_persisted(store, {'faq_version':'corrected','api_version':'corrected','case_ids':['S02']}, execute_run, request_key='browser-crash')
`,workspace],{encoding:'utf8',windowsHide:true,timeout:30000});
 assert.equal(crash.status,41,crash.stderr||String(crash.error||'crash did not occur'));
 const server=spawn(python,['-u','-c',"import sys; from rehearsal.server import make_server; s=make_server(0,sys.argv[1]); print(s.server_port,flush=True); s.serve_forever()",workspace],{windowsHide:true});
 let browser;
 try {
  const port=await new Promise((resolve,reject)=>{let value=''; const timer=setTimeout(()=>reject(Error('server timeout')),15000);server.stdout.on('data',chunk=>{value+=chunk;if(value.includes('\n')){clearTimeout(timer);resolve(Number(value.trim()));}});server.once('error',reject);});
  browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage();const url=`http://127.0.0.1:${port}`;
  await page.goto(url);await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  const recovered=page.locator('#archive-execution-list details');
  await recovered.locator('summary').click();
  await recovered.getByText(/호출 · 시작 기록만 있음 · 확인 필요/).waitFor();
  assert.match(await recovered.innerText(),/완료 미확인/);
  assert.match(await recovered.innerText(),/초기 관찰 · 완료 기록/);
  assert.match(await recovered.innerText(),/호출 · 시작 기록만 있음 · 확인 필요/);
  if(process.env.QA_OUTPUT_DIR)await page.locator('#archive-executions').screenshot({path:path.join(process.env.QA_OUTPUT_DIR,'execution-crash-recovered.png')});
  await page.route('**/api/executions',route=>route.abort('failed'));
  await page.locator('#archive-refresh').click();
  await page.waitForFunction(()=>document.querySelector('#archive-execution-status').textContent.includes('확인하지 못했습니다'));
  assert.equal(await recovered.count(),0);
  await page.unroute('**/api/executions');
  const keys=[]; let lose=true;
  await page.route('**/api/run',async route=>{keys.push(route.request().headers()['idempotency-key']);const response=await route.fetch();assert.equal(response.status(),200);if(lose)await route.abort('failed');else await route.fulfill({response});});
  const run=async()=>{await page.click('#run');await page.waitForFunction(()=>!document.querySelector('#run').disabled);};
  await run(); const first=keys[0];assert.ok(first);
  assert.match(await page.locator('#run-status').innerText(),/실행 완료 여부를 확인하지 못했습니다/);
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  assert.match(await page.locator('#run-status').innerText(),/완료 응답을 확인하지 못한/);
  assert.equal(keys.length,1);
  await run();assert.equal(keys[1],first);
  await page.check('input[name=faq_version][value=corrected]');await run();assert.notEqual(keys[2],first);
  await page.check('input[name=faq_version][value=stale]');await run();assert.equal(keys[3],first);
  const count=async()=>page.evaluate(async()=> (await (await fetch('/api/executions')).json()).executions.length);
  assert.equal(await count(),3);
  lose=false;await run();assert.equal(keys[4],first);assert.equal(await count(),3);
  assert.equal(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('ax.pending-executions.v1')).length),1);
  await page.screenshot({path:path.join(root,'recovered.png'),fullPage:true});
  await page.evaluate(()=>sessionStorage.setItem('ax.pending-executions.v1','corrupt'));
  const before=keys.length;await run();assert.equal(keys.length,before);
  console.log(JSON.stringify({result:'PASS',browser:await browser.version(),requests:keys.length,executions:3,crashExit:crash.status,unknownStagesVisible:true,failedReadClearsStale:true,reload:true,configurationReturn:true,corruptStorageBlocked:true,evidence:root}));
 } finally {if(browser)await browser.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
