"""Build a standard-library zipapp; no package downloads or model calls."""
from pathlib import Path
import shutil, tempfile, zipapp

root=Path(__file__).resolve().parents[1]
(root/'dist').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    target=Path(temp)
    shutil.copytree(root/'runtime/codex_flow',target/'codex_flow',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (target/'__main__.py').write_text('from codex_flow.cli import main\nraise SystemExit(main())\n',encoding='utf-8')
    zipapp.create_archive(target,root/'dist/codex-flow.pyz',interpreter='/usr/bin/env python3',compressed=True)
print('dist/codex-flow.pyz')
