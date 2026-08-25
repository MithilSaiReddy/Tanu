# Building & Packaging

There is no compile step — Tanu runs from source. The desktop UI is plain
Python (Pygame), installed together with the rest of the package.

## Running from Source

```bash
bash setup.sh          # once: venv + dependencies
python3 main.py desk   # server subprocess + Pygame window
```

Any change under `src/tanu/desktop/` is picked up on the next launch.

## Cubie / ARM Package

The GitHub workflow (`.github/workflows/build-cubie.yml`) assembles a portable
source package for ARM boards (e.g. Radxa Cubie A7Z):

1. Copies `main.py`, `requirements.txt`, `pyproject.toml`, `src/tanu/`, and
   the launcher scripts into `build/tanu-cubie/`
2. Runs a syntax check over the bundled source
3. Uploads `tanu-cubie.tar.gz` as a workflow artifact

On the device:

```bash
tar xzf tanu-cubie.tar.gz && cd tanu-cubie
./scripts/first-boot.sh    # creates venv, installs deps
./scripts/launch.sh        # starts server + Pygame UI
```

## Build Artifacts

The `build/` directory contains packaging output. It's excluded from git via `.gitignore`.
