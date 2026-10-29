from pathlib import Path
import os
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

class Settings:
    def __init__(self, overrides=None):
        self.values = {**dotenv_values(ROOT / '.env'), **os.environ, **(overrides or {})}
        raw = Path(self.get('DATA_DIR', 'data'))
        self.data = raw if raw.is_absolute() else ROOT / raw
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    def get(self, key, default=''):
        return str(self.values.get(key) or default)
    def flag(self, key, default=False):
        return self.get(key, str(default)).lower() in ('true', '1', 'yes')
    def integer(self, key, default):
        return int(self.get(key, default))
