# Contributing

## How to Contribute

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests (if available)
5. Commit and push
6. Open a Pull Request

## Code Style

### Python

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints where practical
- Avoid unnecessary comments — code should be self-documenting

### GDScript (Godot)

- Follow the [GDScript style guide](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_styleguide.html)
- Use snake_case for variables/functions, PascalCase for classes
- Signals should use past tense (e.g., `connected`, `message_received`)

## Git Workflow

The Tanu agent framework lives directly in this repository under
`src/tanu/` — there is no separate framework repository or submodule to maintain.

```
Tanu (single repo)
  └── src/
      └── tanu/   # agent framework + server + tools + voice (maintained here)
```

When you change the framework, edit `src/tanu/` and commit it like any other
file in this repository.

## Pull Request Checklist

- [ ] Server starts without errors (`python3 main.py serve`)
- [ ] Godot client connects and streams responses
- [ ] No new warnings or errors
- [ ] Gmail flow tested (if applicable)
- [ ] `.gitignore` updated for any new generated files

## Deploying Documentation

The docs are built with MkDocs and deployed to GitHub Pages automatically via
a GitHub Actions workflow (`.github/workflows/deploy-docs.yml`).

### How it works

- Triggered on every push to `main` that touches `docs/**`
- Builds MkDocs from the `docs/` directory
- Uploads `docs/site/` as a Pages artifact
- Deploys to `https://mithilsaireddy.github.io/Tanu/`

### One-time setup

1. Go to repo **Settings → Pages → Source** → select **GitHub Actions**
2. Push to `main` — the workflow runs automatically

### Preview locally

```bash
cd docs
source ../venv/bin/activate
pip install mkdocs mkdocs-material
mkdocs serve
```

Open `http://localhost:8000`.

## Reporting Issues

Open an issue on GitHub with:
- Description of the bug or feature request
- Steps to reproduce (for bugs)
- Relevant logs or screenshots
- Environment info (OS, Godot version, Python version)
