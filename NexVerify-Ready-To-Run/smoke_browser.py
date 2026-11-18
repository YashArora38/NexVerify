from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(__file__).resolve().parent/'output'/'verification'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, channel="msedge")
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:3000/check/quickrupee?q=QuickRupee')
    page.get_by_role('heading',name='Follow the evidence').wait_for(timeout=60000)
    page.locator('.investigation-panel').screenshot(path=str(out/'investigation-desktop.png'))
    assert page.get_by_label('Editable complaint draft').input_value()
    page.get_by_label('Editable complaint draft').fill('Reviewed demo draft; do not submit.')
    page.get_by_role('checkbox',name='I have reviewed').check()
    assert page.get_by_role('link',name='Open official complaint portal').count()==0
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.investigation-panel').screenshot(path=str(out/'investigation-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    assert not errors,errors
    print('UI passed: desktop, mobile, draft editing, demo submission guard, no JS errors.')
    browser.close()

