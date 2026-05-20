# Contributing to k8s-agents-strands

> 🌐 **Language**: **English** · [한국어](./CONTRIBUTING.ko.md)

Thank you for your interest in this project. This document covers the contribution flow and review criteria.

## Core principles

Every change in this project follows four principles.

1. **We do not merge code we do not understand.** Even AI-assisted code goes through a line-by-line review before the PR.
2. **Use MCP and SDKs first.** Custom implementations only when truly necessary.
3. **Write code whose intent is visible in five seconds.** Six months from now, you must still be able to read it instantly.
4. **Build abstractions only when justified.** Never preemptively.

The background and examples are in [docs/05-code-style.md](./docs/05-code-style.md).

## Contribution flow

### 1) Open an issue first

Discuss the change in an issue before writing code.

- **Bug**: reproduction steps, expected behavior, actual behavior
- **Feature**: the problem you are solving, proposed change, alternatives considered

Larger changes (architecture changes, new dependencies, new specialists) require prior agreement.

### 2) Fork and branch

```bash
git clone https://github.com/<your-username>/k8s-agents-strands
cd k8s-agents-strands
git checkout -b feature/short-description
```

Branch naming:

- `feature/...` — new functionality
- `fix/...` — bug fixes
- `docs/...` — documentation only
- `refactor/...` — no behavior change, cleanup

### 3) Set up your dev environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,agentcore]"
pre-commit install   # recommended
```

### 4) Write the code

When adding new functionality, we recommend following the tutorials in [docs/03-development.md](./docs/03-development.md).

Common commands:

```bash
# Unit tests
pytest tests/

# Lint and type checks
ruff check src tests
ruff format src tests
mypy src

# Local run
python -m k8s_rca_agent.main --cluster <your-cluster> "..."
```

### 5) Pre-PR checklist

- [ ] PR description states the intent clearly
- [ ] `pytest tests/` passes
- [ ] `ruff check src tests` passes
- [ ] `ruff format --check src tests` passes
- [ ] `mypy src` passes
- [ ] New functionality has tests
- [ ] Related docs updated (`docs/` or README)
- [ ] AI-assisted code has been reviewed line by line

### 6) PR body template

```markdown
## What changed
- What and how

## Intent and motivation
- Why this change is needed

## How verified
- Commands / scenarios used to test

## Scope of impact
- Breaking changes? Dependency adds/removes?
```

## Code style

- Python 3.11+
- Line length: 100
- Type hints required on the public API
- Docstrings explain *why* (information not visible from the code)
- Magic strings and numbers go into module-level constants

The detailed rules are in [docs/05-code-style.md](./docs/05-code-style.md).

## License

Contributions are licensed under the [Apache License 2.0](./LICENSE).

We do not require a separate CLA. Submitting a PR is treated as license acceptance.

## Code of conduct

All participants must follow the [Code of Conduct](./CODE_OF_CONDUCT.md).

## Questions and help

- General questions / usage — GitHub Discussions (when enabled)
- Bugs / feature requests — GitHub Issues
- Security vulnerabilities — please use a GitHub private security advisory rather than a public issue

## First-time contributors

- Start with issues labeled `good first issue`.
- Small PRs are welcome — typo fixes are great.
- If you get stuck, leave a comment on the issue.
