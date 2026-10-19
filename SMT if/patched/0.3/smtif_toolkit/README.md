# SMT if... English translation toolkit (v0.3)

The tools and English translation files used to build the v0.3 patch. There's no game
data here and no Japanese script: `tools/dump_script.py` regenerates the script from your
own disc.

## Building the patched disc

```sh
python3 tools/iso_extract.py original.bin disc          # extract the disc into disc/
python3 tools/census.py                                  # glyph usage census (optional, already included)
python3 tools/make_patch.py original.bin patched.bin     # text, fonts, graphics, exe patches
python3 tools/fmv_patch.py original.bin patched.bin work # English opening scroll (Java + jPSXdec)
python3 tools/make_ppf.py original.bin patched.bin out.ppf "description"
```

`make_patch.py` takes 5–10 minutes; most of that is choosing the string order that
compresses best, and the result is cached in `tools/.order_cache.pkl`. `fmv_patch.py`
needs Java and [jPSXdec](https://github.com/m35/jpsxdec): set `JPSXDEC` to the jar or a
directory of compiled classes.

## Translation files (`trans/`)

Every file maps string numbers to English. Control codes are written `{ff03}` (newline),
`{ff01}` (wait for button), `{ff02}` (clear) and so on; see the table below. Line wrapping
is automatic, and `make_patch.py` warns about lines or pages that don't fit.

| File | Contents | Where it lives on the disc |
|---|---|---|
| `F0016_u*_b1.json` | First-chapter event script | `D/F0016.BIN` units (repacked, moved to `ZZZ.BIN`) |
| `F0018_o*.json` | School map events | `D/F0018.BIN` |
| `F0017_b0/b1/b2.json` | Menus, ally farewells, party-full prompts | `D/F0017.BIN` fixed slots |
| `F0094_b0..b6.json` | Partner names, demons, items, item descriptions, spells, spell descriptions, races | `D/F0094.BIN` block chain |
| `F0075_b0.json` | Battle messages | `D/F0075.BIN` |
| `F0076_o01814/o02a1c/o02c7c.json` | Demon negotiation narration, results, answer choices | `D/F0076.BIN` |
| `F0043_b0.json` | Cathedral of Shadows | `D/F0043.BIN` |
| `F0049_t798c.json` | Shops, healers, MAG dealer, jewel trader, appraiser | string table inside the `D/F0049.BIN` code overlay |
| `F0088_t42b4.json` | Title-screen memory card prompts | string table inside the `D/F0088.BIN` code overlay |
| `EXE_t0..t5.json` | System and field messages, status labels, memory card, Analyze, config help | six tables in `SLPM_871.53` |
| `tiles.json` | Output: the tile (glyph code) chosen for each letter sequence | written by `make_patch.py` |

`fmv/opening_text.json` holds the lines and positions of the opening text scroll.

## Graphics and code patches

| What | Tool / place | Notes |
|---|---|---|
| Opening scroll | `tools/fmv_opening.py`, `tools/fmv_patch.py` | `D/F0099.BIN` is an STR movie (MDEC, 15 fps). The Japanese text is masked, English is drawn at the same 0.5 px/frame scroll, and jPSXdec re-encodes only the changed macroblocks. |
| Fiction disclaimer | `tools/disclaimer.py` | `D/F0083.BIN`: RLE 0x102 picture followed by its CLUT block. A smaller picture gets its own block size, and the CLUT moves up behind it. |
| Name-entry keyboard | `tools/namegrid.py` | `D/F0073.BIN` is a 156×208 4-bpp picture of the 13×16 keyboard plus the cursor sprites. Input reads the Shift-JIS grid in the exe (`0x15014`), so the two are kept in step. |
| Name characters | `make_patch.py` | Shift-JIS → glyph tables (`0x800F33F0`, `0x800F3558`) map full-width letters to the English tiles. |
| Names in the party panel | `make_patch.py` (`HUD_SEG`, `g2s_code`) | The party panel draws names in a small Shift-JIS font, after the glyph → Shift-JIS function at `0x8004AE8C` (also used by the joke-name check and the memory card title). That function is rewritten so name tiles expand to their letters, in capitals (the small font has none in lower case), up to eight characters (the panel stops drawing names longer than that). Partner and demon names use tiles of at most 4 letters, placed on little-used kanji codes inside one 340-code window; a 4-bytes-per-code table in the exe gives their letters. |
| Exe message tables | `make_patch.py`, `tools/textsrc.py` | Repacked in their region (`0xE5B78`–`0xE853C`); the pointer array and the boot code that registers them (`0x8006A404`) are updated. |

## Text encoding

| Code | Meaning |
|---|---|
| `0x000`–`0x108` | kana and punctuation |
| `0x109`–`0x55B` | kanji; English tiles reuse the least-used ones (see `tools/glyph_census.json`) |
| `FF01` / `FF02` / `FF03` | wait for button / clear page / newline |
| `FF04` / `FF05` | player name / partner name |
| `FF18`, `FF19`, `FF6F`, `FF70`, `FF77` | demon / actor names |
| `FF1B`, `FF7A` | item name |
| `FF67`, `FF68` | race |
| `FF71`, `FF76`, `FF88` | numbers |
| `FF7B` | spell name |
| `FF7C` / `FF92` | timed pause / timed end |
| `FF72` | continue (prompt) |
| `FFFE` | wide space |
| `FFFF` | end of string |

Limits that matter when editing:
- Demon and item names can use at most 8 glyph codes, and other names at most as many as the longest Japanese name in their table.
- Menu strings can use at most 11 glyph codes.
- `F0094` tables must stay in id order without shared bodies.

## Emulator harness (`emu/`)

`emu.py` is a headless libretro frontend for PCSX-ReARMed (build the core with
`build_core.sh`): scripted input, screenshots, RAM access and disc-read logs.
`replay_v03.py` plays from a cold boot into the school; `menu_probe.py` opens menus from
a save state.
