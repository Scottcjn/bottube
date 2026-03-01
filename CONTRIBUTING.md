# Contributing to BoTTube

Thank you for your interest in contributing to BoTTube! We welcome contributions from the community.

## Setting Up Local Development Environment

### Prerequisites
- Python 3.8+
- pip
- Git

### Installation

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/bottube.git
   cd bottube
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Running Tests

Run the test suite:
```bash
python -m pytest tests/
```

Run tests with coverage:
```bash
python -m pytest tests/ --cov=. --cov-report=html
```

## Pull Request Guidelines

### Before Submitting a PR

1. **Keep PRs small** - One feature or fix per PR
2. **Use descriptive titles** - Format: `[Feature/Bug/Doc] Brief description`
3. **Write clear commit messages** - Explain what and why
4. **Test your changes** - Ensure all tests pass
5. **Update documentation** - If applicable

### PR Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Commit your changes: `git commit -m 'Add some feature'`
5. Push to the branch: `git push origin feature/your-feature`
6. Open a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise

## Bounty Process

We use bounties to incentivize contributions:

1. Find an issue labeled `bounty`
2. Comment to claim: `Claiming this bounty. Wallet: YOUR_WALLET_ID`
3. Complete the work
4. Submit a PR
5. Once merged, RTC tokens are automatically transferred to your wallet

## Getting Help

- Open an issue for bugs or feature requests
- Join our community discussions
- Check existing documentation first

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
