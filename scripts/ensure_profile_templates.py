# -*- coding: utf-8 -*-
"""CLI / systemd ExecStartPre: закрепить profile PNG до старта бота.

Использование:
  python scripts/ensure_profile_templates.py
  # или из unit: ExecStartPre=.../python scripts/ensure_profile_templates.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    """Подтянуть PROFILES_* из .env, если systemd EnvironmentFile ещё не задал."""
    env_path = ROOT / '.env'
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip()
            if key not in ('PROFILES_DIR', 'PROFILES_PIN_DIR'):
                continue
            if key in os.environ and os.environ[key].strip():
                continue
            os.environ[key] = val.strip().strip('"').strip("'")
    except OSError:
        pass


_load_dotenv()

from services.profile_templates import REQUIRED, ensure_profile_templates, status


def main() -> int:
    ensure_profile_templates(overwrite=False)
    st = status()
    missing = [n for n, info in st['files'].items() if not info['persist']]
    print(json.dumps(st, ensure_ascii=False, indent=2))
    if missing:
        print(f'MISSING: {", ".join(missing)}', file=sys.stderr)
        return 1
    for name in REQUIRED:
        info = st['files'][name]
        print(f'OK {name} {info["persist_bytes"]} bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
