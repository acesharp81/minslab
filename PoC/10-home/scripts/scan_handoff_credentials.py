import json,os,re,sys
from collections import Counter
from urllib.parse import quote,unquote,urlsplit
secrets={}
for key,value in os.environ.items():
 if re.search(r"KEY|SECRET|TOKEN|PASSWORD|DATABASE_URL",key) and len(value)>=8:
  vals={value,unquote(value),quote(value,safe=""),json.dumps(value)[1:-1]}
  if "DATABASE_URL" in key:
   part=urlsplit(value).password
   if part:vals.update({part,unquote(part)})
  secrets[key]={v.encode() for v in vals if len(v)>=8}
counts=Counter();patterns=Counter();seen=0
pattern=re.compile(rb"(?:[?&]|%26)(servicekey|apikey|authkey|access_token|consumer_secret|authorization|password)(?:=|%3[dD])([^&\s<>\"\\]+)",re.I)
for line in sys.stdin.buffer:
 seen+=len(line)
 for key,values in secrets.items():
  if any(value in line for value in values):counts[key]+=1
 for match in pattern.finditer(line):
  value=match.group(2).lower()
  if value not in {b"[redacted]",b"%5bredacted%5d",b"redacted",b"none",b"null"} and not value.startswith((b"{",b"%7b")):
   patterns[match.group(1).decode().lower()]+=1
result={"checked_configured_secret_names":sorted(secrets),"secret_value_matching_rows":dict(counts),"credential_query_value_candidates":dict(patterns),"logical_dump_bytes_scanned":seen,"credentials_printed":False}
print(json.dumps(result,ensure_ascii=False),flush=True)
sys.exit(1 if counts or patterns else 0)
