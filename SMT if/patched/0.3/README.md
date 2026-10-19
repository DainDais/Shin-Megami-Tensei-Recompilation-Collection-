# Shin Megami Tensei if... (PS1): English translation v0.3

## Applying the patch

- **Base image:** `Shin Megami Tensei If... (Japan) (Anniversary Pack).bin`, a single-track MODE2/2352 BIN/CUE. Its CRC32 must be `D77E3D8F`.
- **Patches** (both produce the same image):
  - `SMTif_PS1_English_v0.3.xdelta` (preferred). It's built without secondary compression, so it works in Rom Patcher JS, Delta Patcher, or `xdelta3 -d -s original.bin patch.xdelta out.bin`.
  - `SMTif_PS1_English_v0.3.ppf`, the same changes in PPF 3.0 format.
- Apply it to the **original** image, not to an earlier version's output.
- Keep your original `.cue` file and point it at the patched `.bin`.
- Patched CRC32: `F27A4461`.

Share only the patch files, never the disc image.

## What's new in v0.3

- **The opening.** The attract-movie text scroll is now English: the frames were redrawn and re-encoded into the movie itself. The fiction disclaimer before it is in English too.
- **The title screen.** The memory card checks and the "load clear data?" question are in English.
- **Name entry.** The keyboard shows English letters, digits and punctuation, and typing works. The kana rows are still there below them. Joke names like "AAA" are still refused, as in the original.
- **Names everywhere.** These are all in English:
  - all 309 demons and 47 races
  - all 283 items and equipment, with their descriptions
  - all 160 spells, with their descriptions
  - the partner names
- **Battles.** All 307 battle messages: attacks, damage, spells, status effects, victory, experience and money, level ups, escapes and the help bar.
- **Demon negotiation framework.** The narration, the results ("joined you", "left") and the answer choices are in English. The demons' own lines are not yet (see below).
- **Menus and system screens.** These are in English:
  - The status, equipment, item and COMP screens, and their labels and help text.
  - Level-up and stat messages, the Analyze resistance display, and the config screen.
  - The memory card screens and the field and system messages ("You don't have a COMP", door and item prompts).
- **Cathedral of Shadows** (fusion).
- **Shops and services.** These are in English:
  - the weapon, armor and general stores
  - the healing spring
  - the MAG dealer, the jewel trader and the appraiser
  - the menu choices
- From v0.2: the whole first-chapter event script, the school map events and the fortune-teller menus.

The opening, title prompts, name entry, Nova, the school, the party panel, and the status, item and equipment screens were checked in an emulator from a cold boot. Shops and battles were checked only for format and size: the test run didn't get as far as a shop or a fight.

## Known limitations

- **Demon conversation lines are still Japanese.** `F0077` holds about 2,450 lines that demons say during negotiation. That's the next big job.
- **Story events after the first chapter are still Japanese.** These are the other event files, `F0021`–`F0038`.
- **The ending movies keep their Japanese text scroll.** They are `F0100`–`F0104`, and the same movie method would work for them.
- **Some kanji in untranslated text are replaced.** English uses 800 glyph slots taken from the least-used kanji. Untranslated screens can show an English fragment in place of a kanji, which is at most 15 uses of any one kanji across the remaining Japanese text.
- **The party panel shows names in capitals.** Its small font has no lower-case letters, and like the Japanese names it shows at most eight characters, so long demon names are cut short there (for example "TAKEMIKA"). Menus and dialogue show the full name.
- **Names are limited by the original buffers.** Some names are shortened, for example "Zombie Prof" and "Jack Ripper". Demon and item names are at most 8 glyph tiles.

## Native Mac build

`SMTif_Native_Mac_Kit_v0.3.zip` builds this patched disc as a native Mac program with PSXRecomp, adding an in-game F1 menu for save states, key bindings, a controls diagram and a guide. See the README inside the kit.

`SMT_Recomp_Launcher_v1.0.zip` is a small launcher that does the same for any PS1 disc you give it (it was tested end to end with this one) and lists the games you've built so you can start them with one click.
