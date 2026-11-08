const H='a'.repeat(64);
const manifest=(pack=H)=>({registered_pack_sha256:H,policy_sha256:{before:H,after:H},
 api_manifest:{pack_digest:pack,sources:Object.fromEntries(['rehearsal/engine.py','rehearsal/adapters.py','rehearsal/validation.py','fixtures/customer_service/policy_before.md','fixtures/customer_service/policy_after.md'].map(p=>[p,H]))},
 service_sources:{'rehearsal/app.py':H,'rehearsal/workbench.py':H}});
const expected=()=>({status:'DECIDED',decision:'ELIGIBLE',state_delta:{table:'return_requests',count:1}});
module.exports={H,manifest,expected};
