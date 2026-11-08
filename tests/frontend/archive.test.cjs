const test=require('node:test');
const assert=require('node:assert/strict');
const archive=require('../../web/archive.js');
const id='12345678-1234-1234-1234-123456789abc',h='a'.repeat(64);
const created='2026-11-08T00:00:00Z';
const storage={enabled:true,kind:'local-synthetic',review_is_approval:false,limit:100};
const record=()=>({run_id:id,sha256:h,created_at:created,revision:0,review_status:'UNREVIEWED',review_is_approval:false});
const detail=()=>{
 const configuration={faq_version:'stale',api_version:'corrected',case_ids:['S01']};
 const scope={selected_case_ids:['S01'],omitted_case_ids:[],selected_total:1,registered_total:1,complete:true};
 const manifest={...require('./comparison-fixtures.cjs').manifest(),configuration:structuredClone(configuration),scope:structuredClone(scope),faq_sha256:h,faq_artifact_sha256:h};
 return {record:record(),report:{run_id:id,created_at:created,synthetic_only:true,total:1,cases:[{id:'S01',business_verdict:'FAIL'}],configuration,scope,counts:{FAIL:1},readiness:'BLOCKED',manifest,manifest_sha256:h},events:[]};
};
test('record identity, revision, approval disclaimer, and digest fail closed',()=>{
 assert.equal(archive.validRecord(record()),true);
 for(const bad of [{revision:-1},{revision:0.5},{review_status:'APPROVED'},{review_is_approval:true},{sha256:'bad'},{run_id:'../x'}])assert.equal(archive.validRecord({...record(),...bad}),false);
});
test('detail rejects wrong run, missing evidence, and inconsistent chronology',()=>{
 assert.equal(archive.validateDetail(detail(),id).record.run_id,id);
 for(const alter of [d=>d.report.run_id='wrong',d=>d.report.cases=[],d=>d.record.revision=1,d=>d.record.review_status='REVIEWED',d=>d.events.push({revision:1})]){const d=detail();alter(d);assert.throws(()=>archive.validateDetail(d,id));}
});
test('payload pins evidence and revision; accepts literal text without HTML rendering',()=>{
 assert.deepEqual(archive.reviewPayload(record(),'CHANGES_REQUESTED','<script>literal</script>'),{expected_revision:0,report_sha256:h,status:'CHANGES_REQUESTED',note:'<script>literal</script>'});
 assert.throws(()=>archive.reviewPayload(record(),'APPROVED',''));
 assert.throws(()=>archive.reviewPayload(record(),'REVIEWED','a'.repeat(1001)));
});
class Node{
 constructor(){this.handlers={};this.children=[];this.value='';}
 addEventListener(k,fn){this.handlers[k]=fn;}setAttribute(){}focus(){}append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;}
}
const settle=()=>new Promise(r=>setImmediate(r));
function setup(){
 const nodes={};const doc={getElementById:id=>nodes[id]??=new Node(),createElement:()=>new Node()};
 let post,getDetail;const calls=[];const d=detail();
 const request=async(path,options)=>{calls.push({path,options});if(options)return post();if(path==='/api/runs')return {runs:[record()],storage};return getDetail?getDetail():structuredClone(d);};
 const controller=archive.mount(doc,request);
 return {nodes,controller,calls,post(fn){post=fn;},getDetail(fn){getDetail=fn;},async start(){controller.configure({csrf_token:'csrf',storage:{enabled:true,kind:'local-synthetic',review_is_approval:false}});await settle();await nodes['archive-list'].children[0].children[1].handlers.click();nodes['archive-review-status'].value='REVIEWED';}};
}
test('disabled storage makes no list requests and cannot save',async()=>{
 const a=setup();a.controller.configure({storage:{enabled:false}});await settle();assert.equal(a.calls.length,0);assert.equal(a.nodes['archive-save'].disabled,true);
});
test('uncertain POST retains note, blocks double click and requires explicit re-read',async()=>{
 const a=setup();await a.start();let reject;a.post(()=>new Promise((_,r)=>reject=r));a.nodes['archive-note'].value='Keep my note';
 const first=a.nodes['archive-review-form'].handlers.submit({preventDefault(){}});
 await a.nodes['archive-review-form'].handlers.submit({preventDefault(){}});
 assert.equal(a.calls.filter(c=>c.options).length,1);reject(new Error('conflict'));await first;
 assert.equal(a.nodes['archive-note'].value,'Keep my note');assert.equal(a.nodes['archive-save'].disabled,true);
 await a.nodes['archive-reload-detail'].handlers.click();assert.equal(a.nodes['archive-note'].value,'Keep my note');assert.equal(a.nodes['archive-save'].disabled,false);
 assert.equal(a.calls.filter(c=>c.options).length,1);
});
test('wrong success response never clears inputs or claims successful save',async()=>{
 const a=setup();await a.start();a.nodes['archive-note'].value='retain';a.post(async()=>detail());
 await a.nodes['archive-review-form'].handlers.submit({preventDefault(){}});
 assert.equal(a.nodes['archive-note'].value,'retain');assert.equal(a.nodes['archive-save'].disabled,true);
 assert.match(a.nodes['archive-status'].textContent,/확인하지 못했습니다/);
});
test('confirmed review checks chronology and uses CSRF before clearing note',async()=>{
 const a=setup();await a.start();a.nodes['archive-note'].value='<img src=x onerror=alert(1)>';
 a.post(async()=>{const d=detail();d.record.revision=1;d.record.review_status='REVIEWED';d.events=[{revision:1,status:'REVIEWED',note:a.nodes['archive-note'].value,created_at:'2026-11-08T00:00:00Z',report_sha256:h,event_sha256:'b'.repeat(64),previous_sha256:'0'.repeat(64)}];return d;});
 await a.nodes['archive-review-form'].handlers.submit({preventDefault(){}});
 assert.equal(a.nodes['archive-note'].value,'');assert.equal(a.nodes['archive-save'].disabled,false);
 assert.match(a.nodes['archive-events'].children[0].textContent,/<img src=x/);
 const post=a.calls.find(c=>c.options);assert.equal(post.options.headers['X-CSRF-Token'],'csrf');
 assert.equal(JSON.parse(post.options.body).expected_revision,0);
});
test('accepts server hex UUID and interleaved global ledger predecessors',()=>{
 const d=detail();d.record.run_id=d.report.run_id=id.replaceAll('-','');d.record.revision=2;d.record.review_status='CHANGES_REQUESTED';
 d.events=[1,2].map((revision,i)=>({revision,status:i?'CHANGES_REQUESTED':'REVIEWED',note:'memo',created_at:'2026-11-08',report_sha256:h,event_sha256:String(i+1).repeat(64),previous_sha256:'c'.repeat(64)}));
 assert.equal(archive.validateDetail(d,d.record.run_id).events.length,2);
});

test('historical report rejects inconsistent scope, verdicts, provenance, and timestamps',()=>{
 const mutations=[d=>d.report.synthetic_only=false,d=>d.report.created_at='other',d=>d.record.created_at='',
 d=>d.report.scope.selected_case_ids=['S02'],d=>d.report.scope.selected_total=2,d=>d.report.scope.registered_total=2,
 d=>d.report.scope.omitted_case_ids=['S01'],d=>d.report.scope.complete=false,d=>d.report.counts.FAIL=0,
 d=>d.report.counts.UNKNOWN=0,d=>d.report.readiness='PASS_WITHIN_REGISTERED_SCOPE',d=>d.report.manifest.configuration.api_version='stale',
 d=>d.report.manifest.scope.complete=false,d=>delete d.report.manifest.service_sources['rehearsal/app.py'],
 d=>d.report.manifest.api_manifest.sources['rehearsal/engine.py']='bad',d=>d.report.manifest.faq_sha256='bad',
 d=>d.report.manifest.policy_sha256.after='bad',d=>d.report.cases.push(d.report.cases[0])];
 for(const mutate of mutations){const d=detail();mutate(d);assert.throws(()=>archive.validateDetail(d,id));}
});
test('saved lists require explicit local storage, bounded unique valid records',()=>{
 assert.equal(archive.validateList({runs:[record()],storage}).runs.length,1);
 for(const data of [{runs:[record()]},{runs:[record()],storage:{...storage,enabled:false}},
 {runs:[record()],storage:{...storage,review_is_approval:true}}, {runs:[record(),record()],storage},
 {runs:Array.from({length:101},(_,i)=>({...record(),run_id:i.toString(16).padStart(32,'0')})),storage}])assert.throws(()=>archive.validateList(data));
});

test('pending detail read locks inputs and keeps their binding until response',async()=>{
 const a=setup();await a.start();a.nodes['archive-note'].value='Retain this draft';let resolve;
 a.getDetail(()=>new Promise(r=>resolve=r));
 const reading=a.nodes['archive-reload-detail'].handlers.click();
 assert.equal(a.nodes['archive-note'].disabled,true);assert.equal(a.nodes['archive-review-status'].disabled,true);
 assert.equal(a.nodes['archive-save'].disabled,true);assert.equal(a.nodes['archive-note'].value,'Retain this draft');
 resolve(detail());await reading;
 assert.equal(a.nodes['archive-note'].disabled,false);assert.equal(a.nodes['archive-review-status'].disabled,false);
 assert.equal(a.nodes['archive-note'].value,'Retain this draft');
});
