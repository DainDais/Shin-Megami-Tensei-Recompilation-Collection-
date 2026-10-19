import sys, random
sys.path.insert(0,'/home/claude/emu')
from emu import Emu
files=[]
for line in open('/home/claude/smtif/disc/filelist.tsv'):
    p=line.rstrip('\n').split('\t')
    if p[0]=='path': continue
    lba,size=int(p[1]),int(p[2])
    files.append((lba,lba+max(1,(size+2047)//2048),p[0]))
def name(l):
    for a,b,n in files:
        if a<=l<b: return n
    return f'?{l}'
e=Emu('/home/claude/emu/pcsx_rearmed/pcsx_rearmed_libretro.so',sys.argv[1])
e.load(sys.argv[2])
random.seed(int(sys.argv[4]) if len(sys.argv)>4 else 1)
e.cdlog()
seen=set()
for step in range(int(sys.argv[3])):
    m=random.choice(['UP','UP','UP','UP','LEFT','RIGHT','CIRCLE'])
    e.run(4,m); e.run(30)
    log=e.cdlog()
    ns=sorted(set(name(x) for x in log))
    new=[n for n in ns if n not in seen]
    if new:
        print(step, m, ns)
        seen.update(ns)
        if any(x in ns for x in ('D/F0075.BIN','D/F0076.BIN','D/F0077.BIN','D/F0084.BIN')):
            e.save(f'shots/battle_{step}.st'); e.shot(f'shots/battle_{step}.png',1)
e.save('shots/randwalk_end.st')
