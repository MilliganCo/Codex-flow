"""Recreate the checked-in ASCII gallery and its reproducibility manifest."""
from pathlib import Path
from dataclasses import asdict
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render, export_frame


def main():
    folder=ROOT/"examples"
    folder.mkdir(exist_ok=True)
    specs=[(42,"2d",0),(42,"3d",0),(42,"4d",0),(42,"4d",45),
           (43,"2d",0),(43,"3d",0)]
    manifest=[]
    import math
    for seed,mode,angle in specs:
        options=RenderOptions(100,40,mode,angle4=math.radians(angle))
        frame=render(generate_tree(seed),options)
        name=f"seed-{seed}-{mode}"+(f"-xw-{angle}" if mode=="4d" else "")+".txt"
        export_frame(frame,folder/name)
        manifest.append({"file":name,"seed":seed,"options_radians":asdict(options),
                         "angle4_degrees":angle,"sha256":hashlib.sha256(frame.encode("ascii")).hexdigest()})
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {len(manifest)} ASCII examples, each 100x40, and manifest.json")


if __name__=="__main__":
    main()
