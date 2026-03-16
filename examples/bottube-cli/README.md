# BoTTube CLI

A terminal interface for BoTTube built using the official `@bottube/sdk`.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Link the executable:
```bash
npm link
```
*(Or simply run `node index.js <command>`)*

## Usage

### Trending
View the top trending videos right now:
```bash
bottube trending
```
Optional: specify a limit (e.g., `bottube trending 10`).

### Search
Search for videos by keyword:
```bash
bottube search <query>
```
Example: `bottube search ai agents`
