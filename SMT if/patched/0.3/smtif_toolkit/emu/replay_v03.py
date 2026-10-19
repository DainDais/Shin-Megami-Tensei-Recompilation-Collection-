"""Replay from cold boot to the 2-A classroom, saving screenshots at checkpoints."""
import sys, os
sys.path.insert(0, '/home/claude/emu')
from emu import Emu
from nav import goto_opening
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
e = Emu('/home/claude/emu/pcsx_rearmed/pcsx_rearmed_libretro.so', '/home/claude/emu/game/v03.cue')
goto_opening(e)
for _ in range(10): e.tap('CIRCLE', 3, 25)
e.run(30)
for b in ['CIRCLE', 'RIGHT', 'CIRCLE', 'START']: e.tap(b, 3, 25)
n = 0
def snap():
    global n
    e.shot(f'{out}/{n:03d}.png', 1); n += 1
for k in range(48 * 2 + 60 * 2):
    e.tap('CIRCLE', 3, 25)
    if k % 2: snap()
for k in range(48):
    for _ in range(3): e.tap('CIRCLE', 3, 25)
    snap()
e.save(f'{out}/hall.bin')
def mv(seq, wait=40):
    M = {'U': 'UP', 'L': 'LEFT', 'R': 'RIGHT', 'C': 'CIRCLE', 'X': 'CROSS'}
    for m in seq:
        if m == 'W': e.run(60)
        else: e.run(4, M[m]); e.run(wait)
        snap()
mv('XXW')
mv('RUUUUUUUUUU')
mv('CCC')
mv('LUUULUUUU')
mv('UUUUUUUULUCCCC')
mv('XXWLUUUUUL', 45)
mv('RRUWLURUWLURUW', 45)
e.save(f'{out}/end.bin')
print('shots', n)
