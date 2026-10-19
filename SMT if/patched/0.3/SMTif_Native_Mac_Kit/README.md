# Shin Megami Tensei if... — native Mac build kit (English patch v0.3)

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

Apply `SMTif_PS1_English_v0.3.xdelta` to the original Japanese `.bin` (CRC32
`D77E3D8F`). The patched `.bin` should have CRC32 `F27A4461`; the script
checks this for you.

## 3. Build

Unzip this kit, then in Terminal:

```sh
cd ~/Downloads/SMTif_Native_Mac_Kit     # wherever you unzipped it
bash build.sh
```

When it asks, drag your patched `.bin` into the Terminal window and press
Return. The script:

1. Downloads PSXRecomp and recomp-ui at the exact versions this kit was tested with.
2. Copies your disc into `disc/` and recompiles the game's code into C (`generated/`).
3. Compiles everything into `build/SMTif_Recompiled`. This usually takes 5–20 minutes.
   The recompile step needs about 6 GB of memory, so close big apps first on an 8 GB Mac.
   If it stops with "exit -9", it ran out of memory: close more apps and run `bash build.sh` again.
4. Creates `play.command`.

If you built v0.2 with the old kit, unzip this kit into a fresh folder and build
there: v0.3 changes the game's code, so it has to be recompiled.

## 4. Play

Double-click **play.command**, or run `./play.command` in Terminal.

| PlayStation | Keyboard | In the game |
|---|---|---|
| D-pad | Arrow keys | Up/down walk, left/right turn; move cursors |
| Circle | S | Confirm, talk, open the command bar |
| Cross | X | Cancel / back |
| Triangle | A | Explain the highlighted command |
| Square | Z | Cancel / close menus |
| L1 / R1 | Q / W | Previous / next character on the status screen |
| L2 / R2 | E / R | — |
| Start | Return | System menu (quick save, load, settings) |
| Select | Right Shift | — |

Controllers also work. Memory-card saves are kept in the `saves/` folder.

### The F1 menu

Press **F1** (or Select + L3 on a controller) at any time. The game pauses and
the menu shows:

- **Save States:** ten slots with a picture and the time saved. Save or load any slot.
- **Controls:** a drawing of the controller with your keys and what each button does.
- **Key Bindings:** click a button, then press the key you want. Saved to `keybinds.ini`.
- **Manual:** a short original guide to the game (story, exploring, the COMP,
  battles, talking to demons, fusion, alignment, saving).
- **Quit Game.**

Other keys: F7 opens PSXRecomp's own save-state browser, hold Tab to
fast-forward, F8 rewinds, Alt+Enter or Cmd+F toggles fullscreen.

If the picture is black or wrong, try `./play.command --renderer software`.

## Notes

- **Keep it to yourself.** The built game contains Atlus's code recompiled
  from your disc, so don't share `build/`, `generated/` or `disc/`. Anyone
  else should build from their own disc with this kit. PSXRecomp's license
  is non-commercial.
- **What was tested.** On Linux, this kit's steps ran from a fresh folder and
  the result played the English opening, name entry and the school, and the F1
  menu saved and loaded states. The Mac build uses the same steps, but this kit
  hasn't been run on a Mac yet.
- **If a download fails** while CMake fetches a dependency, you can point it at
  a local copy: `EXTRA_CMAKE_ARGS="-DFETCHCONTENT_SOURCE_DIR_PSX_LIBWEBP=/path/to/libwebp" bash build.sh`.
- **Still running through an interpreter.** Some code the game loads from the
  disc while playing, like the title and opening module, still runs through
  PSXRecomp's small built-in interpreter. The main program is fully native.
- **Other games.** The SMT Recomp launcher (separate download) builds other PS1
  discs the same way and adds the same F1 menu.
