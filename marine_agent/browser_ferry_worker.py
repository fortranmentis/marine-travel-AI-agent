"""Read visible official KOMSA tables without private endpoint calls."""
import json
import sys

from .browser_ferries import SOURCE,OFFICES


def lookup(office):
    from playwright.sync_api import sync_playwright
    if office not in OFFICES: raise ValueError('Unknown office')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,timeout=10000)
        try:
            page=browser.new_page(locale='ko-KR',timezone_id='Asia/Seoul')
            page.set_default_timeout(15000)
            page.goto(SOURCE,wait_until='domcontentloaded',timeout=20000)
            page.locator('#jbcd').select_option(OFFICES[office])
            with page.expect_navigation(wait_until='domcontentloaded',timeout=20000):
                page.locator('#txt').get_by_role('button',name='검색',exact=True).click()
            if page.locator('#jbcd').input_value()!=OFFICES[office]: raise ValueError('Office mismatch')
            table=page.locator('#txt table')
            table.wait_for(state='visible')
            return dict(status='ok',as_of=page.get_by_text('기준시간',exact=True).locator('..').locator('span').inner_text(),
                headers=table.locator('thead th').all_text_contents(),
                rows=table.locator('tbody tr').evaluate_all('(rows)=>rows.map(r=>Array.from(r.querySelectorAll("td")).map(c=>c.textContent.trim()))'))
        finally: browser.close()


if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.read(2000));result=lookup(request['office'])
        result['headers']=[s.strip() for s in result['headers']]
    except Exception: result=dict(status='unavailable')
    print(json.dumps(result,ensure_ascii=False))
