# Shin Megami Tensei if... — native Mac build kit (English patch v0.2)

This kit builds the game as a real Mac program with no emulator, using
[PSXRecomp](https://github.com/mstan/psxrecomp). It doesn't contain any game
code: the build script recompiles the game from **your own disc image** on your
Mac.

## 1. Install the tools (one time)

Open **Terminal** and run:

```sh
xcode-select --install
```

Then install [Homebrew](https://brew.sh) if you don't have it, and run:

```sh
brew install cmake ninja pkg-config git python
```

## 2. Have the English-patched disc ready

Apply `SMTif_PS1_English_v0.2.xdelta` to the original Japanese `.bin` (CRC32
`D77E3D8F`). The patched `.bin` should have CRC32 `137C1A05`; the script
checks this for you.

## 3. Build

Unzip this kit, then in Terminal:

```sh
cd ~/Downloads/SMTif_Native_Mac_Kit     # wherever you unzipped it
bash build.sh
```

When it asks, drag your patched `.bin` into the Terminal window and press
Return. The script:

1. Downloads PSXRecomp at the exact version this kit was tested with.
2. Copies your disc into `disc/` and recompiles the game's code into C (`generated/`).
3. Compiles everything into `build/SMTif_Recompiled`. This usually takes 5–20 minutes.
4. Creates `play.command`.

## 4. Play

Double-click **play.command**, or run `./play.command` in Terminal.

| PlayStation | Keyboard |
|---|---|
| D-pad | Arrow keys |
| Circle (confirm) | S |
| Cross (cancel) | X |
| Triangle | A |
| Square | Z |
| L1 / R1 | Q / W |
| L2 / R2 | E / R |
| Start | Return |
| Select | Right Shift |

Controllers also work. Fullscreen: Cmd+F. Memory-card saves are kept in the
`saves/` folder.

If the picture is black or wrong, try `./play.command --renderer software`.

## Notes

- **Keep it to yourself.** The built game contains Atlus's code recompiled
  from your disc, so don't share `build/`, `generated/` or `disc/`. Anyone
  else should build from their own disc with this kit. PSXRecomp's license
  is non-commercial.
- **What was tested.** On Linux, this kit's own `build.sh` ran from a fresh
  folder and the result opened in a window. The same native build played
  through the English opening, the 3D school halls and the floppy-disk event.
  The Mac build uses the same steps, but this kit hasn't been run on a Mac yet.
- **Not translated yet.** The opening school slideshow, system messages,
  battles and demon conversations are still in Japanese.
- **Still running through an interpreter.** Some code the game loads from the
  disc while playing, like the title and opening module, still runs through
  PSXRecomp's small built-in interpreter. The main program is fully native.
