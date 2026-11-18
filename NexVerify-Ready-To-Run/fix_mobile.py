from pathlib import Path
from playwright.sync_api import sync_playwright
css='.tech-body > div{min-width:0}.formula{overflow-wrap:anywhere}.btn{max-width:100%;white-space:normal;text-align:center}.tech-body .evs{min-width:0}.tech-body .ev{min-width:0}.tech-body .ev span{min-width:0;overflow-wrap:anywhere}'
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,channel='msedge');page=b.new_page(viewport={'width':390,'height':844});page.goto('http://127.0.0.1:3000/check/quickrupee?q=QuickRupee');page.get_by_role('heading',name='Follow the evidence').wait_for();page.add_style_tag(content=css);print(page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})'));b.close()
with Path('NexVerify-Ready-To-Run/source/frontend/app/globals.css').open('a') as f:f.write('\n'+css+'\n')
