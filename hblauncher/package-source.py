#!/usr/bin/env python3
"""Archive source (including initialized submodules), excluding local output."""
import io
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def files(repo, prefix=Path()):
    names = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z', '--cached', '--others', '--exclude-standard']).decode().split('\0')
    for name in sorted(set(names) - {''}):
        path = repo / name
        relative = prefix / name
        if path.is_dir():
            if (path / '.git').exists():
                yield from files(path, relative)
            continue
        if path.is_file() or path.is_symlink():
            yield relative, path

def main():
    status = subprocess.check_output(['git', '-C', str(ROOT), 'submodule', 'status', '--recursive'], text=True)
    if any(line.startswith('-') for line in status.splitlines()):
        raise SystemExit('Initialize submodules before packaging: git submodule update --init --recursive')
    out = ROOT / 'hblauncher/dist' / (ROOT.name + '-source.tar.gz')
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(out, 'w:gz') as archive:
        for name, path in files(ROOT):
            # Ignore generated data even if accidentally staged later.
            if name.parts[:2] in [('hblauncher', 'build'), ('hblauncher', 'dist'), ('hblauncher', 'deps'), ('hblauncher', 'fsroot')]:
                continue
            if name.suffix.lower() in ['.iso', '.gcm', '.rvz', '.ciso', '.sav']:
                raise SystemExit(f'Refusing user game data: {name}')
            info = tarfile.TarInfo(str(Path(ROOT.name) / name))
            info.mtime = 0
            if path.is_symlink():
                target = path.readlink()
                if target.is_absolute() or not path.resolve().is_relative_to(ROOT):
                    raise SystemExit(f'Refusing external symlink: {name}')
                info.type = tarfile.SYMTYPE
                info.linkname = str(target)
                archive.addfile(info)
            else:
                data = path.read_bytes()
                info.size = len(data)
                info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                archive.addfile(info, io.BytesIO(data))
            count += 1
    print(f'Packaged {count} source files: {out}')

if __name__ == '__main__':
    main()
