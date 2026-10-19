"""Scripted navigation from cold boot."""
def goto_opening(e, settle=800):
    e.run(2020)
    for _ in range(4):
        e.tap('START', 4, 150)
    e.tap('CIRCLE', 4, 120)   # YES (no memory card)
    e.tap('CIRCLE', 4, 120)   # NORMAL
    e.tap('DOWN', 4, 30)
    e.tap('CIRCLE', 4, 200)   # NO (don't load clear data)
    e.run(settle)
