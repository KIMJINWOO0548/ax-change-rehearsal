/* Local synthetic records are evidence snapshots, never identity or approval. */
(function(root){
  'use strict';
  const statuses={UNREVIEWED:'미검토',REVIEWED:'검토함 · 승인 아님',CHANGES_REQUESTED:'수정 요청'};
  const verdicts={PASS_WITHIN_SCOPE:'범위 내 통과',FAIL:'불일치',INCONCLUSIVE:'판정 보류'};
  const version=v=>v==='corrected'?'변경 반영':'이전 정책';
  const when=value=>{const d=new Date(value);return Number.isNaN(d.getTime())?value:new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'UTC'}).format(d)+' UTC';};
  const uuid=/^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;
  const hash=/^[0-9a-f]{64}$/;
  function validRecord(r){return !!r&&typeof r.created_at==='string'&&r.created_at.trim().length>0&&uuid.test(r.run_id)&&hash.test(r.sha256)&&Number.isSafeInteger(r.revision)&&r.revision>=0&&r.review_is_approval===false&&Object.hasOwn(statuses,r.review_status);}
  const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
  const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':object(v)?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
  const same=(a,b)=>stable(a)===stable(b);
  const ids=v=>Array.isArray(v)&&v.every(id=>typeof id==='string'&&id.length>0)&&new Set(v).size===v.length;
  function hashes(value,required){
    if(!object(value))return false;
    const pairs=Object.entries(value).map(([k,v])=>[k.replaceAll(String.fromCharCode(92),'/'),v]);
    const normalized=Object.fromEntries(pairs);
    return pairs.length===Object.keys(normalized).length&&pairs.every(([,v])=>typeof v==='string'&&hash.test(v))&&required.every(k=>hash.test(normalized[k]));
  }
  function validateList(data){
    if(data?.storage?.enabled!==true||data.storage.kind!=='local-synthetic'||data.storage.review_is_approval!==false||data.storage.limit!==100||
       !Array.isArray(data.runs)||data.runs.length>100||data.runs.some(r=>!validRecord(r))||new Set(data.runs.map(r=>r.run_id)).size!==data.runs.length)
      throw new Error('저장 목록 응답이 유효하지 않습니다.');
    return data;
  }
  function validReport(p){
    if(!object(p)||p.synthetic_only!==true||typeof p.created_at!=='string'||!p.created_at.trim()||!Array.isArray(p.cases)||!p.cases.length||p.cases.some(c=>!object(c)))return false;
    const actualIds=p.cases.map(c=>c.id),s=p.scope,c=p.configuration,m=p.manifest;
    if(!ids(actualIds)||!object(s)||!ids(s.selected_case_ids)||!ids(s.omitted_case_ids)||!same(actualIds,s.selected_case_ids)||
       !Number.isSafeInteger(s.registered_total)||s.registered_total<1||!Number.isSafeInteger(s.selected_total)||
       s.selected_total!==actualIds.length||p.total!==actualIds.length||s.selected_total+s.omitted_case_ids.length!==s.registered_total||
       s.omitted_case_ids.some(id=>actualIds.includes(id))||s.complete!==(s.omitted_case_ids.length===0)||
       !object(c)||!['stale','corrected'].includes(c.faq_version)||!['stale','corrected'].includes(c.api_version)||
       (Object.hasOwn(c,'case_ids')&&!same(c.case_ids,actualIds)))return false;
    const counts={PASS_WITHIN_SCOPE:0,FAIL:0,INCONCLUSIVE:0};
    for(const item of p.cases){if(!Object.hasOwn(counts,item.business_verdict))return false;counts[item.business_verdict]++;}
    if(!object(p.counts)||Object.keys(p.counts).some(k=>!Object.hasOwn(counts,k))||Object.entries(counts).some(([k,v])=>(p.counts[k]??0)!==v))return false;
    const readiness=counts.FAIL?'BLOCKED':counts.INCONCLUSIVE?'REVIEW_REQUIRED':!s.complete?'PARTIAL_SCOPE':'PASS_WITHIN_REGISTERED_SCOPE';
    return p.readiness===readiness&&object(m)&&same(m.configuration,c)&&same(m.scope,s)&&
      hash.test(p.manifest_sha256)&&hash.test(m.registered_pack_sha256)&&hash.test(m.faq_sha256)&&hash.test(m.faq_artifact_sha256)&&
      hashes(m.policy_sha256,['before','after'])&&hash.test(m.api_manifest?.pack_digest)&&
      hashes(m.api_manifest?.sources,['rehearsal/engine.py','rehearsal/adapters.py','rehearsal/validation.py','fixtures/customer_service/policy_before.md','fixtures/customer_service/policy_after.md'])&&
      hashes(m.service_sources,['rehearsal/app.py','rehearsal/workbench.py']);
  }
  function validateDetail(data,id){
    const r=data?.record,p=data?.report;
    if(!validReport(p)||!validRecord(r)||r.created_at!==p.created_at||r.run_id!==id||p?.run_id!==id||!Array.isArray(p.cases)||!p.cases.length||p.total!==p.cases.length||
       !Array.isArray(data.events)||!p.configuration||!p.scope||!p.counts||!hash.test(p.manifest_sha256)||
       new Set(p.cases.map(c=>c.id)).size!==p.cases.length||p.cases.some(c=>typeof c.id!=='string'||!['PASS_WITHIN_SCOPE','FAIL','INCONCLUSIVE'].includes(c.business_verdict)))
      throw new Error('저장 근거 응답이 유효하지 않습니다. 검토를 저장하지 않습니다.');
    if(data.events.length!==r.revision||data.events.some((e,i)=>e.revision!==i+1||!['REVIEWED','CHANGES_REQUESTED'].includes(e.status)||typeof e.note!=='string'||[...e.note].length>1000||e.report_sha256!==r.sha256||!hash.test(e.event_sha256)||typeof e.created_at!=='string'||!hash.test(e.previous_sha256))||
       (r.revision===0?r.review_status!=='UNREVIEWED':data.events.at(-1).status!==r.review_status))
      throw new Error('검토 이력과 리비전이 일치하지 않습니다.');
    return data;
  }
  function reviewPayload(record,status,note){
    if(!validRecord(record)||!['REVIEWED','CHANGES_REQUESTED'].includes(status)||typeof note!=='string'||[...note].length>1000)
      throw new Error('검토 상태 또는 메모를 확인하세요.');
    return {expected_revision:record.revision,report_sha256:record.sha256,status,note};
  }
  function mount(document,request){
    const $=id=>document.getElementById(id);
    const state={context:null,enabled:false,detail:null,busy:false,loading:false,generation:0,uncertain:false,runs:[]};
    const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
    const notice=(text,error=false)=>{$('archive-status').textContent=text;$('archive-status').className=error?'notice error':'section-note';};
    function controls(){
      $('archive-filter').disabled=!state.enabled||state.busy||state.loading;
      $('archive-refresh').disabled=!state.enabled||state.busy||state.loading;
      $('archive-save').disabled=!state.enabled||!state.detail||state.busy||state.loading||state.uncertain;
      $('archive-reload-detail').disabled=!state.detail||state.busy||state.loading;
      $('archive-close').disabled=state.busy||state.loading;
      $('archive-note').disabled=state.busy||state.loading;
      $('archive-review-status').disabled=state.busy||state.loading;
      $('archive-save').textContent=state.busy?'저장 확인 중…':'로컬 검토 메모 저장';
      $('archive-detail').setAttribute('aria-busy',String(state.busy||state.loading));
    }
    function renderList(){
      const filter=$('archive-filter').value||'all';
      const shown=state.runs.filter(r=>filter==='all'||r.review_status===filter);
      $('archive-list').replaceChildren();
      for(const r of shown){
        const row=node('li'),content=node('span'),button=node('button','저장 근거 열기');
        const status=node('strong',statuses[r.review_status]);status.className='archive-review-badge '+r.review_status.toLowerCase();
        const time=node('span',when(r.created_at));time.className='archive-time';
        const identity=node('small','실행 '+r.run_id.slice(0,8)+' · 리비전 '+r.revision);identity.className='archive-id';
        content.append(status,time,identity);button.type='button';button.className='secondary';
        button.setAttribute('aria-label',r.run_id+' 저장 근거 열기');button.addEventListener('click',()=>open(r.run_id));
        row.append(content,button);$('archive-list').append(row);
      }
      $('archive-filter-count').textContent=shown.length+' / '+state.runs.length+'개 표시'+(!shown.length&&state.runs.length?' · 이 검토 표시에 해당하는 기록이 없습니다.':'');
    }
    function renderDetail(){
      const {record:r,report:p,events}=state.detail;
      $('archive-meta').textContent='저장 실행 '+r.run_id+'\n'+statuses[r.review_status]+' · 리비전 '+r.revision+'\nReport SHA-256 '+r.sha256+
        '\n실행 시각 '+p.created_at+' · FAQ '+p.configuration.faq_version+' / API '+p.configuration.api_version+' · '+p.total+'개';
      const summary=$('archive-summary');summary.replaceChildren();
      for(const [label,value] of [['검토 표시',statuses[r.review_status]],['실행 시각',when(p.created_at)],['검증 범위',p.scope.complete?'등록 '+p.total+'개 전체':'부분 '+p.total+' / '+p.scope.registered_total+'개'],['업무 판정','통과 '+(p.counts.PASS_WITHIN_SCOPE||0)+' · 불일치 '+(p.counts.FAIL||0)+' · 보류 '+(p.counts.INCONCLUSIVE||0)],['FAQ / API',version(p.configuration.faq_version)+' / '+version(p.configuration.api_version)]]){const pair=node('div');pair.append(node('dt',label),node('dd',value));summary.append(pair);}
      const evidence=$('archive-evidence');evidence.replaceChildren();
      for(const c of p.cases){
        const d=node('details');d.className='raw-object';d.append(node('summary',(c.label||c.id)+' · '+verdicts[c.business_verdict]));
        d.append(node('p',c.reason||'판정 사유 없음'));
        for(const e of c.evidence||[]){const item=node('p',e.quote+'\n'+e.path+':'+e.line+'\nSHA-256 '+e.sha256);item.className='mono evidence';d.append(item);}
        d.append(node('pre',JSON.stringify(c,null,2)));evidence.append(d);
      }
      const raw=node('details');raw.className='raw-object';raw.append(node('summary','저장 실행 전체 JSON · 읽기 전용'),node('pre',JSON.stringify(p,null,2)));evidence.append(raw);
      $('archive-events').replaceChildren(...events.map(e=>{
        const row=node('li'),heading=node('div');heading.className='event-heading';
        heading.append(node('strong',statuses[e.status]),node('span','리비전 '+e.revision+' · '+when(e.created_at)));
        const note=node('p',e.note||'메모 내용 없음');note.className='event-note';
        const hashes=node('details');hashes.append(node('summary','연결된 근거 hash 확인'),node('p','근거 SHA-256 '+e.report_sha256+'\n이벤트 SHA-256 '+e.event_sha256+'\n이전 이벤트 SHA-256 '+(e.previous_sha256||'없음')));
        row.append(heading,note,hashes);return row;
      }));
      if(!events.length)$('archive-events').append(node('li','검토 메모가 없습니다.'));
      $('archive-detail').hidden=false;
    }
    async function refresh(){
      if(!state.enabled||state.loading||state.busy)return;
      state.loading=true;controls();const generation=state.generation;
      try{
        const data=validateList(await request('/api/runs'));if(generation!==state.generation)return;
        if(!Array.isArray(data?.runs)||data.runs.some(r=>!validRecord(r))||new Set(data.runs.map(r=>r.run_id)).size!==data.runs.length)throw new Error('저장 목록 응답이 유효하지 않습니다.');
        state.runs=data.runs;renderList();
        notice(data.runs.length?'저장된 합성 실행 '+data.runs.length+'개. 현재 실행 결과와 별도로 열립니다.':'저장된 실행이 없습니다. 저장 모드에서 새로 실행하면 기록됩니다.');
      }catch(e){notice('저장 목록을 확인하지 못했습니다. '+e.message,true);}
      finally{state.loading=false;controls();}
    }
    async function open(id,preserve=false){
      if(!state.enabled||state.busy||state.loading)return;
      if(!preserve&&state.detail?.record.run_id!==id&&$('archive-note').value){notice('작성 중인 메모가 있습니다. 메모를 저장하거나 직접 지운 뒤 다른 기록을 여세요.',true);return;}
      if(state.detail?.record.run_id===id&&$('archive-note').value)preserve=true;
      state.loading=true;controls();const generation=state.generation;
      try{
        const data=validateDetail(await request('/api/runs/'+encodeURIComponent(id)),id);if(generation!==state.generation)return;
        state.detail=data;state.uncertain=false;renderDetail();if(!preserve){$('archive-note').value='';$('archive-review-status').value='REVIEWED';}
        notice(preserve?'최신 기록을 다시 확인했습니다. 남아 있는 입력과 이력을 비교한 뒤 저장하세요.':'과거 저장 근거를 열었습니다. 현재 실행 결과는 바뀌지 않습니다.');$('archive-detail').focus();
      }catch(e){state.uncertain=true;notice('저장 근거를 확인하지 못했습니다. '+e.message,true);}
      finally{state.loading=false;controls();}
    }
    async function save(event){
      event.preventDefault();if(!state.enabled||!state.detail||state.busy||state.loading||state.uncertain)return;
      const old=state.detail.record;let payload;
      try{payload=reviewPayload(old,$('archive-review-status').value,$('archive-note').value);}catch(e){notice(e.message,true);return;}
      state.busy=true;controls();
      try{
        const data=await request('/api/runs/'+old.run_id+'/review',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.context.csrf_token},body:JSON.stringify(payload)});
        const next=validateDetail(data,old.run_id);
        if(next.record.sha256!==old.sha256||next.record.revision!==old.revision+1||next.record.review_status!==payload.status||next.events.at(-1)?.note!==payload.note)throw new Error('저장 확인 응답이 요청과 일치하지 않습니다.');
        state.detail=next;state.runs=state.runs.map(r=>r.run_id===next.record.run_id?next.record:r);renderDetail();renderList();$('archive-note').value='';notice('로컬 검토 메모를 저장했습니다. 승인이나 배포 허가는 아닙니다. 목록은 새로고침으로 확인하세요.');
      }catch(e){state.uncertain=true;notice('저장 완료를 확인하지 못했습니다. '+e.message+' 입력은 유지했습니다. 중복 저장하지 말고 “이 기록 다시 확인”으로 최신 이력을 확인하세요.',true);}
      finally{state.busy=false;controls();}
    }
    $('archive-filter').addEventListener('change',renderList);
    $('archive-refresh').addEventListener('click',refresh);
    $('archive-review-form').addEventListener('submit',save);
    $('archive-reload-detail').addEventListener('click',()=>state.detail&&open(state.detail.record.run_id,true));
    $('archive-close').addEventListener('click',()=>{$('archive-detail').hidden=true;$('archive-refresh').focus();});
    return {configure(context){
      state.generation++;state.context=context;
      const s=context?.storage;state.enabled=!!(s?.enabled===true&&s.kind==='local-synthetic'&&s.review_is_approval===false&&context.csrf_token);
      $('archive-mode').textContent=state.enabled?'로컬 합성 저장 사용 중 · 서버 작업 폴더에 실행 근거와 검토 메모가 저장됩니다. 새로고침 후에도 이 목록에서 열 수 있습니다.':
        '로컬 저장 꺼짐 · 현재 실행은 저장되지 않습니다. 저장하려면 서버 시작 시 --workspace 전용폴더 옵션을 명시하세요. 실제 고객 자료를 넣지 마세요.';
      if(!state.enabled){state.detail=null;state.runs=[];$('archive-filter-count').textContent='';$('archive-detail').hidden=true;$('archive-list').replaceChildren();}
      controls();if(state.enabled)refresh();
    },afterRun(result){if(state.enabled){if(!validRecord(result.record)||result.record.run_id!==result.run_id)notice('실행은 완료됐지만 저장 확인 정보가 없습니다. 저장 목록에서 확인하세요.',true);else refresh();}}};
  }
  const api={validRecord,validateDetail,validateList,reviewPayload,mount};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RehearsalArchive=api;
})(globalThis);
