# Discord Bot Example

This example demonstrates how to build a Discord bot using the BoTTube JavaScript SDK to interact with YouTube content.

## Prerequisites

- Node.js 16 or higher
- Discord bot token
- BoTTube API access

## Setup

1. **Install dependencies**
   ```bash
   npm install
   ```

2. **Create a Discord application and bot**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application
   - Go to the "Bot" section and create a bot
   - Copy the bot token

3. **Configure environment variables**
   Create a `.env` file in this directory:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   BOTTUBE_API_KEY=your_bottube_api_key_here
   ```

4. **Invite the bot to your server**
   - In the Discord Developer Portal, go to OAuth2 → URL Generator
   - Select "bot" scope
   - Select necessary permissions (Send Messages, Read Message History, etc.)
   - Use the generated URL to invite the bot to your server

## Running the Bot

```bash
npm start
```

## Available Commands

- `!search <query>` - Search for YouTube videos
- `!trending` - Get trending videos
- `!channel <channel_name>` - Get channel information
- `!help` - Show available commands

## Features

- Real-time YouTube search results
- Trending video notifications
- Channel statistics and information
- Interactive embed messages with video previews
- Error handling and user feedback

## Customization

You can extend the bot by:
- Adding more BoTTube SDK features
- Creating custom commands
- Implementing scheduled tasks for trending updates
- Adding database storage for user preferences

## Support

For issues with the BoTTube SDK, please refer to the main repository documentation.