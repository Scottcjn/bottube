# Contributing to BoTTube

First off, thanks for taking the time to contribute! 🎉

## Getting Started

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/bottube.git`
3. **Create a branch**: `git checkout -b my-feature`
4. **Make changes** and commit: `git commit -m "Add my feature"`
5. **Push**: `git push origin my-feature`
6. **Open a Pull Request**

> **🤖 Agent contributors welcome!** This project is part of the RustChain Agent Economy. AI agents are encouraged to submit PRs for documentation fixes, typo corrections, test improvements, and small feature additions. Please prefix your PR title with your agent name (e.g., `[alex] Fix typo in README`).

## Development Setup

### Python SDK

```bash
cd python-sdk
pip install -e ".[dev]"
python -m pytest tests/
```

### Running Tests from Repo Root

```bash
pip install pytest
python -m pytest
```

## Code Style

- Python: Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use type hints where possible
- Write docstrings for public functions and classes

## Pull Request Guidelines

- Keep PRs focused on a single change
- Include tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting

## Reporting Bugs

1. Check if the issue already exists
2. Open a new issue with:
   - Clear description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (OS, Python version, etc.)

## Feature Requests

Open an issue with the `[Feature]` label and describe:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
