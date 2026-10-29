# Validation

Validated on 2026-10-29 with the HBLauncher ABI 3 SDK.

- Clean AArch64 game build completed using the standalone fork and build script.
- HBLauncher Linux runtime rebuilt and linked into the executable.
- Code/data package generated and accepted by HBLauncher's package loader,
  including manifest, ABI, file sizes, and code hash verification.
- Source archive excludes local build output, dependencies, discs, and saves.
- Hardware launch and gameplay of this standalone package have not been tested.

The clean build also compiled Dawn, SDL3, Aurora, and the other game dependencies
from local source checkouts. Aurora is carried as a patch against its upstream
submodule revision.
