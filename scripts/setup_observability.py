"""Generate local observability secrets without overwriting existing credentials."""
import json
from pathlib import Path
import secrets
from marine_agent.config import ROOT,DATA

def main():
 path=ROOT/'.env'
 if not path.exists():raise SystemExit('Copy .env.example to .env and configure external credential paths first.')
 text=path.read_text(encoding='utf-8-sig')
 existing={k.strip():v.strip().strip('"').strip("'") for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#') and '=' in line for k,v in [line.split('=',1)]}
 values={'LANGFUSE_ENABLED':'true','LANGFUSE_BASE_URL':'http://127.0.0.1:3000','LANGFUSE_PUBLIC_URL':'http://127.0.0.1:3000','LANGFUSE_PUBLIC_KEY':'pk-lf-'+secrets.token_hex(16),'LANGFUSE_SECRET_KEY':'sk-lf-'+secrets.token_hex(24),'LF_DB_PASSWORD':secrets.token_hex(24),'LF_CLICKHOUSE_PASSWORD':secrets.token_hex(24),'LF_REDIS_PASSWORD':secrets.token_hex(24),'LF_MINIO_PASSWORD':secrets.token_hex(24),'LF_SALT':secrets.token_hex(24),'LF_ENCRYPTION_KEY':secrets.token_hex(32),'LF_NEXTAUTH_SECRET':secrets.token_hex(32),'LF_USER_PASSWORD':secrets.token_urlsafe(32)+'Aa1!','OPS_TOKEN':secrets.token_urlsafe(32),'SYNC_TOKEN':secrets.token_urlsafe(32)}
 for key,value in values.items():
  if existing.get(key):continue
  lines=[line for line in text.splitlines() if not line.startswith(key+'=')]
  text='\n'.join(lines)+'\n'+key+'='+value+'\n';existing[key]=value
 path.write_text(text,encoding='utf-8')
 DATA.mkdir(parents=True,exist_ok=True)
 login=DATA/'langfuse-local-login.json'
 if not login.exists():login.write_text(json.dumps({'email':'marine.operator@localhost.invalid','password':existing['LF_USER_PASSWORD']},indent=2),encoding='utf-8')
 print('Observability configured. Secrets remain in ignored .env; local login: data/langfuse-local-login.json')
if __name__=='__main__':main()
