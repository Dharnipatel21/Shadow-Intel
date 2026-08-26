import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app import store
store.init(force=True)
print(f'Reset and reseeded {store.DB}')
