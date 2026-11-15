/* Optional real browser check; use isolated synthetic workspace and browser profile. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||'playwright-core');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'ax-browser-session-'));
 const server=spawn(process.env.PYTHON||'python',['-u','-c',"import sys; from rehearsal.server import make_server; s=make_server(0,sys.argv[1]); print(s.server_port,flush=True); s.serve_forever()",path.join(root,'workspace')],{windowsHide:true});
 let browser;
 try {
  const port=await new Promise((resolve,reject)=>{let value=''; const timer=setTimeout(()=>reject(Error('server timeout')),15000);server.stdout.on('data',chunk=>{value+=chunk;if(value.includes('\n')){clearTimeout(timer);resolve(Number(value.trim()));}});server.once('error',reject);});
  browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage();const url=`http://127.0.0.1:${port}`;
  await page.goto(url);await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  const keys=[]; let lose=true;
  await page.route('**/api/run',async route=>{keys.push(route.request().headers()['idempotency-key']);const response=await route.fetch();assert.equal(response.status(),200);if(lose)await route.abort('failed');else await route.fulfill({response});});
  const run=async()=>{await page.click('#run');await page.waitForFunction(()=>!document.querySelector('#run').disabled);};
  await run(); const first=keys[0];assert.ok(first);
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#run').disabled);await run();assert.equal(keys[1],first);
  await page.check('input[name=faq_version][value=corrected]');await run();assert.notEqual(keys[2],first);
  await page.check('input[name=faq_version][value=stale]');await run();assert.equal(keys[3],first);
  const count=async()=>page.evaluate(async()=> (await (await fetch('/api/executions')).json()).executions.length);
  assert.equal(await count(),2);
  lose=false;await run();assert.equal(keys[4],first);assert.equal(await count(),2);
  assert.equal(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('ax.pending-executions.v1')).length),1);
  await page.screenshot({path:path.join(root,'recovered.png'),fullPage:true});
  await page.evaluate(()=>sessionStorage.setItem('ax.pending-executions.v1','corrupt'));
  const before=keys.length;await run();assert.equal(keys.length,before);
  console.log(JSON.stringify({result:'PASS',browser:await browser.version(),requests:keys.length,executions:2,reload:true,configurationReturn:true,corruptStorageBlocked:true,evidence:root}));
 } finally {if(browser)await browser.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
