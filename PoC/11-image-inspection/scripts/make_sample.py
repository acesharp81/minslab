"""Deterministic diagram fixture, not AI-generated content or an accuracy benchmark."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[1]
im=Image.new('RGB',(960,960),'#f1f4eb');d=ImageDraw.Draw(im)
fontpath='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
font=lambda n:ImageFont.truetype(fontpath,n) if Path(fontpath).exists() else ImageFont.load_default(size=n)
d.rectangle((0,0,960,110),fill='#164b45');d.text((45,35),'COMMUNITY / SAFETY',font=font(30),fill='white')
d.text((125,130),'SAMPLE',font=font(52),fill='#173c37');d.text((125,205),'A safer day, together.',font=font(25),fill='#5b7466')
d.rounded_rectangle((630,275,850,410),radius=10,fill='white',outline='#bac8c0',width=2)
d.ellipse((712,310,765,363),fill='#d44140');d.arc((712,310,765,363),0,180,fill='#2d64ad',width=25)
for x,y in [(651,290),(795,290),(651,370),(795,370)]:
 for j in range(3):d.line((x,y+j*6,x+25,y+j*6),fill='#152b2b',width=3)
d.text((635,425),'SYMBOL / REVIEW',font=font(14),fill='#687f72')
for x in (190,570):
 d.ellipse((x,455,x+120,570),fill='#f0ba82');d.rounded_rectangle((x-20,550,x+150,820),radius=30,fill='#297b68' if x==190 else '#8ba9bf')
for i in range(6):d.rounded_rectangle((160+i*21,480-(i%3)*9,177+i*21,550),radius=7,fill='#f0ba82',outline='#b47b55',width=2)
d.rectangle((540,520,720,570),fill='#d6e8df');d.text((105,870),'SYNTHETIC DEMO / NOT A REAL INSPECTION',font=font(21),fill='#526b60')
im.save(root/'samples/demo.png')
