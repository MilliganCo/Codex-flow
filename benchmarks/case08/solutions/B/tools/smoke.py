"""One finite command: all tests + three CLI modes + optional native terminal."""
from pathlib import Path
import argparse
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--terminal",action="store_true",help="also exercise native Windows ConPTY; no visible window")
    args=parser.parse_args()
    os.chdir(ROOT)
    suite=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-v"],timeout=60)
    if suite.returncode:
        return suite.returncode
    for mode in ("2d","3d","4d"):
        result=subprocess.run([sys.executable,"-m","ascii_tree","render","--mode",mode,
                               "--seed","42","--width","100","--height","40"],
                              capture_output=True,timeout=10)
        assert result.returncode == 0,result.stderr
        assert len(result.stdout)==4040
        assert all(b==10 or 32<=b<=126 for b in result.stdout)
    print("PASS: finite headless smoke (three modes, 100x40 ASCII)",flush=True)
    if args.terminal:
        return subprocess.run([sys.executable,"tools/terminal_smoke.py"],timeout=60).returncode
    return 0


if __name__=="__main__":
    raise SystemExit(main())
