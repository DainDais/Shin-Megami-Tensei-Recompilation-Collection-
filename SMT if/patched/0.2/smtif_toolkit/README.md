# Shin Megami Tensei if... (PS1) — English translation proof of concept

## Applying the patch

- **Base image:** `Shin Megami Tensei If... (Japan) (Anniversary Pack).bin`, a single-track MODE2/2352 BIN/CUE. Its CRC32 must be `D77E3D8F`.
- **Patches:**
  - `SMTif_PS1_English_PoC.xdelta` (preferred). Apply it with Rom Patcher JS, Delta Patcher, or `xdelta3 -d -s original.bin patch.xdelta out.bin`.
  - `SMTif_PS1_English_PoC.ppf`, the same changes in PPF 3.0 format.
- Keep your original `.cue` file and point it at the patched `.bin`.
- Patched CRC32: `C1BB237F`.

Share only the patch files, never the disc image.

## What's translated

The whole opening, from Nova the cyber fortune-teller through the point where Yumi asks you to come along:
- Nova's dialogue and all of the questions.
- Every fortune-result variant.
- The Demon Emperor's speech.
- The classroom panic scene and Yumi's lines.

This is all 58 strings in the opening event (F0016 event at 0x1000). The scene was tested end to end in an emulator; see `SMTif_English_PoC_screenshots.png`.

## Known limitations

- **Menus are still Japanese.** This covers the gender and answer choices, and every other menu. Menus are drawn from a second font (probably `D/F0003.BIN`) that isn't decoded yet. English menu strings are drafted in `trans/F0017_b0.json`.
- **Name entry still uses the kana grid.**
- **Rare kanji elsewhere are replaced.** The proof of concept reuses 333 of the least-used kanji glyph slots (each appears 5 times or fewer in the whole game) for English letter tiles. Untranslated text later in the game will occasionally show an English fragment where one of those kanji was. A full translation replaces all Japanese text, so this goes away.
- **Japanese letter spacing is 1 px tighter.** Letter spacing is now 1 px (it was 2 px), which also affects any remaining Japanese.
- **Graphic text is still Japanese.** That includes the fiction disclaimer, logos, and in-image text.

## How it works (technical notes)

| Item | Detail |
|---|---|
| Text encoding | 16-bit little-endian glyph indices. 0x000–0x108 are kana and punctuation (ordered by the table at exe offset 0xE3F64). 0x109–0x566 are 1,118 kanji in JIS order, except the last 11, which were appended out of order. The full map is in `tools/table.tsv`. |
| Control codes | FF01 wait for button, FF02 clear page, FF03 newline, FF04 player name, FFFE wide space, FF7C timed pause, FFFF end of string. |
| Compression | Magic 0x201: header `u32 magic, u32 total_size, u32 unpacked_size`. Control byte c < 0x80 means copy c+1 literal bytes; c ≥ 0x80 means copy (c&0x7F)+3 bytes from distance (next byte)+1. The game decodes this as a stream. Files can chain blocks; F0013 holds the font followed by its palette. |
| String tables | Unpacked: `u32 offsets[n]`, followed by strings terminated by FFFF. |
| Event scripts | `D/F0016.BIN`. Each event is a 2 KB-aligned slot holding [bytecode LZ block][4-byte align][text LZ block], then zero padding. A text block has to fit inside its own slot. |
| Dialogue font | `D/F0013.BIN`: 1,383 glyphs, 16×12 cells, 2 bits per pixel, least-significant pixel first. Value 3 is transparent. |
| Width table | Exe offset 0xE3680 (RAM 0x800F2E80): one byte per glyph giving its ink width. The pen advances by width + 1 + window spacing. |
| Spacing patch | Exe 0x3A930 and 0x4BB9C: the `+1` changed to `+0`. |
| English font | An original proportional pixel font (`tools/enfont.py`). Common letter combinations are packed into single glyphs: 333 tiles average 2.2 letters per code. That halves storage, and the tiles look identical to letter-by-letter text. |
| Disc rebuild | Files are rewritten in place: same sector address, same allocation. EDC/ECC is regenerated for every modified sector. `FILEPOS.DAT` (the game's file table) stays valid. |

## Toolkit

- **Pipeline:**
  - `tools/iso_extract.py` extracts the disc.
  - `tools/dump_script.py` dumps every compressed string table to JSON.
  - `tools/make_patch.py` rebuilds the patched image from `trans/*.json`.
- **Supporting tools:** `lz.py` (codec), `cdsector.py` (EDC/ECC), `font.py`, `enfont.py`, `en_insert.py` (wrapping, tile building, encoding, string-order optimization), `build.py`.
- **Testing harness:** `emu/` contains a headless libretro frontend for PCSX-ReARMed using its built-in BIOS replacement. It handles scripted input, screenshots, RAM access, and (with a small core patch) VRAM dumps.

### Rebuilding from scratch

```bash
python3 tools/iso_extract.py original.bin disc
python3 tools/dump_script.py disc script
python3 tools/make_patch.py original.bin patched.bin
```

## Next steps toward a full translation

1. **Menu font.** Decode `D/F0003.BIN`, then apply the same tile approach to the menu string tables (F0017 and others).
2. **Room for longer text.** Many event slots have only a few hundred bytes of padding. A full script needs the event index found, so events can be repacked or relocated.
3. **Remaining text sources.** Translate the uncompressed tables (F0084 shops/NPCs, F0040, F0049, the executable's system messages), then the graphics.
4. **Name entry.** Switch the grid to Latin letters.
