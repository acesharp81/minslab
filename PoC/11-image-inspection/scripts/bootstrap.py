"""Create local secrets without overwriting API keys or existing settings."""
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values, set_key
root=Path(__file__).resolve().parents[1];env=root/'.env'
if not env.exists():env.write_text((root/'.env.example').read_text())
values=dotenv_values(env)
for key in ('REVIEWER_PASSWORD','ADMIN_PASSWORD','SESSION_SECRET'):
    if not values.get(key):set_key(env,key,secrets.token_urlsafe(24))
env.chmod(0o600)
print('Ready. Login passwords and API key fields are in .env (values never printed).')
