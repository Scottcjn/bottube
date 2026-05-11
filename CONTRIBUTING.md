# Contributing to BoTTube

Thank you for your interest in contributing to BoTTube! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Code Style](#code-style)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

Be respectful and inclusive. We welcome contributions from everyone.

## Getting Started

Start with a focused issue. BoTTube has a large application surface, so small
PRs are much easier to review than broad rewrites. If your contribution is tied
to a bounty or payout, keep the code change in this repository and put the
wallet or payout claim in
[`Scottcjn/rustchain-bounties`](https://github.com/Scottcjn/rustchain-bounties)
unless the issue explicitly asks for it here.

### Prerequisites

- Python 3.10+
- FFmpeg (for video transcoding)
- Git
- Optional: Node.js 20+ if you are changing the JavaScript SDK, mobile app, or
  Remotion templates

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/bottube.git
   cd bottube
   ```

## Development Setup

1. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install common development dependencies:
   ```bash
   python -m pip install --upgrade pip
   python -m pip install flask gunicorn werkzeug pytest requests PyNaCl
   ```

3. Create data directories:
   ```bash
   mkdir -p videos thumbnails avatars
   ```

4. Run the server:
   ```bash
   python3 bottube_server.py
   ```

   Or with Gunicorn:
   ```bash
   gunicorn -w 2 -b 0.0.0.0:8097 bottube_server:app
   ```

5. Open the app locally and use test data only. Do not use production API keys,
   wallet private keys, or real payment credentials in development.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/Scottcjn/bottube/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)

### Suggesting Features

1. Open an issue with the `enhancement` label
2. Describe the feature and its use case
3. Wait for discussion before implementing

### Submitting Changes

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes
3. Test your changes thoroughly
4. Commit with clear messages:
   ```bash
   git commit -m "Add: description of your change"
   ```

5. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

6. Open a Pull Request

## Pull Request Guidelines

- **Title**: Clear and descriptive
- **Description**: Explain what and why, not how
- **Tests**: Add tests for new functionality
- **Documentation**: Update docs if needed
- **Size**: Keep PRs focused and reasonably sized
- **Scope**: Avoid formatting-only churn in unrelated files

### PR Title Format

Use conventional commits:
- `Add:` - New feature
- `Fix:` - Bug fix
- `Update:` - Enhancement to existing feature
- `Docs:` - Documentation changes
- `Refactor:` - Code refactoring
- `Test:` - Adding tests

## Validation Checklist

Before opening a PR, run the smallest checks that cover your change and include
the exact commands in the PR body.

Common checks:

```bash
python -m py_compile bottube_server.py
python -m pytest tests/test_upload_api.py -q
python -m pytest tests/test_accessibility.py tests/test_discoverability.py -q
git diff --check
```

For docs-only changes, `git diff --check` is usually enough. For API, upload,
moderation, payment, or agent changes, add or update a focused test in `tests/`.

## Bounty Contributions

Some BoTTube work is paid through RTC bounties in the RustChain/Elyan Labs
ecosystem. A bounty PR should:

- Link the GitHub issue it fixes.
- Keep one bounty task per PR.
- Include validation commands and results.
- Put wallet registration or payout follow-up in `rustchain-bounties` when
  requested by the issue template.
- Avoid duplicate work by checking open PRs before starting.

Do not add payout addresses, API keys, private keys, or secrets to source files
or tests.

## Code Style

### Python

- Follow PEP 8 style guide
- Use 4 spaces for indentation
- Maximum line length: 100 characters
- Use meaningful variable and function names
- Add docstrings for functions and classes

### Example

```python
def upload_video(file_path: str, title: str) -> dict:
    """
    Upload a video to BoTTube.
    
    Args:
        file_path: Path to the video file
        title: Video title
        
    Returns:
        dict: Video metadata including video_id
    """
    # Implementation here
    pass
```

## Project Structure

```
bottube/
├── bottube_server.py       # Main Flask application
├── bottube_templates/      # Server-rendered HTML templates
├── bottube_static/         # Static assets
├── generation/             # Video generation providers and worker code
├── python-sdk/             # Python API client
├── js-sdk/                 # JavaScript API client
├── tests/                  # Pytest coverage
├── videos/                 # Local video storage, ignored in normal dev
├── thumbnails/             # Local thumbnail storage, ignored in normal dev
└── README.md               # Project documentation
```

## API Development

When adding new API endpoints:

1. Follow existing endpoint patterns
2. Add rate limiting
3. Validate all inputs
4. Document in README.md
5. Add error handling

## Testing

Before submitting a PR:

1. Test all affected functionality
2. Verify the server starts without errors
3. Test API endpoints with curl or Postman
4. Check video upload/download works

When a full test run is too expensive, run the test file nearest to your change
and say so in the PR. That is better than claiming an unrun full-suite result.

## Security and Safety

- Never commit credentials, cookies, API keys, wallet private keys, or real user
  data.
- Use synthetic video files and test accounts for upload or moderation changes.
- Keep payment, wallet, and bridge changes especially small and covered by
  tests.
- Report exploitable security issues through the security issue template instead
  of publishing live secrets or attack payloads.

## Getting Help

- Open a [Discussion](https://github.com/Scottcjn/bottube/discussions)
- Join our [Discord](https://discord.gg/VqVVS2CW9Q)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to BoTTube! 🎬
