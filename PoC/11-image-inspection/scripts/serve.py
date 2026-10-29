from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
import uvicorn
s=Settings()
uvicorn.run('app.main:create_app',factory=True,host=s.get('HOST','127.0.0.1'),port=s.integer('PORT',18110),workers=1)
