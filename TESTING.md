# Testing `checking-branch`

`main` is not used by this test flow. Start from a clean checkout of the review
branch:

```bash
git clone --branch checking-branch --single-branch https://github.com/MithilSaiReddy/Tanu
cd Tanu
python3 scripts/verify.py
```

The first command performs source, CLI, and unit checks without downloading
packages or creating a virtual environment. Temporary configuration and
workspace files are removed when it finishes.

For the product/server check, use an isolated environment:

```bash
python3 -m venv .test-venv
source .test-venv/bin/activate          # Windows: .test-venv\Scripts\activate
python -m pip install -e .
python scripts/verify.py --full
```

`--full` starts Tanu on a free loopback port, validates the status, config,
tools, and event endpoints, checks the server process tree against the 800 MB
limit, and shuts it down. It does not need an API key or contact an LLM.

Voice hardware and the Godot interface are optional, machine-dependent checks:

```bash
python -m pip install -e '.[voice]'
bash build.sh
python main.py onboard
python main.py desk
```

Delete `.test-venv` after testing to reclaim its disk space. A real local model
is required to judge response quality; the automated checks deliberately do
not download a model.
