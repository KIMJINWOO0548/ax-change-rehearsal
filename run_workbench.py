#!/usr/bin/env python3
"""Generate a local synthetic workbench; no HTTP server or external writes."""
import argparse
import json
from pathlib import Path

from rehearsal.report import render_html
from rehearsal.workbench import build_workbench, load_faq


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/workbench'))
    parser.add_argument('--stale-faq', type=Path)
    parser.add_argument('--corrected-faq', type=Path)
    args = parser.parse_args()
    result = build_workbench(load_faq(args.stale_faq) if args.stale_faq else None,
                             load_faq(args.corrected_faq) if args.corrected_faq else None)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'index.html').write_text(render_html(result), encoding='utf-8')
    (args.output / 'workbench.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(args.output / 'index.html')
    for stage in result['stages']:
        print(stage['title'], stage['readiness'], stage['counts'])


if __name__ == '__main__':
    main()
