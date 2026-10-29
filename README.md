# Twilight Princess for HBLauncher

A Switch 2 HBLauncher port of [TwilitRealm/Dusklight](https://github.com/TwilitRealm/dusklight),
based on the Twilight Princess decompilation. Maintained by **@ravensclawx**.

The native AArch64 game runs through HBLauncher's Linux personality. Aurora
renders through Dawn/Vulkan into the console's display. The included `nod-lite`
adapter reads plain GameCube ISO images. This setup targets your own **GZ2E01
USA GameCube** disc; compressed RVZ/WIA images need conversion to ISO first.

## Set up HBLauncher first

These apps run inside [HBLauncher](https://github.com/ravensclawx/HBLauncher)
on Nintendo Switch 2. Follow the
[HBLauncher Getting Started guide](https://github.com/ravensclawx/HBLauncher/blob/main/docs/GETTING_STARTED.md)
to install the launcher, set up its external session runner, and establish the
required verified session. Then follow this README's **Build** and **Install and
run** sections to add the game to your app library and start its file server.
Launch the game from HBLauncher's library while that server is running.

## Requirements

- [HBLauncher](https://github.com/ravensclawx/HBLauncher), with ABI 3 and its Linux personality runtime.
- Linux, Python 3, Git, CMake, Ninja, and a patched `aarch64-linux-musl` toolchain.
- Your own supported game disc image. This integration adds no disc images, extracted game data, or private saves.
  Upstream source resources retain their original notices.

These are experimental Switch 2 ports. A successful build does not establish
console compatibility or gameplay performance. Hardware testing of these new
standalone packages is still required.

## Toolchain

Set the SDK and compiler locations (replace the example paths):

```sh
export HBL_ROOT=/path/to/HBLauncher
export HBXL_TOOLCHAIN=/path/to/patched-toolchain
```

An ordinary Linux cross-compiler is insufficient: musl must route syscalls
through HBLauncher's `__hbx_syscall`, and target libraries need BTI landing pads.
The known configuration uses GCC 15.1.0, musl 1.2.6, and binutils 2.44. To build
it with musl-cross-make:

```sh
git clone https://github.com/richfelker/musl-cross-make.git toolchain-src
git -C toolchain-src checkout 5e8042e63de29f8473fc3b0b831a587ba284e1a8
cp hblauncher/cmake/config.mak.example toolchain-src/config.mak
mkdir -p toolchain-src/patches/musl-1.2.6
cp "$HBL_ROOT/sdk/linux/musl-hbx-syscall-hooks.diff"   toolchain-src/patches/musl-1.2.6/9001-hbx-syscall-hooks.diff
make -C toolchain-src -j8
make -C toolchain-src install
export HBXL_TOOLCHAIN="$PWD/toolchain-src/toolchain"
```

Compiler sources and downloads remain local; they are not part of this fork.

## Build

Clone with submodules, or initialize them in an existing checkout:

```sh
git submodule update --init --recursive
python3 hblauncher/dependencies.py fetch
export DAWN_SOURCE="$PWD/hblauncher/deps/dawn"
export SDL3_SOURCE="$PWD/hblauncher/deps/sdl3"
python3 hblauncher/build.py build --jobs 8
```

The build applies the included Aurora patch to the pinned Aurora submodule,
then builds the static game and dependencies using the HBLauncher linker script
and runtime. Rerunning the script recognizes an already applied patch. A modified
Aurora submodule after configuration is expected; the patch is kept in this
repository instead of requiring an unpublished submodule commit.

You may set `DAWN_SOURCE` and `SDL3_SOURCE` to existing matching, patched source
trees. `build.py configure` only configures. Additional `-D...` arguments are
passed to CMake. The default code/data addresses are `0x30000000` / `0x38000000`.
Code mods and Opus are disabled in this configuration. This is the GameCube
port, not a Wii emulator.

## Install and run

The resulting app directory is `hblauncher/dist/twilight`. Copy that whole
directory into `$HBL_ROOT/apps/`, or run:

```sh
python3 hblauncher/build.py install
```

Installation refuses to overwrite an existing app directory. Only the manifest,
code/data images, and matching build report are installed; there is no bundled
commercial game artwork. To package an already linked game without rebuilding,
use `python3 hblauncher/build.py pack --elf /path/to/dusklight.elf`.

Create a private file-server root:

```sh
mkdir -p hblauncher/fsroot/tp
cp /path/to/your/GZ2E01.iso hblauncher/fsroot/tp/GZ2E01.iso
cp -R res hblauncher/fsroot/res
printf 'HBXL_PRELOAD=/tp/GZ2E01.iso\n' > hblauncher/fsroot/hbxl-env
python3 hblauncher/build.py serve
```

The server uses `10.42.0.1:39501`, the runtime default. Keep it running,
establish a verified HBLauncher session, and select **Twilight Princess**.
Select your disc from `/tp/GZ2E01.iso` when the game asks. The file-server root
also receives configuration and saves; keep them private and back up saves
before replacing a local setup. Read `README.upstream.md` for upstream controls
and required game resources.

## Source and credits

Upstream history and licensing are preserved. Read [LICENSE.md](LICENSE.md),
[the upstream README](README.upstream.md), and
[the integration notices](hblauncher/THIRD_PARTY.md). HBLauncher integration
additions use [MIT](hblauncher/LICENSE.integration). Original upstream CI is
disabled for this port branch; local build instructions above target HBLauncher.

## Source archive

`python3 hblauncher/package-source.py` writes a source-only archive under
`hblauncher/dist/`. Initialize submodules before packaging Twilight Princess.
The archive includes their source and the applied Aurora changes. It excludes
local dependencies, build output, discs, saves, and file-server data. Build the
app locally using the instructions above; generated app packages are ignored by Git.
