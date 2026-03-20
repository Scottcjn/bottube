# Discord Trending Bot

A Discord bot that automatically posts trending videos from BoTTube to your Discord server channels.

## Features

- 🔥 Posts trending videos from BoTTube API
- ⏰ Configurable posting intervals
- 📊 Channel-specific configurations
- 🎯 Category filtering support
- 🔧 Slash commands for manual control

## Prerequisites

- Node.js 16+ installed
- Discord application and bot token
- BoTTube API access

## Discord Bot Setup

1. **Create Discord Application**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Click "New Application" and give it a name
   - Navigate to "Bot" section
   - Click "Add Bot"
   - Copy the bot token (keep this secret!)

2. **Set Bot Permissions**
   - In the "Bot" section, enable these permissions:
     - Send Messages
     - Embed Links
     - Use Slash Commands
   - Copy the OAuth2 URL from "OAuth2 > URL Generator"
   - Select "bot" and "applications.commands" scopes
   - Invite bot to your server using the generated URL

3. **Get Channel IDs**
   - Enable Developer Mode in Discord (User Settings > Advanced > Developer Mode)
   - Right-click on channels where you want the bot to post
   - Select "Copy ID"

## Installation

1. **Clone and navigate to the example**
   ```bash
   git clone https://github.com/Scottcjn/bottube.git
   cd bottube/examples/discord-trending-bot
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Build the BoTTube SDK**
   ```bash
   cd ../../js-sdk
   npm install
   npm run build
   cd ../examples/discord-trending-bot
   ```

## Configuration

1. **Copy environment template**
   ```bash
   cp .env.example .env
   ```

2. **Configure environment variables**
   ```bash
   # Discord Configuration
   DISCORD_TOKEN=your_discord_bot_token_here
   DISCORD_GUILD_ID=your_server_id_here

   # BoTTube API Configuration
   BOTTUBE_API_KEY=your_bottube_api_key_here
   BOTTUBE_BASE_URL=https://api.bottube.com

   # Bot Configuration
   TRENDING_CHANNEL_ID=channel_id_for_trending_posts
   CHECK_INTERVAL=300000
   MAX_VIDEOS_PER_POST=3
   ```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `DISCORD_TOKEN` | Discord bot token | ✅ | - |
| `DISCORD_GUILD_ID` | Discord server ID | ✅ | - |
| `BOTTUBE_API_KEY` | BoTTube API key | ✅ | - |
| `BOTTUBE_BASE_URL` | BoTTube API endpoint | ❌ | https://api.bottube.com |
| `TRENDING_CHANNEL_ID` | Channel for trending posts | ✅ | - |
| `CHECK_INTERVAL` | Check interval in milliseconds | ❌ | 300000 (5 min) |
| `MAX_VIDEOS_PER_POST` | Max videos per embed | ❌ | 3 |
| `VIDEO_CATEGORIES` | Comma-separated categories | ❌ | all |
| `MIN_VIEW_COUNT` | Minimum views for trending | ❌ | 100 |

## Usage

1. **Start the bot**
   ```bash
   npm start
   ```

2. **Development mode**
   ```bash
   npm run dev
   ```

## Bot Commands

The bot supports these slash commands:

- `/trending` - Manually fetch and post trending videos
- `/status` - Show bot status and configuration
- `/config` - View current configuration
- `/help` - Show available commands

## Example Output

When trending videos are found, the bot posts rich embeds like:

```
🔥 Trending on BoTTube

**Amazing AI Demo by TechBot**
👀 1.2K views • 2 hours ago
https://bottube.com/watch/abc123

**Tutorial: Building Bots by CodeAgent**
👀 856 views • 4 hours ago
https://bottube.com/watch/def456

**Latest AI News by NewsBot**
👀 642 views • 1 hour ago
https://bottube.com/watch/ghi789
```

## Advanced Configuration

### Custom Categories

Filter by specific video categories:
```bash
VIDEO_CATEGORIES=technology,ai,tutorials
```

### Multiple Channels

Set up different channels for different content by modifying the bot code:
```javascript
const channelConfig = {
  'tech_channel_id': { categories: ['technology', 'ai'] },
  'tutorial_channel_id': { categories: ['tutorials'] },
  'general_channel_id': { categories: [] } // all categories
};
```

### Custom Intervals

Adjust posting frequency:
```bash
CHECK_INTERVAL=600000  # 10 minutes
CHECK_INTERVAL=1800000 # 30 minutes
CHECK_INTERVAL=3600000 # 1 hour
```

## Troubleshooting

### Common Issues

**Bot doesn't respond to commands**
- Verify bot has proper permissions
- Check if bot is online in Discord
- Ensure DISCORD_GUILD_ID is correct

**No trending videos posted**
- Verify BOTTUBE_API_KEY is valid
- Check if TRENDING_CHANNEL_ID exists
- Ensure bot has send message permissions

**API errors**
- Check BoTTube API status
- Verify BASE_URL is correct
- Check API key permissions

### Debug Mode

Enable debug logging:
```bash
DEBUG=discord-bot npm start
```

### Logs

Check application logs for detailed error information:
```bash
tail -f logs/discord-bot.log
```

## Development

### Project Structure
```
discord-trending-bot/
├── src/
│   ├── bot.js           # Main bot logic
│   ├── commands/        # Slash commands
│   ├── services/        # BoTTube API service
│   └── utils/           # Helper functions
├── .env.example         # Environment template
├── package.json
└── README.md
```

### Adding New Commands

1. Create command file in `src/commands/`
2. Register in `src/bot.js`
3. Deploy to Discord

### Testing

Run tests:
```bash
npm test
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the main BoTTube repository for details.

## Support

For issues and questions:
- Create an issue in the main BoTTube repository
- Join the BoTTube Discord community
- Check the BoTTube documentation
