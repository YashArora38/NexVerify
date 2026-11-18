from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
p=Path('NexVerify-Ready-To-Run/output/verification'); sheet=Image.new('RGB',(1200,1740),'#bbb')
for i,f in enumerate(sorted(p.glob('report-*.png'))):
 im=Image.open(f);im.thumbnail((390,550));x=(i%3)*400;y=(i//3)*580;sheet.paste(im,(x,y));ImageDraw.Draw(sheet).text((x+8,y+552),f.name,fill='black')
sheet.save(p/'pdf-contact-sheet.png')
