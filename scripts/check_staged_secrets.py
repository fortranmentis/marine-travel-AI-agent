"""Reject staged contents containing any key from the supplied credential document."""
import argparse
import subprocess
import urllib.parse

from check_data_connections import load_credentials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', required=True)
    args = parser.parse_args()
    keys = [entry['key'] for entry in load_credentials(args.credentials)]
    paths = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z']).decode().split('\0')
    for path in filter(None, paths):
        body = subprocess.check_output(['git', 'show', ':' + path])
        if any(key.encode() in body or urllib.parse.quote(key, safe='').encode() in body for key in keys):
            print('FAILED: supplied credential detected in staged contents. Nothing should be pushed.')
            return 1
    print('PASS: supplied credential values absent from staged contents.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
