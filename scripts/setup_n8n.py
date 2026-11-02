"""Bootstrap this new local-only n8n instance. Secrets are never printed/exported."""
import json
import os
from pathlib import Path
import secrets
import sys
import httpx
from marine_agent.config import ROOT,DATA,load_env
load_env()

def main():
 base=os.environ.get('N8N_LOCAL_URL','http://127.0.0.1:5678')
 if base not in ('http://127.0.0.1:5678','http://localhost:5678'):raise ValueError('Local n8n only')
 loginfile=DATA/'n8n-local-login.json';DATA.mkdir(exist_ok=True,parents=True)
 with httpx.Client(base_url=base,timeout=30,trust_env=False) as c:
  r=c.get('/rest/settings');r.raise_for_status();setup=r.json()['data']['userManagement']['showSetupOnFirstLoad']
  if setup:
   login=dict(email='marine.operator@localhost.invalid',password=secrets.token_urlsafe(32)+'Aa1!')
   # A newly provisioned local account, not an existing user password change.
   r=c.post('/rest/owner/setup',json=dict(firstName='Marine',lastName='Operator',**login));r.raise_for_status()
   loginfile.write_text(json.dumps(login),encoding='utf-8')
  elif loginfile.exists():
   login=json.loads(loginfile.read_text());r=c.post('/rest/login',json=dict(emailOrLdapLoginId=login['email'],password=login['password']));r.raise_for_status()
  else:raise RuntimeError('Existing n8n owner: configure/import through your existing account; no credentials changed')
  r=c.get('/rest/credentials');r.raise_for_status();existing=r.json().get('data',[])
  credential=next((d for d in existing if d['name']=='Marine Sync API'),None)
  if credential is None:
   r=c.post('/rest/credentials',json=dict(name='Marine Sync API',type='httpHeaderAuth',data={'name':'Authorization','value':'Bearer '+os.environ['SYNC_TOKEN']}));r.raise_for_status();credential=r.json()['data']
  workflow=json.loads((ROOT/'workflows'/'marine-refresh.json').read_text())
  workflow.pop('id',None);workflow.pop('active',None)
  for node in workflow['nodes']:
   if 'credentials' in node:node['credentials']['httpHeaderAuth']['id']=credential['id']
  r=c.get('/rest/workflows');r.raise_for_status();items=r.json().get('data',[])
  existing=next((v for v in items if v['name']==workflow['name']),None)
  if existing:workflow_id=existing['id']
  else:
   r=c.post('/rest/workflows',json=workflow);r.raise_for_status();workflow_id=r.json()['data']['id']
  evidence=ROOT/'.tmp'/'n8n-setup.json';evidence.parent.mkdir(exist_ok=True);evidence.write_text(json.dumps({'workflow_id':workflow_id}),encoding='utf-8')
  print('n8n local owner and workflow ready. Login saved only to ignored data/n8n-local-login.json.')
  print('Workflow ID:',workflow_id)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('n8n bootstrap failed:',type(e).__name__)
  if isinstance(e,httpx.HTTPStatusError):print('Endpoint:',e.request.url.path,'HTTP:',e.response.status_code,'response keys:',list(e.response.json()))
  sys.exit(1)
