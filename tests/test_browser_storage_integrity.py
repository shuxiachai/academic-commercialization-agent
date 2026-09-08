"""Storage faults cross the real HTTP-client and language module boundaries."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["denied", "write_failure", "remove_failure", "normal", "language"])
def test_storage_faults_do_not_block_requests_or_restore_cleared_keys(scenario):
    """A successful fetch cannot repair a failed localStorage access before fetch."""
    node = shutil.which("node")
    assert node, "Node must execute the actual client; skipping loses the seam"
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8')), requests=[];
const persisted=new Map(),session=new Map();
let denyRead=input.scenario==='denied', denyWrite=input.scenario==='write_failure', denyRemove=false;
function storage(map){return {
 getItem:k=>{if(denyRead)throw Error('restricted');return map.get(k)??null;},
 setItem:(k,v)=>{if(denyWrite)throw Error('quota');map.set(k,v);},
 removeItem:k=>{if(denyRemove)throw Error('remove denied');map.delete(k);},
};}
const ctx=vm.createContext({localStorage:storage(persisted),sessionStorage:storage(session), assert, requests,
 fetch:async(url,options)=>{requests.push({url,options});return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({ok:true})};},
 document:{querySelectorAll:()=>[],documentElement:{}}});
const load=name=>vm.runInContext(fs.readFileSync(input.root+'/web/static/js/'+name,'utf8').replace(/^import .*;\r?\n/gm,'').replace(/export /g,''),ctx);
(async()=>{
 if(input.scenario==='language'){
  denyRead=true;denyWrite=true;load('i18n.js');
  assert.equal(vm.runInContext('language()',ctx),'English');
  vm.runInContext("setLanguage('Simplified Chinese')",ctx);
  assert.equal(vm.runInContext('language()',ctx),'Simplified Chinese');
  assert.equal(ctx.document.documentElement.lang,'zh-CN');return;
 }
 load('api.js');
 await vm.runInContext('health()',ctx);assert.equal(requests.length,1);
 if(input.scenario==='remove_failure'){
  vm.runInContext("setAccessCode('stale');setByok({llmKey:'old'})",ctx);
  denyRemove=true;
  assert.equal(vm.runInContext('setAccessCode(null)',ctx),false);
  assert.equal(vm.runInContext('setByok(null)',ctx),false);
  denyRemove=false;
  assert.equal(persisted.get('access-code'),'stale');
  assert.equal(vm.runInContext('getAccessCode()',ctx),null);
  assert.equal(vm.runInContext('getByok()',ctx),null);
  await vm.runInContext('health()',ctx);
  assert.equal(requests.at(-1).options.headers['X-Access-Code'],undefined);
 }else{
  vm.runInContext("setAccessCode('page-code')",ctx);
  await vm.runInContext('health()',ctx);
  assert.equal(requests.at(-1).options.headers['X-Access-Code'],'page-code');
  vm.runInContext("setByok({provider:'qwen',llmKey:'page-key',serperKey:'search-key'});setAccessCode(null)",ctx);
  assert.equal(vm.runInContext('getByok().llmKey',ctx),'page-key');
  await vm.runInContext('health()',ctx);
  assert.equal(requests.at(-1).options.headers['X-Access-Code'],undefined);
  if(input.scenario==='normal'){
   assert.equal(persisted.has('access-code'),false);
   assert.ok(session.has('byok-credentials'));assert.equal(vm.runInContext('storageDegraded()',ctx),false);
  }else assert.equal(vm.runInContext('storageDegraded()',ctx),true);
 }
})().catch(err=>{console.error(err);process.exitCode=1;});
'''
    subprocess.run([node, "-e", script], input=json.dumps({"root": str(ROOT), "scenario": scenario}),
                   text=True, encoding="utf-8", capture_output=True, timeout=30, check=True)
