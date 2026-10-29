#!/usr/bin/env python3
"""Configure/build, pack, install, or serve this HBLauncher port."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = HERE / "app/manifest.json"
CONFIG = json.loads(MANIFEST.read_text())
IS_AC = CONFIG["id"] == "animalcrossing"
BUILD = HERE / "build"

def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)

def required(name, relative=None):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name}; see README.md")
    path = Path(value).expanduser().resolve()
    if not (path / relative if relative else path).exists():
        raise SystemExit(f"Invalid {name}: {path}")
    return path

def sdk():
    return required("HBL_ROOT", "sdk/tools/hbxl-build.py")

def patch_aurora():
    aurora = ROOT / "extern/aurora"
    if not (aurora / "CMakeLists.txt").exists():
        raise SystemExit("Run git submodule update --init --recursive first")
    patch = HERE / "patches/aurora-hbx-switch2.diff"
    check = subprocess.run(["git", "-C", str(aurora), "apply", "--check", str(patch)], capture_output=True)
    if check.returncode == 0:
        run(["git", "-C", aurora, "apply", patch])
    else:
        reverse = subprocess.run(["git", "-C", str(aurora), "apply", "--reverse", "--check", str(patch)], capture_output=True)
        if reverse.returncode:
            raise SystemExit("Aurora differs from the pinned source; cannot apply the HBLauncher patch")

def configure(extra):
    hbl = sdk()
    required("HBXL_TOOLCHAIN", "bin/aarch64-linux-musl-gcc")
    dawn = required("DAWN_SOURCE", "include/webgpu/webgpu.h")
    BUILD.mkdir(parents=True, exist_ok=True)
    runtime = BUILD / "libhbxl.a"
    run(["python3", hbl / "sdk/tools/hbxl-build.py", "--runtime-lib", runtime])
    code = CONFIG["linux"]["code_base"]
    data = CONFIG["linux"]["data_base"]
    args = ["cmake", "-S", ROOT / "pc" if IS_AC else ROOT, "-B", BUILD, "-G", "Ninja",
        f"-DCMAKE_TOOLCHAIN_FILE={HERE / 'cmake/switch2-musl.cmake'}", "-DCMAKE_BUILD_TYPE=Release"]
    if IS_AC:
        dawn_build = required("DAWN_BUILD", "src/dawn/native/libwebgpu_dawn.a")
        glslang = required("GLSLANG_PREFIX", "lib/libglslang.a")
        sdl = required("SDL2_PREFIX", "libSDL2.a")
        args += ["-DPC_HBX_SWITCH2=ON", "-DPC_GLWGPU=ON", f"-DGLWGPU_DIR={HERE / 'glwgpu'}",
            f"-DDAWN_SWITCH_SRC={dawn}", f"-DDAWN_SWITCH_BUILD={dawn_build}", f"-DGLSLANG_DIR={glslang}",
            f"-DSDL_SWITCH_DIR={sdl}", f"-DHBXL_RUNTIME={runtime}", f"-DHBXL_LD={hbl / 'sdk/linux/hbxl.ld'}",
            f"-DHBXL_CODE_BASE={code}", f"-DHBXL_DATA_BASE={data}", f"-DHBXL_FS_PORT={CONFIG['linux']['fs_port']}"]
    else:
        sdl = required("SDL3_SOURCE", "CMakeLists.txt")
        patch_aurora()
        # CMake needs one shell-safe linker flag string. Paths with whitespace
        # are unsupported here, rather than silently producing a broken link.
        if any(c.isspace() for c in str(hbl) + str(BUILD)):
            raise SystemExit("Use build and SDK paths without whitespace")
        flags = f"-static -no-pie -nostartfiles -Wl,-T,{hbl / 'sdk/linux/hbxl.ld'} -Wl,--defsym=HBXL_CODE_BASE={code} -Wl,--defsym=HBXL_DATA_BASE={data} -Wl,--eh-frame-hdr -Wl,--gc-sections -Wl,-z,noexecstack -Wl,--whole-archive {runtime} -Wl,--no-whole-archive"
        args += [f"-DCMAKE_EXE_LINKER_FLAGS={flags}", "-DHBX_SWITCH2=ON", f"-DHBX_SDK_INCLUDE={hbl / 'sdk/include'}",
            "-DDUSK_ENABLE_CODE_MODS=OFF", "-DDUSK_ENABLE_OPUS=OFF", "-DAURORA_DAWN_PROVIDER=vendor",
            "-DAURORA_DAWN_LINKAGE=static", f"-DFETCHCONTENT_SOURCE_DIR_DAWN={dawn}",
            "-DAURORA_SDL3_PROVIDER=vendor", "-DAURORA_SDL3_LINKAGE=static", f"-DFETCHCONTENT_SOURCE_DIR_SDL={sdl}",
            "-DAURORA_NOD_PROVIDER=hbx", f"-DAURORA_NOD_LITE_DIR={HERE / 'nod-lite'}"]
        for option in ["DAWN_BUILD_PROTOBUF", "TINT_BUILD_IR_BINARY", "DAWN_USE_X11", "DAWN_USE_WAYLAND",
            "DAWN_ENABLE_OPENGLES", "DAWN_ENABLE_DESKTOP_GL", "TINT_BUILD_GLSL_WRITER", "TINT_BUILD_HLSL_WRITER",
            "TINT_BUILD_MSL_WRITER", "TINT_BUILD_GLSL_VALIDATOR", "DAWN_USE_GLFW", "DAWN_SUPPORTS_GLFW_FOR_WINDOWING",
            "GLFW_BUILD_WAYLAND", "GLFW_BUILD_X11", "SDL_X11", "SDL_WAYLAND", "SDL_KMSDRM", "SDL_OPENGL",
            "SDL_OPENGLES", "SDL_ALSA", "SDL_PULSEAUDIO", "SDL_PIPEWIRE", "SDL_JACK", "SDL_SNDIO", "SDL_DBUS",
            "SDL_IBUS", "SDL_LIBUDEV", "SDL_HIDAPI", "SDL_CAMERA", "SDL_TESTS", "SDL_EXAMPLES"]:
            args.append(f"-D{option}=OFF")
        args += ["-DSDL_UNIX_CONSOLE_BUILD=ON", "-DSDL_OFFSCREEN=ON"]
    run(args + extra)

def pack(elf):
    hbl = sdk()
    required("HBXL_TOOLCHAIN", "bin/aarch64-linux-musl-nm")
    if not elf.is_file():
        raise SystemExit(f"Build the game first; missing ELF: {elf}")
    run(["python3", hbl / "sdk/tools/hbxl-build.py", HERE / "app", "--pack", elf])
    # Distribute only the manifest and runtime image, never build caches or discs.
    dest = HERE / "dist" / CONFIG["id"]
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANIFEST, dest / "manifest.json")
    (dest / "build").mkdir(exist_ok=True)
    for filename in ["code.bin", "data.bin", "report.json"]:
        shutil.copy2(HERE / "app/build" / filename, dest / "build" / filename)
    print(f"Package: {dest}")
    return dest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["configure", "build", "pack", "install", "serve"])
    parser.add_argument("--elf", type=Path, help="Pack an already linked ELF instead of building")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--fsroot", type=Path, default=HERE / "fsroot")
    args, extra = parser.parse_known_args()
    if extra and args.action not in ["configure", "build"]:
        parser.error("Extra CMake arguments require configure or build")
    elf = args.elf or (BUILD / "bin/AnimalCrossing" if IS_AC else BUILD / "dusklight")
    if args.action in ["configure", "build"]:
        configure(extra)
    if args.action == "build":
        # The runtime archive is supplied as a linker option, so force a relink
        # after rebuilding it even when the game objects are unchanged.
        elf.unlink(missing_ok=True)
        run(["cmake", "--build", BUILD, "--parallel", str(args.jobs)])
    if args.action in ["build", "pack", "install"]:
        package = pack(elf.resolve())
        if args.action == "install":
            destination = sdk() / "apps" / CONFIG["id"]
            if destination.exists():
                raise SystemExit(f"Package built, but install destination already exists: {destination}")
            shutil.copytree(package, destination)
            print(f"Installed: {destination}")
    if args.action == "serve":
        if not args.fsroot.is_dir():
            raise SystemExit("Create --fsroot with your own disc and required resources; see README.md")
        port = CONFIG["linux"].get("fs_port", 39501)
        run(["python3", sdk() / "tools/hbxl-fileserver.py", args.fsroot.resolve(), "--port", str(port)])

if __name__ == "__main__":
    main()
