# SMT Recomp launcher

A small launcher that turns PlayStation disc images into native programs with
[PSXRecomp](https://github.com/mstan/psxrecomp), and keeps them in one library
you can start with one click. It was made for the Shin Megami Tensei games on PS1,
but it accepts any PS1 disc.

## What it does

When you add a disc, the launcher:

1. Reads the disc's serial (for example `SLPM-87153`) from `SYSTEM.CNF`.
2. Downloads PSXRecomp and recomp-ui at the versions this launcher was tested with (first time only).
3. Creates a PSXRecomp project for the game with PSXRecomp's own setup script.
4. Adds the in-game menu: press **F1** for save states, key bindings, a controls diagram and a guide.
5. Recompiles the game's code to C, then compiles the native program. The recompile step
   needs about 6 GB of memory.

Nothing is uploaded anywhere. The disc stays where it is; the project points at it.

## Setup (Mac, one time)

```sh
xcode-select --install
brew install cmake ninja pkg-config git python
```

## Use

Double-click **Open SMT Recomp.command**, or run `python3 smt_launcher.py`. The
launcher opens in your browser at `http://127.0.0.1:8765/`. Then:

- **Add a game:** click **Browse...** and pick a `.cue` file (or a single-track `.bin`), then click **Recompile**. The first build takes 10–30 minutes.
- **Play:** click **Play** next to a built game.
- **Rebuild:** do this after you apply a newer translation patch to the same disc image, or after you edit a game's guide.
- **Folder:** opens the game's project folder.

The library is in `~/SMT-Recomp` (set `SMT_RECOMP_HOME` to use another folder).
Each game gets `games/<Name>Recomp/`, and build logs go in `logs/`.

You can also use the command line:

```sh
python3 smt_launcher.py probe ~/Discs/game.cue    # show the serial and boot file
python3 smt_launcher.py add ~/Discs/game.cue --name SMT2 --title "Shin Megami Tensei II"
python3 smt_launcher.py list
python3 smt_launcher.py play SMT2
```

## Guides for other games

Shin Megami Tensei if... comes with its own guide and button descriptions. For any
other game, the menu's Manual page explains how to add one: put a `guide.txt` in the
game's folder, start each section with a line like `# Battles`, and click Rebuild.

## Limits

- **Only SMT if... was tested end to end.** That game (`SLPM-87153`, with the English
  patch applied) was built with this launcher on Linux and played; the Mac steps are the
  same but haven't been run on a Mac yet. Other discs go through the
  same PSXRecomp pipeline, but whether each game boots and plays correctly depends on
  PSXRecomp's support for that game. Use the build log in `logs/` to see where a
  build stopped.
- **Japanese games stay Japanese.** The launcher recompiles whatever disc you give
  it. Translation patches are separate: apply them to the disc image first.
- **Single-track discs work best.** Multi-disc games need PSXRecomp's
  `update_disc_set.py` after the first build (see PSXRecomp's
  `docs/GAME_PROJECT_SETUP.md`).
- **Keep the builds to yourself.** A built game contains code recompiled from your
  disc. Share translation patches, never builds. PSXRecomp's license is non-commercial.
- If a build fails on a missing dependency download, set `EXTRA_CMAKE_ARGS` before
  starting the launcher, for example
  `EXTRA_CMAKE_ARGS="-DFETCHCONTENT_SOURCE_DIR_PSX_LIBWEBP=/path/to/libwebp"`.
