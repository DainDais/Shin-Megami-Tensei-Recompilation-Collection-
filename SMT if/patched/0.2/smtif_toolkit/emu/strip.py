import sys
from PIL import Image
def strip(paths,out,cols=4,scale=0.5):
    ims=[Image.open(p) for p in paths]
    ims=[im.resize((int(im.width*scale),int(im.height*scale))) for im in ims]
    w,h=ims[0].size; rows=(len(ims)+cols-1)//cols
    o=Image.new('RGB',(cols*(w+6),rows*(h+6)),(60,60,60))
    for i,im in enumerate(ims): o.paste(im,((i%cols)*(w+6),(i//cols)*(h+6)))
    o.save(out); return out
