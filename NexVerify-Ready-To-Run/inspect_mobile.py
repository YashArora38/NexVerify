from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,channel='msedge');page=b.new_page(viewport={'width':390,'height':844});page.goto('http://127.0.0.1:3000/check/quickrupee?q=QuickRupee');page.get_by_role('heading',name='Follow the evidence').wait_for();print(page.evaluate('JSON.stringify([...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>395 && !e.closest(".table-scroll")).map(e=>({tag:e.tagName,cls:e.className,w:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right})).slice(0,25))'));b.close()

