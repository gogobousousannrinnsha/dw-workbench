"""Compatibility entry. Review images now belong outside the immutable bundle."""
import argparse
from pathlib import Path
from docuworks_integrations import render_text_maps
from docuworks_integrations.results import write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('run_dir',type=Path)
    p.add_argument('--output-dir',type=Path)
    p.add_argument('--font',type=Path)
    p.add_argument('--page',type=int)
    p.add_argument('--report',type=Path)
    p.add_argument('--overwrite',action='store_true')
    p.add_argument('--no-text-map-boxes',action='store_true')
    a=p.parse_args()
    if a.overwrite: p.error('--overwrite is no longer supported; choose a new output directory')
    output=a.output_dir or a.run_dir.resolve().with_name(a.run_dir.name+'-text-maps')
    if a.report:
        if a.report.resolve().is_relative_to(a.run_dir.resolve()): p.error('--report must be outside the bundle')
        if a.report.exists(): raise FileExistsError(a.report)
    result=render_text_maps(a.run_dir,output,font=a.font,page=a.page,draw_boxes=not a.no_text_map_boxes)
    if a.report: write_json(a.report,result)
    print(output)
    return 0


if __name__=='__main__': raise SystemExit(main())
