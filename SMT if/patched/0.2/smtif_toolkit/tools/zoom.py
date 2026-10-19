import sys
from PIL import Image, ImageDraw
data=open('font_raw.bin','rb').read()
gl=[int(x,16) for x in sys.argv[2].split(',')]
scale=10; cw,ch=14*scale+10,12*scale+18
img=Image.new('L',(len(gl)*cw,ch),255); dr=ImageDraw.Draw(img)
for i,g in enumerate(gl):
    base=g*48
    for y in range(12):
        for x in range(14):
            v=(data[base+(y*32+x*2)//8]>>((y*32+x*2)%8))&3
            c=[0,85,170,255][v]
            if c<255: dr.rectangle([i*cw+x*scale,16+y*scale,i*cw+x*scale+scale-1,16+y*scale+scale-1],fill=c)
    dr.text((i*cw,0),f'{g:03x}',fill=0)
img.save(sys.argv[1])
