/* Dependency-free state/DOM contract tests. Not a replacement for browser QA. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web/app.js','utf8');
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.attrs={};this.textContent='';this.value='';this.hidden=false;this.disabled=false;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];if(this.tag==='select')this.value=nodes[0]?.value;}
 setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,fn){this.handlers[k]=fn;}focus(){this.focused=true;}remove(){}click(){return this.handlers.click?.({preventDefault(){}});}
}
function setup({invalidPolicy=false}={}){
 const ids={};const html=fs.readFileSync('web/index.html','utf8');for(const match of html.matchAll(/id="([^"]+)"/g))ids[match[1]]=new Node(match[1]==='verdict-filter'?'select':'div');
 const radios=['faq_version','api_version'].flatMap(name=>['stale','corrected'].map(value=>Object.assign(new Node('input'),{name,value,checked:value==='stale'})));
 const links=Array.from({length:3},()=>new Node('a'));
 const policy={path:'policy.md',sha256:'hash',lines:[{number:1,text:'return rule'}]};
 const context={csrf_token:'test-token',policy_review_valid:!invalidPolicy,policy:{before:policy,after:policy},defaults:{faq_version:'stale',api_version:'stale'},project:{scenario_count:1},change:{old_window_days:14,new_window_days:30,effective_date:'2026-12-01',preserved:[]},limits:[]};
 const calls=[];let next=null;
 const document={getElementById:id=>ids[id],createElement:tag=>new Node(tag),body:new Node('body'),querySelectorAll(selector){if(selector.includes('.rail'))return links;if(selector.includes('input'))return radios.filter(r=>selector.includes(r.name));return[];},querySelector(selector){if(selector.includes('.rail'))return links[0];return radios.find(r=>r.checked&&selector.includes(r.name));}};
 const fetch=async(path,options)=>{calls.push({path,options});return path==='/api/context'?{ok:true,json:async()=>context}:next();};
 const sandbox={document,fetch,console,AbortController,setTimeout,clearTimeout,Blob,URL,Option:class extends Node{constructor(text,value){super('option');this.textContent=text;this.value=value;}}};
 vm.runInNewContext(source,sandbox);
 const settle=()=>new Promise(resolve=>setImmediate(resolve));
 const config=()=>Object.fromEntries(radios.filter(r=>r.checked).map(r=>[r.name,r.value]));
 const result=()=>({run_id:'r1',created_at:'now',configuration:config(),manifest_sha256:'hash',readiness:'REVIEW_REQUIRED',counts:{INCONCLUSIVE:1},total:1,limits:[],cases:[{id:'case1',label:'Case <script>',business_verdict:'INCONCLUSIVE',assertion_status:'PASS',input:{},intended_behavior:'INDETERMINATE',faq:{response:{decision:'NEEDS_INPUT'}},candidate:{response:{decision:'NEEDS_INPUT'},observed_state:[]},baseline:{},evidence:[],reason:'missing'}]});
 return {ids,calls,settle,run:()=>ids['run-form'].handlers.submit({preventDefault(){}}),setNext:fn=>{next=fn;},good:()=>({ok:true,json:async()=>result()}),change(name,value){radios.filter(r=>r.name===name).forEach(r=>r.checked=r.value===value);ids['run-form'].handlers.change();}};
}
test('real request headers, duplicate guard, stale invalidation, failure and retry',async()=>{
 const s=setup();await s.settle();assert.equal(s.ids.run.disabled,false);let resolve;s.setNext(()=>new Promise(r=>resolve=r));const pending=s.run();await s.run();assert.equal(s.calls.filter(c=>c.path==='/api/run').length,1);assert.equal(s.ids.run.disabled,true);resolve(s.good());await pending;
 assert.equal(s.ids.download.disabled,false);assert.equal(s.ids['case-rows'].children.length,1);assert.equal(s.calls[1].options.headers['X-CSRF-Token'],'test-token');assert.equal(s.calls[1].options.body,'{"faq_version":"stale","api_version":"stale"}');
 s.change('faq_version','corrected');assert.equal(s.ids.download.disabled,true);assert.match(s.ids['run-status'].textContent,/이전 실행/);
 s.setNext(async()=>({ok:false,json:async()=>({error:{message:'test failed'}})}));await s.run();assert.match(s.ids['run-status'].textContent,/test failed/);assert.equal(s.ids.run.disabled,false);assert.equal(s.ids.download.disabled,true);
 s.setNext(async()=>s.good());await s.run();assert.equal(s.ids.download.disabled,false);assert.match(s.ids['run-status'].textContent,/실행 완료/);
});
test('discard response if configuration revision changed during request',async()=>{const s=setup();await s.settle();let resolve;s.setNext(()=>new Promise(r=>resolve=r));const pending=s.run();s.change('api_version','corrected');resolve(s.good());await pending;assert.equal(s.ids.download.disabled,true);assert.equal(s.ids['case-rows'].children.length,0);});
test('changed policy blocks requests',async()=>{const s=setup({invalidPolicy:true});await s.settle();assert.equal(s.ids.run.disabled,true);assert.match(s.ids['run-status'].textContent,/정책 문서/);await s.run();assert.equal(s.calls.length,1);});
test('no dynamic HTML or external dependencies in shipped UI',()=>{const html=fs.readFileSync('web/index.html','utf8');assert.doesNotMatch(source,/innerHTML|outerHTML|eval\(/);assert.doesNotMatch(html,/https?:\/\//);assert.doesNotMatch(fs.readFileSync('web/app.css','utf8'),/@import|https?:\/\//);});
