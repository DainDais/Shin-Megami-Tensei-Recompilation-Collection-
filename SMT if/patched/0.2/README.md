# Shin Megami Tensei if... (PS1) — English translation v0.2 (school chapter)

## Applying the patch

- **Base image:** `Shin Megami Tensei If... (Japan) (Anniversary Pack).bin`, a single-track MODE2/2352 BIN/CUE. Its CRC32 must be `D77E3D8F`.
- **Patches** (both produce the same image):
  - `SMTif_PS1_English_v0.2.xdelta` (preferred). Built without secondary compression, so it works in Rom Patcher JS, Delta Patcher, or `xdelta3 -d -s original.bin patch.xdelta out.bin`.
  - `SMTif_PS1_English_v0.2.ppf`, the same changes in PPF 3.0 format.
- Apply to the **original** image, not to the v0.1 proof-of-concept output.
- Keep your original `.cue` file and point it at the patched `.bin`.
- Patched CRC32: `137C1A05`.

Share only the patch files, never the disc image.

## What's translated

- **The whole first-chapter event script** (event file `F0016`, script 0: 709 strings, 497 unique lines). That covers:
  - The opening: Nova, the fortune-teller questions and results, the Demon Emperor's speech, the classroom panic.
  - Recruiting Yumi, Reiko, Charlie or Akira, including the "come with me?" prompts and the refusal lines.
  - Every student, teacher and staff conversation in the school: Mr. Yahata and the Arm Terminal, Ms. Kayama in the nurse's office, Sato and the save system, the principal, the custodian, the club rooms, the music room and the hall monitors.
  - Mr. Ootsuki and his "no scientific basis" speeches, the astral body of Hazama, Ryuichi and Akiko, and the Demon Emperor.
  - The Realms of Gluttony and Greed, Orcus and the cooks, the casino (all game explanations), the Chamber of Seals, and the chapter endings.
- **The school map events** (`F0018`, 119 strings): Akira's introduction, the floppy disk in the hallway, Sato's program and STEVEN, the demon escaping the disk, the astral body, and the hall monitors blocking the exits.
- **The fortune-teller answer menus** (`F0017`).

Tested in an emulator from a cold boot: name entry, all fortune-teller questions, the opening, Yumi's recruitment, the floppy disk event and a classroom conversation. See `SMTif_English_v0.2_screenshots.png`.

## Known limitations

- **System messages are still Japanese.** These are the top-bar messages such as "ＣＯＭＰを持っていない" ("You don't have a COMP"), plus the COMP, item and magic prompts. They live in a string table inside the executable and are the next target.
- **Battles and demon negotiation are still Japanese.** That's `F0076` (battle messages) and `F0077` (demon conversations, about 2,500 lines), plus the encounter text in the dungeon files.
- **Item, demon and skill names are still Japanese.** These are inserted into English sentences at run time, so lines like "You got [item]." show the Japanese name.
- **A few kanji in untranslated text are replaced.** English uses 600 glyph slots taken from kanji that appear 12 times or fewer in the remaining Japanese text. Untranslated screens will occasionally show an English fragment in place of one of those kanji.
- **Name entry still uses the kana grid.** Enter a real name: the game rejects names like "ああああ".
- **Graphic text is still Japanese.** That includes the fiction disclaimer, logos, and in-image text.

## How it works (technical notes)

| Item | Detail |
|---|---|
| Text encoding | 16-bit little-endian glyph indices. 0x000–0x108 are kana and punctuation; 0x109–0x566 are kanji. The full map is in `tools/table.tsv`. |
| Control codes | FF01 wait for button (text after it starts a new line), FF02 clear page, FF03 newline, FF04 player name, FF6F/FF70 actor/demon name, FF18 demon name, FF1B item name, FF71/FF88 numbers, FFFE wide space, FF7C timed pause, FFFF end of string. |
| Compression | Magic 0x201 LZ (`u32 magic, u32 total, u32 unpacked`) and magic 0x102 RLE for images. |
| Event scripts | `D/F0016.BIN` is split into 444 sector-aligned units. Their offsets come from an index in the executable (file offset 0xE4CF4, entries `0x04000000 | offset`). Each unit is a bytecode block followed by a text block. Limits: a unit may be at most 6 sectors, and a text block may be at most 0x14FA bytes unpacked. |
| Repacking | `tools/f16pack.py` rebuilds F0016 with grown text blocks and rewrites the index. The new file no longer fits its original slot, so it is moved into the zero-filled `ZZZ.BIN` area at LBA 95371. `FILEPOS.DAT` and the ISO directory records are updated to match. |
| Map events | `D/F0018.BIN` uses the same unit layout but has no index. Each text block grows in place up to the start of the next unit. |
| Fonts | Dialogue: `D/F0013.BIN` (16×12, 2 bpp), with widths in the exe table at 0xE3680. Menus: `D/F0014.BIN` (RLE 4 bpp texture holding 12×12 1-bpp glyphs in four bit planes), with metrics at 0xE3110. Menu strings may use at most 11 glyph codes. |
| English font | An original proportional pixel font (`tools/enfont.py`). Common letter sequences are merged into 600 tiles that average 2.1 letters per code. Each tile is drawn into both fonts. |
| Spacing patch | Exe 0x3A930 and 0x4BB9C: the `+1` letter gap changed to `+0`. |
| Disc rebuild | EDC/ECC is regenerated for every modified sector. |

## Toolkit

- `tools/iso_extract.py original.bin disc` extracts the disc.
- `tools/dump_script.py disc script` dumps every compressed string table to JSON.
- `tools/make_patch.py original.bin patched.bin` rebuilds the patched image from the translation files in `trans/`:
  - `F0016_u<unit>_b<block>.json` for event text.
  - `F0018_o<offset>.json` for map events.
  - `F0017_b0.json` for menus.
- `tools/make_ppf.py original.bin patched.bin out.ppf` writes a PPF 3.0 patch. Run `make_ppf.py apply ...` to check one.
- **Emulator harness:** `emu/` holds a headless libretro frontend for PCSX-ReARMed. It handles scripted input, screenshots, RAM access and disc-read logging; `replay.py` plays from a cold boot to the 2-A classroom.

The translation files contain only English, keyed by string number. The Japanese script is not included; `dump_script.py` regenerates it from your own disc.
