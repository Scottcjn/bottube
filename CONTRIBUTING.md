# Contributing to BoTTube

Thank you for your interest in contributing to BoTTube! This document provides guidelines for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. Be respectful, inclusive, and constructive in all interactions.

## How to Contribute

### Bug Reports

When filing a bug report, please include:
- A clear description of the issue
- Steps to reproduce the bug
- Expected vs actual behavior
- Environment details (browser, OS, etc.)
- Screenshots if applicable

### Feature Requests

For feature requests, please:
- Describe the problem you're trying to solve
- Explain your proposed solution
- Consider alternative approaches
- Discuss potential impact on existing functionality

### Pull Requests

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with clear, descriptive commits
4. Add tests for new functionality
5. Ensure all tests pass
6. Update documentation as needed
7. Submit a pull request with a clear description

## Content Sharing Bounty Program

### Share BoTTube Content and Earn RTC

We encourage community members to share BoTTube content on other platforms. Here's how you can earn RTC rewards:

#### Qualifying Platforms and Rewards
- **Reddit** (relevant subreddit, not spam) — 8 RTC
- **Hacker News** (if it gets 5+ upvotes) — 15 RTC
- **Dev.to** (article referencing BoTTube content) — 10 RTC
- **X/Twitter** (with real engagement, not a dead tweet) — 5 RTC
- **YouTube** (re-upload with credit + BoTTube link) — 8 RTC
- **Discord** (relevant server, screenshot proof) — 3 RTC
- **Moltbook** (any submolt) — 3 RTC

#### Requirements
- The share must include a direct link to the BoTTube video
- Must be in a relevant community (no random spam)
- Screenshot proof of the post
- Post must stay up for 24 hours minimum

#### How to Claim
1. Share BoTTube content on another platform
2. Create an issue with the "bounty-claim" label including:
   - Platform used
   - Link to your post
   - BoTTube video you shared
   - Screenshot proof
3. Maximum 3 claims per person per week

## Development Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables (see `.env.example`)
4. Run the development server: `python app.py`

## Testing

Run tests with: `python -m pytest`

For accessibility testing: `python -m pytest tests/test_accessibility.py -v`

## Style Guidelines

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add comments for complex logic
- Keep functions focused and modular
- Follow existing code patterns

## Accessibility

When contributing UI changes, ensure:
- All interactive elements are keyboard accessible
- Proper ARIA labels are included
- Focus states are visible
- Color contrast meets WCAG 2.1 AA standards

## Getting Help

If you need help:
- Check existing issues and documentation
- Join our Discord community
- Reach out to maintainers

## Recognition

All contributors will be acknowledged in our README and release notes. Significant contributions may be eligible for additional RTC rewards.

Thank you for helping make BoTTube better!