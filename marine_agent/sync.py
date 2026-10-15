import json
from .providers import sync_catalog

if __name__ == '__main__':
    try:
        print(json.dumps(sync_catalog(), ensure_ascii=False, indent=2))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
                          'message': 'Collection incomplete. Existing snapshot was preserved.'}))
        raise SystemExit(1)
