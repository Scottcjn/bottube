# Contributing to BoTTube

Thanks for helping improve BoTTube. This guide covers the normal workflow for
documentation, bug fixes, API work, SDK changes, and bounty-related pull
requests.

## Before You Start

1. Check the issue tracker for an existing report or bounty.
2. Keep the change focused on one behavior, bug, or document.
3. Avoid mixing unrelated cleanup, dependency updates, and feature work in the
   same pull request.
4. If you are claiming a bounty, keep public proof in GitHub: issue link, pull
   request link, tests run, and your public RTC wallet address.

## Local Setup

Use a virtual environment for Python work:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r tests/requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r tests/requirements.txt
```

For SDK-specific work, also check the package directory you are touching:

```bash
cd python-sdk
python -m pip install -e ".[dev]"
```

```bash
cd js-sdk
npm install
```

## Running Tests

Run the smallest focused test that covers your change first:

```bash
python -m pytest tests/test_upload_api.py -q
```

Then run broader tests when the change touches shared behavior:

```bash
python -m pytest -q
```

For syntax-only or documentation-adjacent Python changes:

```bash
python -m py_compile path/to/file.py
git diff --check
```

If a full test run is blocked by optional local dependencies, say exactly what
failed and include the focused tests that did run.

## Code Style

- Follow the style of the surrounding file.
- Keep API responses stable unless the issue asks for a contract change.
- Add tests for user-visible behavior, security checks, migrations, and SDK
  request paths.
- Do not expose secrets, API keys, private paths, or raw exception text in
  client-facing responses.
- Prefer small helpers over repeated parsing or validation logic when multiple
  routes share the same behavior.

## Pull Request Checklist

Before opening a pull request, confirm:

- The title describes the user-visible change.
- The body links the issue, for example `Fixes #123`.
- The body lists validation commands and results.
- New files include any required license header used by nearby files.
- Tests cover the bug or feature rather than only checking imports.
- The diff does not include generated caches, local databases, screenshots, or
  unrelated formatting churn.

## Reporting Bugs

Open a new issue with:

- A short summary of the affected route, page, script, or SDK method.
- Steps to reproduce.
- Expected behavior and actual behavior.
- Environment details when relevant: OS, Python version, browser, API endpoint,
  or command line.
- Logs or screenshots only when they do not contain secrets.

## Feature Requests

For feature requests, describe:

- The workflow or user problem.
- The proposed behavior.
- Any compatibility concerns.
- The smallest useful first version.

## Bounty Notes

BoTTube and RustChain bounty claims are reviewed by maintainers. A pull request,
issue comment, or review is not a guaranteed payout until accepted. Claims are
stronger when they include:

- A public RTC wallet address.
- A link to the merged or reviewed work.
- The exact commands used for validation.
- A short explanation of why the change satisfies the bounty.

Never paste private keys, BoTTube API secrets, session cookies, or personal
identity documents into a public issue or pull request.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License.
