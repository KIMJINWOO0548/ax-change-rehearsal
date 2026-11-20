/* Real Edge, isolated synthetic SQLite only. No external services or browser profile. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||'playwright-core');
(async()=>{
 const root=process.env.QA_OUTPUT_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'ax-policy-selector-'));
 const workspace=path.join(root,'version-selector-evidence-'+Date.now());
 const server=spawn(process.env.PYTHON||'python',['-u','-c',"import sys; from rehearsal.server import make_server; s=make_server(0,sys.argv[1]); print(s.server_port,flush=True); s.serve_forever()",workspace],{windowsHide:true});
 let browser;
 try{
  const port=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('server timeout')),15000);server.stdout.on('data',part=>{text+=part;if(text.includes('\n')){clearTimeout(timer);resolve(Number(text.trim()));}});server.once('error',reject);});
  browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1365,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${port}`);await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  assert.match(await page.locator('#effective-date').innerText(),/2026-12-01/);
  const requests=[],reports=[];let lose=true;
  await page.route('**/api/run',async route=>{
   requests.push({key:route.request().headers()['idempotency-key'],body:route.request().postDataJSON()});
   const response=await route.fetch();assert.equal(response.status(),200);reports.push(await response.json());
   if(lose)await route.abort('failed');else await route.fulfill({response});
  });
  const one=async()=>{await page.click('#select-none');await page.check('input[name=case_id][value=S04]');};
  const run=async()=>{await page.click('#run');await page.waitForFunction(()=>!document.querySelector('#run').disabled);};
  await one();await run();assert.match(await page.locator('#run-status').innerText(),/실행 완료 여부/);
  const first=requests[0].key;assert.ok(first);assert.equal(requests[0].body.policy_version,undefined);
  await page.selectOption('#policy-version','returns-20270115');await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  assert.equal(requests.length,1);assert.equal(await page.locator('input[name=case_id]').count(),8);
  assert.match(await page.locator('#effective-date').innerText(),/2027-01-15/);
  assert.match(await page.locator('#policy-change').innerText(),/21/);
  assert.match(await page.locator('#after-change').innerText(),/21 days inclusive/);
  assert.match(await page.locator('#after-source').textContent(),/versions\/returns-20270115/);
  assert.equal(await page.locator('#result-content').isVisible(),false);assert.equal(await page.locator('#download').isDisabled(),true);
  await page.check('input[name=faq_version][value=corrected]');await page.check('input[name=api_version][value=corrected]');
  lose=false;await run();assert.equal(requests[1].body.policy_version,'returns-20270115');assert.notEqual(requests[1].key,first);
  assert.equal(reports[1].total,8);assert.deepEqual(reports[1].counts,{PASS_WITHIN_SCOPE:8});
  assert.ok(reports[1].cases.some(item=>item.crosscheck.state==='ALIGNED'));
  await page.locator('#case-rows button[data-case-id="S04"]').click();
  assert.match(await page.locator('#detail-facts').textContent(),/FAQ·API 교차 판단/);
  assert.match(await page.locator('#state-comparison').innerText(),/모의 알림 의도/);
  assert.match(await page.locator('#state-comparison').innerText(),/후보 · 검토자 기대 1건 · 최초 1건 · 재호출 1건/);
  const savedRun=reports[1].run_id;
  await page.getByRole('button',{name:savedRun+' 저장 근거 열기'}).click();
  const savedEffect=page.locator('#archive-evidence details').filter({hasText:/"id": "S04"/}).filter({hasText:/후보 검토자 기대 1건/}).first();
  await savedEffect.locator('summary').click();
  assert.match(await savedEffect.innerText(),/모의 알림 의도 · 후보 검토자 기대 1건 · 최초 1건 · 재호출 1건/);
  assert.equal(await page.locator('#download').isDisabled(),false);assert.match(await page.locator('#run-meta').textContent(),/returns-20270115/);
  assert.equal(await page.locator('#compare-run').isDisabled(),true);
  await page.screenshot({path:path.join(root,'version-selector-alternate.png'),fullPage:true});
  await page.selectOption('#policy-version','');await page.waitForFunction(()=>!document.querySelector('#run').disabled);
  assert.equal(await page.locator('input[name=case_id]').count(),12);await one();await run();
  assert.equal(requests[2].key,first);assert.equal(reports[2].run_id,reports[0].run_id);
  const attempts=await page.evaluate(async()=> (await (await fetch('/api/executions')).json()).executions);
  assert.equal(attempts.length,2);assert.ok(attempts.every(a=>a.state==='COMPLETED'));
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#run').disabled);assert.equal(requests.length,3);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',browser:await browser.version(),requests:requests.map(r=>r.body),completedAttempts:attempts.length,alternateCases:8,legacyCases:12,noAutoReplay:true,lostResponseKeyRecovered:true,crossVersionResultsCleared:true,workspace},null,2));
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
