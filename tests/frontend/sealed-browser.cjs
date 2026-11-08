/* Verify an encrypted-backup restored synthetic workspace through the real local UI. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const assert=require('node:assert/strict');
const {spawn,spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const output=process.env.QA_OUTPUT_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'ax-sealed-qa-'));
const scratch=fs.mkdtempSync(path.join(os.tmpdir(),'ax-sealed-data-'));
const source=path.join(scratch,'source'),backup=path.join(scratch,'backup'),restored=path.join(scratch,'restored');
const env={...process.env,PYTHONUNBUFFERED:'1',PYTHONIOENCODING:'utf-8'};
let browser,server;
async function start(workspace){
 server=spawn(process.env.PYTHON||'python',['serve_workbench.py','--port','0','--workspace',workspace],{cwd:root,env,stdio:['ignore','pipe','pipe']});
 const child=server;
 return new Promise((resolve,reject)=>{
  let logs='';const timer=setTimeout(()=>reject(new Error('Server startup timed out')),15000);
  child.stdout.on('data',chunk=>{logs+=chunk;const match=logs.match(/Open (http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
  child.stderr.on('data',chunk=>logs+=chunk);
  child.once('exit',code=>{clearTimeout(timer);reject(new Error('Server startup failed '+code+': '+logs));});
 });
}
async function stop(){
 if(server&&server.exitCode===null){const child=server;await new Promise(resolve=>{child.once('exit',resolve);child.kill();});}
 server=null;
}
function command(args){
 const result=spawnSync(process.env.PYTHON||'python',['manage_recovery.py',...args],{cwd:root,env,encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout);
}
function sealedCommand(operation){
 // Public synthetic fixture phrase only; no real user password or file is accepted.
 const script = "import json,sys; from rehearsal.sealed import seal_backup,inspect_sealed,restore_sealed; " +
  "phrase=b'synthetic browser QA phrase only'; operation,bundle,cipher,target=sys.argv[1:]; " +
  "result=seal_backup(bundle,cipher,phrase) if operation=='seal' else inspect_sealed(cipher,phrase) if operation=='inspect' else restore_sealed(cipher,target,phrase); print(json.dumps(result))";
 const cipher=path.join(scratch,'sample.axsealed');
 const result=spawnSync(process.env.PYTHON||'python',['-c',script,operation,backup,cipher,restored],{cwd:root,env,encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout);
}
async function archiveStatus(page,text){await page.waitForFunction(text=>document.getElementById('archive-status').textContent.includes(text),text);}
async function revealStoredEvidence(page){
 await page.waitForFunction(()=>!document.getElementById('archive-detail').hidden&&document.getElementById('archive-detail').getAttribute('aria-busy')==='false');
 if(await page.locator('.archive-identifiers').getAttribute('open')===null)await page.locator('.archive-identifiers > summary').click();
 for(const details of await page.locator('#archive-events details').all())if(await details.getAttribute('open')===null)await details.locator('summary').click();
}
(async()=>{
 try{
  fs.mkdirSync(output,{recursive:true});
  browser=await chromium.launch({...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  let url=await start(source);await page.goto(url);await page.locator('#run:enabled').waitFor();
  await page.locator('#select-boundary').click();await page.locator('#run').click();
  await page.waitForFunction(()=>document.getElementById('run-status').textContent.startsWith('실행 완료'));
  await archiveStatus(page,'저장된 합성 실행 1개');
  await page.locator('#archive-list button').first().click();await archiveStatus(page,'과거 저장 근거');await revealStoredEvidence(page);
  await page.locator('#archive-review-status').selectOption('CHANGES_REQUESTED');
  await page.locator('#archive-note').fill('Synthetic recovery drill: preserve scope and review history.');
  await page.locator('#archive-save').click();await archiveStatus(page,'로컬 검토 메모를 저장했습니다');await revealStoredEvidence(page);
  const meta=await page.locator('#archive-meta').innerText(),events=await page.locator('#archive-events').innerText();
  // Online snapshot while source server remains available. Restore never touches it.
  const created=command(['backup','--workspace',source,'--destination',backup]);
  const sealed=sealedCommand('seal');
  const checked=sealedCommand('inspect');
  const recovered=sealedCommand('restore');
  assert.equal(sealed.encrypted,true);assert.equal(checked.database_verified,false);
  assert.equal(checked.verification,'AUTHENTICATED_ENVELOPE');
  assert.equal(recovered.database_verified,true);assert.equal(recovered.verification,'RESTORED_DATABASE_VERIFIED');
  assert.equal(created.database_sha256,checked.database_sha256);
  assert.equal(created.database_sha256,recovered.database_sha256);
  assert.equal(created.authenticated,false);assert.equal(created.encrypted,false);
  assert.equal(recovered.signer_authenticated,false);
  await page.reload();await page.locator('#archive-list button').first().waitFor();
  await page.locator('#archive-list button').first().click();await archiveStatus(page,'과거 저장 근거');await revealStoredEvidence(page);
  assert.equal(await page.locator('#archive-meta').innerText(),meta,'Source remains unchanged');
  await stop();url=await start(restored);await page.goto(url);await page.locator('#run:enabled').waitFor();
  await page.locator('#archive-list button').first().waitFor();await page.locator('#archive-list button').first().click();await archiveStatus(page,'과거 저장 근거');await revealStoredEvidence(page);
  assert.equal(await page.locator('#archive-meta').innerText(),meta);
  assert.equal(await page.locator('#archive-events').innerText(),events);
  assert.equal(await page.locator('#case-rows tr').count(),0,'Historical recovery must not become a current run');
  assert.match(await page.locator('#archive-meta').innerText(),/수정 요청/);
  assert.equal(await page.locator('#archive-save').isEnabled(),true);
  await page.screenshot({path:path.join(output,'ax-sealed-recovered-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.locator('#archive-detail').scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,'ax-sealed-recovered-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',checks:['Live consistent backup plus encrypted copy','Authenticated envelope inspection only','Authenticated new workspace restore','Original evidence unchanged','Exact report and review recovery','Historical and current results remain separate','390px layout'],screenshots:output},null,2));
 }finally{await stop();if(browser)await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
