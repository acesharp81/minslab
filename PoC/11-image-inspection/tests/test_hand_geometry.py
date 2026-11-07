import numpy as np
from PIL import Image,ImageDraw
from app.hand_geometry import measure

def icon(fingers):
    im=Image.new('RGB',(500,600),'white');d=ImageDraw.Draw(im);color=(235,170,130)
    d.rounded_rectangle((185,240,365,470),radius=40,fill=color)
    d.rounded_rectangle((220,435,330,550),radius=18,fill=color)
    # Distinct protrusions with natural gaps; no fixture image/answer coordinates.
    for i in range(fingers):
        x=205+i*(140/(fingers-1));top=85+abs(i-(fingers-1)/2)*28
        d.rounded_rectangle((x-10,top,x+10,300),radius=10,fill=color)
    d.polygon([(120,285),(205,335),(220,365),(110,315)],fill=color)
    d.ellipse((95,270,132,315),fill=color)
    return im

def test_extra_protrusion_measured_without_warning_on_five_or_unmeasurable():
    assert measure(icon(4))['visible_protrusions']==5
    assert measure(icon(5))['visible_protrusions']==6
    assert measure(icon(5).crop((200,0,500,600))) is None
    assert measure(Image.new('RGB',(500,600),'white')) is None
    assert measure(Image.fromarray(np.random.default_rng(123).integers(0,255,(200,200,3),dtype=np.uint8))) is None
