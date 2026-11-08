/* Optional browser QA: installed Playwright + Chromium; server running on 8765. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
 const output = process.env.QA_OUTPUT_DIR || fs.mkdtempSync(path.join(os.tmpdir(), 'ax-workbench-qa-'));
 fs.mkdirSync(output, { recursive: true });
 let browser;
 try {
 browser = await chromium.launch({ ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {}), headless:true });
 const page = await browser.newPage({viewport:{width:1488,height:1058}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const base=process.env.WORKBENCH_URL || 'http://127.0.0.1:8765';
 await page.goto(base);await page.locator('#run:enabled').waitFor();
 assert.match(await page.locator('#run-status').innerText(),/아직/);
 await page.screenshot({path:path.join(output,'ax-initial.png'),fullPage:true});
 async function run(){await page.locator('#run').click();await page.waitForFunction(()=>document.querySelector('#run-status').textContent.startsWith('실행 완료'));}
 await run();assert.equal(await page.locator('#case-rows tr').count(),12);
 assert.match(await page.locator('#summary').innerText(),/불일치/);
 await page.locator('#case-rows button').first().press('Enter');assert.equal(await page.locator('#case-detail').isVisible(),true);
 assert.match(await page.locator('#detail-objects').innerText(),/state|observ|response/);
 await page.locator('#verdict-filter').selectOption('FAIL');assert.ok(await page.locator('#case-rows tr').count()>0);
 await page.locator('input[name=faq_version][value=corrected]').check();assert.match(await page.locator('#run-status').innerText(),/이전 실행/);assert.equal(await page.locator('#download').isDisabled(),true);
 await run();assert.match(await page.locator('#summary').innerText(),/불일치/);
 await page.locator('input[name=api_version][value=corrected]').check();await run();
 assert.doesNotMatch(await page.locator('#summary').innerText(),/불일치/);assert.match(await page.locator('#run-status').innerText(),/보류/);
 const downloadPromise=page.waitForEvent('download');await page.locator('#download').click();const download=await downloadPromise;assert.match(download.suggestedFilename(),/^ax-rehearsal-.*json$/); const exported=JSON.parse(fs.readFileSync(await download.path(),'utf8'));assert.equal(exported.total,12);assert.equal(exported.counts.PASS_WITHIN_SCOPE,9);assert.equal(exported.csrf_token,undefined);
 await page.locator('#case-rows button').first().click();await page.screenshot({path:path.join(output,'ax-result.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 const mobileDetail=page.locator('#case-rows button').first();
 const mobileBox=await mobileDetail.boundingBox();
 assert.ok(mobileBox.width>=84,'Mobile detail button must be at least 84px wide');
 assert.ok(mobileBox.height<=46,'Mobile detail button must remain on one line');
 await mobileDetail.scrollIntoViewIfNeeded();
 const visibleBox=await mobileDetail.boundingBox();const tableBox=await page.locator('.table-wrap').boundingBox();
 assert.ok(visibleBox.x>=tableBox.x-1 && visibleBox.x+visibleBox.width<=tableBox.x+tableBox.width+1,'Entire detail button must be visible after scrolling');
 await page.screenshot({path:path.join(output,'ax-mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
 await page.route('**/api/run',async route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:{message:'QA simulated failure'}})}));
 await page.locator('#run').click();await page.waitForFunction(()=>document.querySelector('#run-status').textContent.includes('QA simulated failure'));
 assert.equal(await page.locator('#download').isDisabled(),true);assert.equal(await page.locator('#run').isEnabled(),true);
 await page.unroute('**/api/run');
 let calls=0;await page.route('**/api/run',async route=>{calls++;await new Promise(resolve=>setTimeout(resolve,250));await route.continue();});
 await page.locator('#run').evaluate(button=>{button.click();button.click();});await page.waitForFunction(()=>document.querySelector('#run-status').textContent.startsWith('실행 완료'));assert.equal(calls,1);
 assert.deepEqual(errors,[]);
 await page.route('**/api/context',async route=>{const response=await route.fetch();const json=await response.json();json.policy_review_valid=false;await route.fulfill({json});});
 await page.reload();await page.waitForFunction(()=>document.querySelector('#run-status').textContent.includes('정책 문서가 바뀌었습니다'));
 assert.equal(await page.locator('#run').isDisabled(),true);
 console.log('PASS: initial, stale/FAQ-only/corrected runs, keyboard detail, filter, invalidation, download, mobile overflow, error recovery, duplicate click, policy review guard; no page errors.');
 console.log('QA screenshots:',output);
 } finally { if (browser) await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
