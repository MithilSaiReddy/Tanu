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

### Rust

- Follow standard Rust conventions (`cargo fmt`, `cargo clippy`)
- Use `tauri::command` for all IPC functions
- Annotate with proper error types (`Result<(), String>`)

### JavaScript / Frontend

- Vanilla JS only — no frameworks
- Use `const` / `let` (no `var`)
- DOM access via `document.getElementById()` (`$` helper in `main.js`)
- `fetch()` for server calls, `invoke()` for Tauri native calls

## Git Workflow

This repository uses a git submodule for the `bujji/` framework:

```
Tanu (main repo)
  └── bujji/ (submodule → github.com/MithilSaiReddy/bujji)
```

When you make changes that affect both:

1. Commit and push the bujji submodule changes first:
   ```bash
   cd bujji
   git add .
   git commit -m "description"
   git push
   cd ..
   ```

2. Then commit the main repo (which updates the submodule reference):
   ```bash
   git add bujji
   git commit -m "Update bujji submodule: ..."
   ```

## Pull Request Checklist

- [ ] Builds successfully (`cargo tauri build`)
- [ ] Server starts without errors (`python3 main.py serve`)
- [ ] No new warnings or errors
- [ ] Gmail flow tested (if applicable)
- [ ] Window clamping tested on multi-monitor setups (if applicable)
- [ ] `.gitignore` updated for any new generated files

## Reporting Issues

Open an issue on GitHub with:
- Description of the bug or feature request
- Steps to reproduce (for bugs)
- Relevant logs or screenshots
- Environment info (OS, display server, Tauri version)
