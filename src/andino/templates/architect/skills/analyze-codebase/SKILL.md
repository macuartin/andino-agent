---
name: analyze-codebase
description: "Deep analysis of a repository or module — structure, patterns, dependencies, and key files"
---
# Analyze Codebase

## Arguments
- `$0` (required): GitHub repository (org/repo) or path within an already-cloned repo
- `focus` (optional): Specific area to focus on (e.g. "auth module", "API layer", "database models")

## Steps

1. **Clone to workspace** — `shell` → `gh repo clone {repo} {workspace_dir}/repo` (skip if already cloned)

2. **Understand project structure** — `shell`:
   - `find . -maxdepth 2 -type d | grep -v node_modules | grep -v .git` for directory tree
   - `cat README.md` for project overview
   - `cat pyproject.toml` or `cat package.json` for dependencies and entry points

3. **Identify architecture patterns**:
   - Framework used (FastAPI, Django, Express, etc.)
   - Directory conventions (src/, lib/, modules/, services/)
   - Configuration patterns (env vars, config files, dependency injection)

4. **Analyze focused area** (if focus provided):
   - `find . -path "*{focus}*" -type f` to locate relevant files
   - `file_read` on key files to understand implementation
   - `grep -rn "class |def |function |export " {path}` for API surface

5. **Map dependencies**:
   - Internal: what modules import from the focused area?
   - External: what packages/services does it depend on?
   - `grep -rn "import.*{module}" src/` for import graph

6. **Check test coverage**:
   - `find . -path "*/test*" -name "*.py"` to locate test files
   - Check if focused area has corresponding tests
   - Note testing patterns used (pytest, jest, etc.)

7. **Write analysis report** — `file_write` to workspace with findings

8. **Report** — summarize key findings in Slack thread
