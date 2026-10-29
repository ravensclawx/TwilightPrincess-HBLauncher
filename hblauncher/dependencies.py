#!/usr/bin/env python3
"""Fetch pinned dependency sources and build the Animal Crossing dependencies."""
import argparse
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
DEPS = HERE / 'deps'

def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)

def checkout(name, url, revision, patch=None):
    path = DEPS / name
    if not path.exists():
        run(['git', 'clone', '--no-checkout', '--filter=blob:none', url, path])
        run(['git', '-C', path, 'checkout', '--detach', revision])
    actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != revision:
        raise SystemExit(f'{path} is at {actual}, expected {revision}; leave your checkout intact and choose a fresh deps directory')
    if patch:
        patch = HERE / 'patches' / patch
        check = subprocess.run(['git', '-C', str(path), 'apply', '--check', str(patch)], capture_output=True)
        if check.returncode == 0:
            run(['git', '-C', path, 'apply', patch])
        else:
            reverse = subprocess.run(['git', '-C', str(path), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
            if reverse.returncode:
                raise SystemExit(f'Patch does not match {path}')
    return path

def configure(source, build, options):
    run(['cmake', '-S', source, '-B', build, '-G', 'Ninja',
         f'-DCMAKE_TOOLCHAIN_FILE={HERE / "cmake/switch2-musl.cmake"}',
         '-DCMAKE_BUILD_TYPE=Release', *options])
    run(['cmake', '--build', build, '--parallel', str(JOBS)])

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('action', choices=['fetch', 'build'])
parser.add_argument('--jobs', type=int, default=min(8, os.cpu_count() or 1))
args = parser.parse_args()
JOBS = args.jobs
if args.action == 'build':
    for name in ['HBL_ROOT', 'HBXL_TOOLCHAIN']:
        if not os.environ.get(name):
            parser.error(f'Set {name}; see README.md')
DEPS.mkdir(parents=True, exist_ok=True)
dawn = checkout('dawn', 'https://github.com/encounter/dawn.git',
    '1155e0ed531126f33a1279afa029349651ca1c93', 'dawn-hbx-switch2.diff')
sdl = checkout('sdl3', 'https://github.com/libsdl-org/SDL.git',
    '8e37db5e797b6167f3a00d697d816a684bd259c7', 'sdl3-hbx-switch2.diff')
is_ac = json.loads((HERE / 'app/manifest.json').read_text())['id'] == 'animalcrossing'
if is_ac:
    glslang = checkout('glslang', 'https://github.com/KhronosGroup/glslang.git',
        '8a85691a0740d390761a1008b4696f57facd02c4')
if args.action == 'build':
    if not is_ac:
        raise SystemExit('Sources ready. Twilight Princess builds these dependencies through hblauncher/build.py build.')
    sdk = Path(os.environ['HBL_ROOT']).expanduser().resolve()
    options = [f'-DHBX_SDK_INCLUDE={sdk / "sdk/include"}', '-DHBX_SWITCH2=ON', '-DSDL_STATIC=ON', '-DSDL_SHARED=OFF',
        '-DSDL_UNIX_CONSOLE_BUILD=ON', '-DSDL_OFFSCREEN=ON']
    options += [f'-D{x}=OFF' for x in ['SDL_X11', 'SDL_WAYLAND', 'SDL_KMSDRM', 'SDL_OPENGL', 'SDL_OPENGLES',
        'SDL_ALSA', 'SDL_PULSEAUDIO', 'SDL_PIPEWIRE', 'SDL_JACK', 'SDL_SNDIO', 'SDL_DBUS', 'SDL_IBUS',
        'SDL_LIBUDEV', 'SDL_HIDAPI', 'SDL_CAMERA', 'SDL_TESTS', 'SDL_EXAMPLES']]
    configure(sdl, DEPS / 'build-sdl', options)
    options = ['-DDAWN_FETCH_DEPENDENCIES=ON', '-DDAWN_ENABLE_VULKAN=ON', '-DDAWN_BUILD_MONOLITHIC_LIBRARY=STATIC']
    options += [f'-D{x}=OFF' for x in ['DAWN_BUILD_SAMPLES', 'DAWN_BUILD_TESTS', 'DAWN_BUILD_PROTOBUF',
        'TINT_BUILD_TESTS', 'TINT_BUILD_CMD_TOOLS', 'TINT_BUILD_IR_BINARY', 'DAWN_USE_X11', 'DAWN_USE_WAYLAND',
        'DAWN_ENABLE_OPENGLES', 'DAWN_ENABLE_DESKTOP_GL', 'DAWN_USE_GLFW', 'TINT_BUILD_GLSL_WRITER',
        'TINT_BUILD_HLSL_WRITER', 'TINT_BUILD_MSL_WRITER', 'TINT_BUILD_GLSL_VALIDATOR']]
    configure(dawn, DEPS / 'build-dawn', options)
    prefix = DEPS / 'glslang-install'
    configure(glslang, DEPS / 'build-glslang', [f'-DCMAKE_INSTALL_PREFIX={prefix}',
        '-DENABLE_GLSLANG_BINARIES=OFF', '-DENABLE_OPT=OFF', '-DENABLE_HLSL=OFF', '-DBUILD_TESTING=OFF'])
    run(['cmake', '--install', DEPS / 'build-glslang'])
    env = os.environ.copy()
    env['HBX_DEPS_ROOT'] = str(DEPS)
    run(['sh', HERE / 'build-sdl2compat.sh', HERE], env=env)
print('Dependencies ready:', DEPS)
