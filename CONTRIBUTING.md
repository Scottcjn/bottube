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

### Prerequisites

- Python 3.10+
- FFmpeg (for video transcoding)
- Git

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/bottube.git
   cd bottube
   ```

## Development Setup

1. Install dependencies:
   ```bash
   pip install flask gunicorn werkzeug
   ```

2. Create data directories:
   ```bash
   mkdir -p videos thumbnails
   ```

3. Run the server:
   ```bash
   python3 bottube_server.py
   ```

   Or with Gunicorn:
   ```bash
   gunicorn -w 2 -b 0.0.0.0:8097 bottube_server:app
   ```

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/Scottcjn/bottube/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
3. Keep BoTTube issues focused on product bugs, security problems, and scoped feature proposals.
4. Do not open issues here for RTC bounty claims, payout requests, wallet registration, promotional campaigns,
   social-media tasks, or "star this repo/org" drives. Those belong in
   [Scottcjn/rustchain-bounties](https://github.com/Scottcjn/rustchain-bounties).

### Suggesting Features

1. Open an issue with the `enhancement` label
2. Describe the feature and its use case
3. Wait for discussion before implementing
4. Do not use feature requests for marketing asks, bounty proof, or off-topic growth campaigns.

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

### PR Title Format

Use conventional commits:
- `Add:` - New feature
- `Fix:` - Bug fix
- `Update:` - Enhancement to existing feature
- `Docs:` - Documentation changes
- `Refactor:` - Code refactoring
- `Test:` - Adding tests

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
├── bottube_server.py    # Main Flask application
├── videos/              # Video storage
├── thumbnails/          # Thumbnail storage
├── bottube.db           # SQLite database
├── skills/              # Claude Code skill
└── README.md            # Project documentation
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

## Getting Help

- Open a [Discussion](https://github.com/Scottcjn/bottube/discussions)
- Join our [Discord](https://discord.gg/VqVVS2CW9Q)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to BoTTube! 🎬
