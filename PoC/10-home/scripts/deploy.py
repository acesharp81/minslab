"""Docker CLI deploy for hosts without the Compose plugin. HOME containers only."""
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, check=True, capture=False):
    return subprocess.run(["docker", *args], cwd=ROOT, check=check, text=True, capture_output=capture)


def main():
    config = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key] = value.strip().strip("\"'")
    if not config.get("POC10_DB_PASSWORD") or not config.get("POC10_INTERNAL_SECRET"):
        raise SystemExit("HOME .env에 전용 DB 비밀번호와 내부 인증 비밀값이 필요합니다.")
    api_memory_mb = int(config.get('POC10_API_MEMORY_MB', '1536'))
    if api_memory_mb < 768:
        raise SystemExit('HOME API 메모리 한도는 768MB 이상이어야 합니다.')
    runtime = ROOT / "data" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    db_env, api_env = runtime / "db.env", runtime / "api.env"
    db_env.write_text("POSTGRES_USER=home\nPOSTGRES_DB=home\nPOSTGRES_PASSWORD=" + config["POC10_DB_PASSWORD"] + "\n")
    config["POC10_DATABASE_URL"] = "postgresql+psycopg://home:" + config["POC10_DB_PASSWORD"] + "@poc10-home-db:5432/home"
    api_env.write_text("".join(k + "=" + v + "\n" for k, v in config.items()))
    for path in (db_env, api_env):
        path.chmod(0o600)
    if run("network", "inspect", "poc10-home", check=False, capture=True).returncode:
        run("network", "create", "poc10-home")
    run("volume", "create", "poc10-home-pgdata")
    if run("container", "inspect", "poc10-home-db", check=False, capture=True).returncode:
        run("run", "-d", "--name", "poc10-home-db", "--network", "poc10-home", "--restart", "unless-stopped",
            "--env-file", str(db_env), "--memory", "1g", "-v", "poc10-home-pgdata:/var/lib/postgresql/data", "postgis/postgis:16-3.5")
    else:
        run("start", "poc10-home-db")
    ready = False
    for _ in range(30):
        if run("exec", "poc10-home-db", "pg_isready", "-U", "home", "-d", "home", check=False, capture=True).returncode == 0:
            ready = True
            break
        time.sleep(1)
    if not ready:
        raise SystemExit("HOME DB가 준비되지 않았습니다.")
    run("build", "-t", "poc10-home:local", ".")
    if run('container','inspect','poc10-home-worker',check=False,capture=True).returncode==0:
        run('stop','poc10-home-worker')
        run('rename','poc10-home-worker','poc10-home-worker-backup-'+str(int(time.time())))
    if run("container", "inspect", "poc10-home-api", check=False, capture=True).returncode == 0:
        run("stop", "poc10-home-api")
        run("rename", "poc10-home-api", "poc10-home-api-backup-" + str(int(time.time())))
    run("run", "-d", "--name", "poc10-home-api", "--network", "poc10-home", "--restart", "unless-stopped", "--init",
        "--env-file", str(api_env), '--env','POC10_AUTO_COLLECT=false', "--memory", str(api_memory_mb)+"m", "--memory-swap", str(max(2048, api_memory_mb))+"m", "-p", "127.0.0.1:18100:8000", "-v", str(ROOT / "data") + ":/app/data",
        "--health-cmd", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)\"",
        "--health-interval", "20s", "--health-retries", "5", "--health-start-period", "60s", "poc10-home:local")
    # Schema migration runs in the API entrypoint before the worker starts.
    for _ in range(60):
        state=run('exec','poc10-home-api','python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)",check=False,capture=True)
        if state.returncode==0:break
        time.sleep(1)
    else:raise SystemExit('HOME API 준비 상태를 확인할 수 없습니다. 수집 작업자는 시작하지 않았습니다.')
    run('run','-d','--name','poc10-home-worker','--network','poc10-home','--restart','unless-stopped','--init',
        '--env-file',str(api_env),'--memory','1536m','--memory-swap','2048m','--cpus','1.0',
        '-v',str(ROOT/'data')+':/app/data',
        '--health-cmd',"python -c \"import json; from datetime import datetime,timezone; from pathlib import Path; p=json.loads(Path('/app/data/runtime/collection-worker-health.json').read_text()); assert (datetime.now(timezone.utc)-datetime.fromisoformat(p['checked_at'])).total_seconds()<90; assert {'home-source-worker-LATEST','home-source-worker-BACKFILL'} <= set(p['running_threads'])\"",
        '--health-interval','30s','--health-retries','3','--health-start-period','60s',
        'poc10-home:local','python','-m','backend.collection_worker')
    run('rm','-f','poc10-home-area-worker',check=False)
    run('run','-d','--name','poc10-home-area-worker','--network','poc10-home','--restart','unless-stopped','--init',
        '--env-file',str(api_env),'--memory','1536m','--memory-swap','2048m','--cpus','0.75',
        '-v',str(ROOT/'data')+':/app/data',
        '--health-cmd',"python -c \"import json; from datetime import datetime,timezone; from pathlib import Path; p=json.loads(Path('/app/data/runtime/area-snapshots/health.json').read_text()); assert (datetime.now(timezone.utc)-datetime.fromisoformat(p['checked_at'])).total_seconds()<90\"",
        '--health-interval','30s','--health-retries','3','--health-start-period','60s',
        'poc10-home:local','python','-m','backend.area_snapshot_worker')
    print('HOME API deployed at loopback :18100; automatic collection/link/snapshot jobs run in poc10-home-worker.')


if __name__ == "__main__":
    main()
