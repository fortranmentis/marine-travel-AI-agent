import json
import argparse
from .providers import sync_catalog

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Collect tourism and marine forecasts atomically.')
    parser.add_argument('--scope',choices=['coastal','incheon'],default='coastal')
    parser.add_argument('--all-marine',action='store_true',help='Refresh all eight marine feeds; otherwise coastal scope requires sea-travel only.')
    args=parser.parse_args()
    try:
        print(json.dumps(sync_catalog(scope=args.scope,all_marine=args.all_marine), ensure_ascii=False, indent=2))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'message': 'Collection incomplete. Existing snapshot was preserved.'}))
        raise SystemExit(1)
