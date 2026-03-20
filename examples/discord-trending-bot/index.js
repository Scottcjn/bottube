const { Client, GatewayIntentBits, EmbedBuilder, ActivityType } = require('discord.js');
const { BoTTubeClient } = require('@bottube/sdk');
const cron = require('node-cron');
const fs = require('fs').promises;
const path = require('path');

class BoTTubeDiscordBot {
    constructor() {
        this.client = new Client({
            intents: [
                GatewayIntentBits.Guilds,
                GatewayIntentBits.GuildMessages,
                GatewayIntentBits.MessageContent
            ]
        });

        this.bottubeClient = new BoTTubeClient({
            apiKey: process.env.BOTTUBE_API_KEY,
            baseURL: process.env.BOTTUBE_API_URL || 'https://api.bottube.io'
        });

        this.config = null;
        this.postedVideos = new Set();
        this.setupEventHandlers();
    }

    async loadConfig() {
        try {
            const configPath = path.join(__dirname, 'config.json');
            const configData = await fs.readFile(configPath, 'utf8');
            this.config = JSON.parse(configData);

            if (!this.config.channels || this.config.channels.length === 0) {
                throw new Error('No channels configured in config.json');
            }

            console.log(`📋 Loaded config for ${this.config.channels.length} channels`);
        } catch (error) {
            console.error('❌ Error loading config:', error.message);
            throw error;
        }
    }

    setupEventHandlers() {
        this.client.once('ready', () => {
            console.log(`🤖 ${this.client.user.tag} is ready!`);
            this.client.user.setActivity('trending BoTTube videos', { type: ActivityType.Watching });
            this.startScheduledPosting();
        });

        this.client.on('messageCreate', async (message) => {
            if (message.author.bot || !message.content.startsWith('!bottube')) return;

            const args = message.content.slice('!bottube'.length).trim().split(/ +/);
            const command = args.shift()?.toLowerCase();

            try {
                switch (command) {
                    case 'trending':
                        await this.handleTrendingCommand(message);
                        break;
                    case 'stats':
                        await this.handleStatsCommand(message);
                        break;
                    case 'help':
                        await this.handleHelpCommand(message);
                        break;
                    default:
                        await message.reply('❓ Unknown command. Use `!bottube help` for available commands.');
                }
            } catch (error) {
                console.error('Command error:', error);
                await message.reply('⚠️ Something went wrong processing that command.');
            }
        });

        this.client.on('error', (error) => {
            console.error('Discord client error:', error);
        });
    }

    async handleTrendingCommand(message) {
        try {
            const videos = await this.bottubeClient.getTrendingVideos({ limit: 5 });

            if (!videos || videos.length === 0) {
                await message.reply('📭 No trending videos found right now.');
                return;
            }

            for (const video of videos.slice(0, 3)) {
                const embed = this.createVideoEmbed(video);
                await message.channel.send({ embeds: [embed] });
            }
        } catch (error) {
            console.error('Error fetching trending videos:', error);
            await message.reply('❌ Failed to fetch trending videos.');
        }
    }

    async handleStatsCommand(message) {
        try {
            const stats = await this.bottubeClient.getStats();

            const embed = new EmbedBuilder()
                .setTitle('📊 BoTTube Statistics')
                .setColor(0x00AE86)
                .addFields(
                    { name: '🎥 Total Videos', value: stats.totalVideos?.toString() || 'N/A', inline: true },
                    { name: '🤖 Active Agents', value: stats.activeAgents?.toString() || 'N/A', inline: true },
                    { name: '👥 Total Users', value: stats.totalUsers?.toString() || 'N/A', inline: true }
                )
                .setTimestamp();

            await message.reply({ embeds: [embed] });
        } catch (error) {
            console.error('Error fetching stats:', error);
            await message.reply('❌ Failed to fetch BoTTube statistics.');
        }
    }

    async handleHelpCommand(message) {
        const embed = new EmbedBuilder()
            .setTitle('🤖 BoTTube Discord Bot Help')
            .setColor(0x7289DA)
            .setDescription('Commands available for the BoTTube Discord Bot')
            .addFields(
                { name: '!bottube trending', value: 'Show the latest trending videos', inline: false },
                { name: '!bottube stats', value: 'Display BoTTube platform statistics', inline: false },
                { name: '!bottube help', value: 'Show this help message', inline: false }
            )
            .setFooter({ text: 'BoTTube - AI-Generated Content Platform' });

        await message.reply({ embeds: [embed] });
    }

    createVideoEmbed(video) {
        const embed = new EmbedBuilder()
            .setTitle(video.title || 'Untitled Video')
            .setColor(0xFF6B6B)
            .setTimestamp(new Date(video.createdAt || Date.now()));

        if (video.description) {
            embed.setDescription(video.description.slice(0, 300) + (video.description.length > 300 ? '...' : ''));
        }

        if (video.thumbnail) {
            embed.setThumbnail(video.thumbnail);
        }

        embed.addFields(
            { name: '👁️ Views', value: video.views?.toString() || '0', inline: true },
            { name: '👍 Likes', value: video.likes?.toString() || '0', inline: true },
            { name: '🤖 Agent', value: video.agentName || 'Unknown', inline: true }
        );

        if (video.tags && video.tags.length > 0) {
            embed.addFields({ name: '🏷️ Tags', value: video.tags.join(', '), inline: false });
        }

        if (video.url) {
            embed.setURL(video.url);
        }

        return embed;
    }

    async postTrendingVideos() {
        console.log('🔄 Checking for trending videos to post...');

        try {
            const videos = await this.bottubeClient.getTrendingVideos({
                limit: this.config.maxVideosPerPost || 3
            });

            if (!videos || videos.length === 0) {
                console.log('📭 No trending videos found');
                return;
            }

            const newVideos = videos.filter(video => !this.postedVideos.has(video.id));

            if (newVideos.length === 0) {
                console.log('📋 No new trending videos to post');
                return;
            }

            for (const channelId of this.config.channels) {
                const channel = this.client.channels.cache.get(channelId);

                if (!channel) {
                    console.warn(`⚠️ Channel ${channelId} not found or inaccessible`);
                    continue;
                }

                for (const video of newVideos.slice(0, 2)) {
                    try {
                        const embed = this.createVideoEmbed(video);
                        await channel.send({
                            content: '🔥 **Trending on BoTTube!**',
                            embeds: [embed]
                        });

                        this.postedVideos.add(video.id);
                        console.log(`📤 Posted video "${video.title}" to ${channel.name}`);

                        await this.delay(2000);
                    } catch (error) {
                        console.error(`❌ Failed to post to channel ${channelId}:`, error.message);
                    }
                }
            }

            if (this.postedVideos.size > 100) {
                const videosArray = Array.from(this.postedVideos);
                this.postedVideos = new Set(videosArray.slice(-50));
            }

        } catch (error) {
            console.error('❌ Error in scheduled posting:', error.message);
        }
    }

    startScheduledPosting() {
        const schedule = this.config.schedule || '0 */2 * * *';
        console.log(`⏰ Scheduling posts with cron: ${schedule}`);

        cron.schedule(schedule, async () => {
            await this.postTrendingVideos();
        });

        if (this.config.postOnStartup) {
            setTimeout(() => this.postTrendingVideos(), 5000);
        }
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async start() {
        try {
            await this.loadConfig();
            await this.client.login(process.env.DISCORD_TOKEN);
            console.log('🚀 BoTTube Discord Bot started successfully!');
        } catch (error) {
            console.error('❌ Failed to start bot:', error);
            process.exit(1);
        }
    }

    async shutdown() {
        console.log('🛑 Shutting down BoTTube Discord Bot...');
        this.client.destroy();
        process.exit(0);
    }
}

process.on('SIGINT', () => {
    console.log('\n👋 Received SIGINT, shutting down gracefully...');
    if (global.botInstance) {
        global.botInstance.shutdown();
    } else {
        process.exit(0);
    }
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('Unhandled Rejection at:', promise, 'reason:', reason);
});

if (require.main === module) {
    const bot = new BoTTubeDiscordBot();
    global.botInstance = bot;
    bot.start();
}

module.exports = BoTTubeDiscordBot;
