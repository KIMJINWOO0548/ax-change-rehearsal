/* Dependency-free DOM contract checks. Real browser rendering is tested separately. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {manifest,expected}=require('./comparison-fixtures.cjs');
const source=fs.readFileSync('web/app.js','utf8');
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.attrs={};this.textContent='';this.value='';this.hidden=false;this.disabled=false;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];if(this.tag==='select')this.value=nodes[0]?.value||'';}
 setAttribute(k,v){this.attrs[k]=v;} getAttribute(k){return this.attrs[k];} removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,fn){this.handlers[k]=fn;} focus(){this.focused=true;} remove(){}
 click(){return this.handlers.click?.({preventDefault(){}});}
}
const descendants=node=>node.children.flatMap(n=>[n,...descendants(n)]);
function setup({invalidPolicy=false}={}){
 const ids={},html=fs.readFileSync('web/index.html','utf8');
 for(const m of html.matchAll(/<([a-z][a-z0-9]*)\b[^>]*id="([^"]+)"/g))ids[m[2]]=new Node(m[1]);
 const radios=['faq_version','api_version'].flatMap(name=>['stale','corrected'].map(value=>Object.assign(new Node('input'),{name,value,checked:value==='stale'})));
 const links=Array.from({length:4},()=>new Node('a'));
 const policy={path:'policy.md',sha256:'hash',lines:[{number:7,text:'return rule'}]};
 const cases=[{id:'S01',label:'Case <script>',intended_behavior:'CHANGE',tags:['boundary']},{id:'S02',label:'Missing input',intended_behavior:'INDETERMINATE',tags:['missing']}];
 const context={csrf_token:'test-token',policy_review_valid:!invalidPolicy,policy:{before:policy,after:policy},defaults:{faq_version:'stale',api_version:'stale'},project:{scenario_count:2},cases,change:{old_window_days:14,new_window_days:30,effective_date:'2026-12-01',preserved:[]},limits:[]};
 const calls=[];let next=null,counter=0;
 const document={getElementById:id=>ids[id],createElement:tag=>new Node(tag),body:new Node('body'),
  querySelectorAll(selector){if(selector.includes('.rail'))return links;if(selector==='#case-rows button')return descendants(ids['case-rows']).filter(n=>n.tag==='button');if(selector.includes('input'))return radios.filter(r=>selector.includes(r.name));return[];},
  querySelector(selector){if(selector.includes('.rail'))return links[0];return radios.find(r=>r.checked&&selector.includes(r.name));}};
 const fetch=async(path,options)=>{calls.push({path,options});return path==='/api/context'?{ok:true,json:async()=>context}:next();};
 const sandbox={document,fetch,console,AbortController,setTimeout,clearTimeout,Blob,URL,Set,Map,Option:class extends Node{constructor(text,value){super('option');this.textContent=text;this.value=value;}}};
 vm.createContext(sandbox);vm.runInContext(fs.readFileSync('web/review.js','utf8'),sandbox);vm.runInContext(source,sandbox);
 const settle=()=>new Promise(resolve=>setImmediate(resolve));
 const result=()=>{
  const config=JSON.parse(calls.filter(c=>c.path==='/api/run').at(-1).options.body);
  const chosen=cases.filter(c=>config.case_ids.includes(c.id));
  const rows=chosen.map(c=>({...c,business_verdict:c.id==='S01'?'FAIL':'INCONCLUSIVE',assertion_status:c.id==='S01'?'FAIL':'PASS',
    input:{id:c.id},faq:{response:{decision:'NEEDS_INPUT'},assertion_status:'FAIL'},
    candidate:{expected:expected(),response:{decision:'NEEDS_INPUT'},observed_state:[],assertion_status:'FAIL'},
    baseline:{expected:expected()},evidence:[],reason:'missing'}));
  const counts={};rows.forEach(c=>counts[c.business_verdict]=(counts[c.business_verdict]||0)+1);
  return {run_id:'r'+(++counter),created_at:'now',configuration:config,manifest_sha256:'hash',
    manifest:manifest(),
    scope:{registered_total:2,selected_total:chosen.length,selected_case_ids:config.case_ids,omitted_case_ids:cases.filter(c=>!config.case_ids.includes(c.id)).map(c=>c.id),complete:chosen.length===2},
    readiness:counts.FAIL?'BLOCKED':'REVIEW_REQUIRED',counts,total:chosen.length,limits:[],cases:rows};
 };
 return {ids,calls,settle,result,run:()=>ids['run-form'].handlers.submit({preventDefault(){}}),setNext:fn=>{next=fn;},good:()=>({ok:true,json:async()=>result()}),
   change(name,value){radios.filter(r=>r.name===name).forEach(r=>r.checked=r.value===value);ids['run-form'].handlers.change();}};
}
test('request headers, selected scope, duplicate guard, invalidation, failure and retry',async()=>{
 const s=setup();await s.settle();assert.equal(s.ids.run.disabled,false);let resolve;s.setNext(()=>new Promise(r=>resolve=r));const pending=s.run();await s.run();
 assert.equal(s.calls.filter(c=>c.path==='/api/run').length,1);assert.equal(s.ids.run.disabled,true);resolve(s.good());await pending;
 assert.equal(s.ids.download.disabled,false);assert.equal(s.ids['case-rows'].children.length,2);
 assert.equal(s.calls[1].options.headers['X-CSRF-Token'],'test-token');
 assert.deepEqual(JSON.parse(s.calls[1].options.body),{faq_version:'stale',api_version:'stale',case_ids:['S01','S02']});
 s.change('faq_version','corrected');assert.equal(s.ids.download.disabled,true);assert.match(s.ids['run-status'].textContent,/이전 실행/);
 s.setNext(async()=>({ok:false,json:async()=>({error:{message:'test failed'}})}));await s.run();
 assert.match(s.ids['run-status'].textContent,/test failed/);assert.equal(s.ids.run.disabled,false);assert.equal(s.ids.download.disabled,true);
 s.setNext(async()=>s.good());await s.run();assert.equal(s.ids.download.disabled,false);assert.match(s.ids['run-status'].textContent,/실행 완료/);
});
test('discard changed-revision response and stop busy state',async()=>{
 const s=setup();await s.settle();let resolve;s.setNext(()=>new Promise(r=>resolve=r));const pending=s.run();s.change('api_version','corrected');resolve(s.good());await pending;
 assert.equal(s.ids.download.disabled,true);assert.equal(s.ids['case-rows'].children.length,0);assert.equal(s.ids.run.disabled,false);
 assert.match(s.ids['run-status'].textContent,/응답을 사용하지/);
});
test('changed policy blocks requests',async()=>{
 const s=setup({invalidPolicy:true});await s.settle();assert.equal(s.ids.run.disabled,true);assert.match(s.ids['run-status'].textContent,/정책 문서/);await s.run();assert.equal(s.calls.length,1);
});
test('empty selection cannot run and partial selection sends only chosen cases',async()=>{
 const s=setup();await s.settle();s.ids['select-none'].click();assert.equal(s.ids.run.disabled,true);await s.run();assert.equal(s.calls.length,1);
 s.ids['select-boundary'].click();assert.equal(s.ids.run.disabled,false);assert.match(s.ids['scope-warning'].textContent,/S02/);
 s.setNext(async()=>s.good());await s.run();assert.equal(JSON.parse(s.calls.at(-1).options.body).case_ids.join(),'S01');
 assert.match(s.ids['result-scope'].textContent,/부분 실행/);assert.equal(s.ids.download.disabled,false);
});
test('search changes visible rows without silently changing selection',async()=>{
 const s=setup();await s.settle();s.ids['case-search'].value='missing';s.ids['case-search'].handlers.input();
 assert.equal(s.ids['scenario-list'].children.length,1);s.setNext(async()=>s.good());await s.run();
 assert.equal(JSON.parse(s.calls.at(-1).options.body).case_ids.length,2);
});
test('mismatched result scope and counts fail closed',async()=>{
 for(const mutate of [r=>r.scope.complete=false,r=>r.counts.FAIL=99,r=>r.cases.pop(),r=>r.readiness='PASS_WITHIN_REGISTERED_SCOPE']){
  const s=setup();await s.settle();s.setNext(async()=>({ok:true,json:async()=>{const r=s.result();mutate(r);return r;}}));await s.run();
  assert.equal(s.ids.download.disabled,true);assert.match(s.ids['run-status'].textContent,/실행하지 못/);
 }
});
test('failure-only rerun is explicit selection and differing scopes cannot compare',async()=>{
 const s=setup();await s.settle();s.setNext(async()=>s.good());await s.run();s.ids['select-failed'].click();
 assert.equal(s.ids.download.disabled,true);assert.match(s.ids['scope-warning'].textContent,/S02/);await s.run();
 assert.match(s.ids['comparison-summary'].textContent,/시나리오가 다릅니다/);assert.equal(s.ids['change-filter'].disabled,true);
});
test('history is bounded and detail close returns focus to its trigger',async()=>{
 const s=setup();await s.settle();s.setNext(async()=>s.good());for(let i=0;i<10;i++)await s.run();
 assert.equal(s.ids['compare-run'].children.length,8);
 const button=descendants(s.ids['case-rows']).find(n=>n.tag==='button');button.click();
 assert.equal(s.ids['case-detail'].hidden,false);s.ids['close-detail'].click();
 assert.equal(s.ids['case-detail'].hidden,true);assert.equal(descendants(s.ids['case-rows']).find(n=>n.tag==='button').focused,true);
});
test('no dynamic HTML or external dependencies in shipped UI',()=>{
 const html=fs.readFileSync('web/index.html','utf8');assert.doesNotMatch(source,/innerHTML|outerHTML|eval\(/);
 assert.doesNotMatch(html,/https?:\/\//);assert.doesNotMatch(fs.readFileSync('web/app.css','utf8'),/@import|https?:\/\//);
});

test('missing omitted cases cannot conceal unexecuted scope',async()=>{
 const s=setup();await s.settle();s.ids['select-boundary'].click();
 s.setNext(async()=>({ok:true,json:async()=>{const r=s.result();r.scope.omitted_case_ids=[];return r;}}));
 await s.run();assert.equal(s.ids.download.disabled,true);assert.match(s.ids['run-status'].textContent,/실행하지 못/);
});
