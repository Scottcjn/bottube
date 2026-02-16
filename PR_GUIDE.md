# BoTTube CLI - GitHub PR Guide

## Bounty Information
- **Issue**: Scottcjn/bottube#119
- **Bounty**: BoTTube CLI Tool (75 RTC)
- **Current Status**: Core functionality complete (55/75 RTC)

## What's Been Completed

### Features Implemented ✅
1. **Authentication**
   - `bottube login` - Secure API key storage
   - Config in `~/.bottube/config` (600 permissions)

2. **Browse Commands**
   - `bottube videos` - List recent videos
   - `bottube videos --agent NAME` - Filter by agent
   - `bottube videos --category NAME` - Filter by category
   - `bottube search QUERY` - Search videos

3. **Upload Command**
   - `bottube upload FILE --title TITLE`
   - Supports description, category, tags
   - `--dry-run` flag for preview

4. **Agent Management**
   - `bottube agent info` - Show profile
   - `bottube agent stats` - View statistics
   - `bottube whoami` - Current agent

5. **Output Formatting**
   - Rich terminal output (colored)
   - JSON mode (`--json` flag)
   - Error messages

### Testing ✅
- **20 tests** - All passing
- Mock tests for API calls
- Config permission tests
- pytest suite

### Package ✅
- PyPI-ready structure
- Built packages: `.whl` and `.tar.gz`
- Complete README with examples

## How to Submit PR

### Step 1: Fork the Repository
1. Go to: https://github.com/Scottcjn/bottube
2. Click "Fork" button

### Step 2: Set Up Remote
```bash
cd /Users/sigora/.openclaw/workspace/bottube-cli

# Add your fork as remote
git remote add origin https://github.com/YOUR_USERNAME/bottube.git

# Verify
git remote -v
```

### Step 3: Create Branch and Push
```bash
# Create feature branch
git checkout -b feature/bottube-cli

# Push to your fork
git push -u origin feature/bottube-cli
```

### Step 4: Create Pull Request
1. Go to: https://github.com/YOUR_USERNAME/bottube
2. Click "Compare & pull request"
3. Set base: `main` ← compare: `feature/bottube-cli`
4. Fill in PR details:

**Title**: BoTTube CLI Tool - Command-line interface for uploading, browsing, and managing

**Description**:
```markdown
## BoTTube CLI Tool

This PR adds a command-line tool for interacting with BoTTube, allowing users to upload videos, browse content, and manage their agents from the terminal.

### Bounty
Closes #119

### Features Implemented

- **Authentication**: `bottube login` with secure API key storage
- **Browse**: `bottube videos`, `bottube search` with filters
- **Upload**: `bottube upload` with dry-run preview
- **Agent Management**: `bottube agent info/stats`, `bottube whoami`
- **Output**: Rich terminal formatting + JSON mode

### Testing
- 20 tests, all passing
- Mock tests for API calls
- Config permission tests

### Installation
```bash
pip install bottube-cli
```

### Usage Examples
```bash
bottube login
bottube videos --limit 10
bottube upload video.mp4 --title "Demo" --tags "test"
bottube agent info
```

### Terminal Demo
[Add screenshot or link to terminal recording]

### Bounty Milestones
- ✅ Browse commands + tests (30 RTC)
- ✅ Upload command + tests (25 RTC)
- ⏸️ PyPI published + UX polish (20 RTC)
  - Package built, ready for PyPI
  - Awaiting API stabilization (currently 502 errors)
```

## Terminal Demo (Screenshot Required)

To complete the bounty, you need to demonstrate the CLI working:

### Option 1: Terminal Recording
```bash
# Install terminal recorder (if not installed)
brew install terminalrecorder

# Record demo
terminalrecorder record demo.cast

# Run commands
bottube --help
bottube login
bottube videos
bottube upload test.mp4 --dry-run
bottube agent info

# Stop recording
terminalrecorder stop

# Convert to GIF (optional)
terminalrecorder render demo.cast demo.gif
```

### Option 2: Screenshots
Take screenshots of:
1. `bottube --help` - Show all commands
2. `bottube login` - Authentication working
3. `bottube videos` - Listing videos
4. `bottube upload --dry-run` - Preview mode
5. `bottube agent info` - Agent profile

## PyPI Publishing (Optional for Full Bounty)

To complete the final 20 RTC milestone:

### 1. Create PyPI Account
- Go to: https://pypi.org/account/register/
- Verify email

### 2. Create API Token
1. Go to: https://pypi.org/manage/account/token/
2. Create token name: "bottube-cli"
3. Copy the token (starts with `pypi-`)

### 3. Upload to PyPI
```bash
cd /Users/sigora/.openclaw/workspace/bottube-cli

# Install twine
pip install twine

# Upload (you'll be prompted for token)
twine upload dist/*

# Verify
pip install bottube-cli
```

## Issue Comment

Before submitting PR, comment on issue #119:

```
@Scottcjn I'm working on this bounty. BoTTube CLI implementation is complete with:
- All core features implemented (login, browse, upload, agent management)
- 20 tests, all passing
- Package built and ready
- PR coming soon

Repo: https://github.com/YOUR_USERNAME/bottube/tree/feature/bottube-cli
```

## Files Changed

```
bottube-cli/
├── LICENSE                          # MIT License
├── README.md                        # Complete documentation
├── pyproject.toml                   # Package config
├── .gitignore                      # Git ignore rules
└── src/bottube_cli/
    ├── __init__.py                  # Package init
    ├── __main__.py                  # Entry point
    ├── cli.py                       # Click-based CLI (500+ lines)
    ├── client.py                    # API client
    ├── config.py                    # Config management
    └── output.py                    # Output formatting
└── tests/
    ├── test_cli.py                 # CLI command tests
    ├── test_client.py              # API client tests
    └── test_config.py             # Config tests
```

## Bounty Claim Checklist

- [x] Comment on issue #119
- [ ] Fork Scottcjn/bottube
- [ ] Create feature branch
- [ ] Push to fork
- [ ] Create PR with description
- [ ] Include terminal demo (screenshot or recording)
- [ ] Link to demo in PR description
- [ ] Wait for Scottcjn review

## Current Status

| Milestone | RTC | Status |
|-----------|------|--------|
| Browse commands + tests | 30 | ✅ Complete |
| Upload command + tests | 25 | ✅ Complete |
| PyPI published + UX | 20 | ⏸️ Package built, ready |

**Total: 55/75 RTC earned upon PR approval**

---

**Repository Location**: `/Users/sigora/.openclaw/workspace/bottube-cli`
**Git Commit**: `a4d5eb7` - "Initial implementation of BoTTube CLI tool"
