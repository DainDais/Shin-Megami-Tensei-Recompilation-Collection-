import sys
sys.path.insert(0, '/home/claude/emu')
from emu import Emu
from PIL import Image
cue = sys.argv[1]; state = sys.argv[2]; seq = sys.argv[3].split(','); out = sys.argv[4]
M = {'U': 'UP', 'D': 'DOWN', 'L': 'LEFT', 'R': 'RIGHT', 'C': 'CIRCLE', 'X': 'CROSS', 'T': 'TRIANGLE', 'S': 'SQUARE', 'P': 'START', 'E': 'SELECT'}
e = Emu('/home/claude/emu/pcsx_rearmed/pcsx_rearmed_libretro.so', cue)
e.load(state)
shots = []
for m in seq:
    if m == 'W': e.run(60)
    else:
        e.run(4, M[m]); e.run(30)
    shots.append(e.image())
e.save(out + '.st')
open(out + '.ram', 'wb').write(e.ram())
W, H = 320, 240; cols = 4
sheet = Image.new('RGB', (cols * W, ((len(shots) + cols - 1) // cols) * H))
for k, im in enumerate(shots):
    sheet.paste(im.resize((W, H)), ((k % cols) * W, (k // cols) * H))
sheet.save(out + '.png')
