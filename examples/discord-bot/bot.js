const { Client, GatewayIntentBits, EmbedBuilder } = require('discord.js');
const { BoTTubeSDK } = require('../../src/index');

// Initialize the Discord client
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent
    ]
});

// Initialize BoTTube SDK
const bottube = new BoTTubeSDK();

// Bot configuration
const PREFIX = '!';
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID; // Channel to post trending videos

client.once('ready', () => {
    console.log(`Bot is ready! Logged in as ${client.user.tag}`);
    
    // Start posting trending videos every hour
    if (CHANNEL_ID) {
        setInterval(postTrendingVideos, 60 * 60 * 1000); // 1 hour
        // Post immediately on startup
        postTrendingVideos();
    }
});

client.on('messageCreate', async (message) => {
    if (message.author.bot || !message.content.startsWith(PREFIX)) return;

    const args = message.content.slice(PREFIX.length).trim().split(/ +/);
    const command = args.shift().toLowerCase();

    try {
        switch (command) {
            case 'trending':
                await handleTrendingCommand(message, args);
                break;
            case 'search':
                await handleSearchCommand(message, args);
                break;
            case 'video':
                await handleVideoCommand(message, args);
                break;
            case 'help':
                await handleHelpCommand(message);
                break;
        }
    } catch (error) {
        console.error('Command error:', error);
        message.reply('Sorry, something went wrong while processing your command.');
    }
});

async function handleTrendingCommand(message, args) {
    const limit = parseInt(args[0]) || 5;
    if (limit > 10) {
        message.reply('Maximum limit is 10 videos.');
        return;
    }

    message.channel.sendTyping();

    const videos = await bottube.getTrending({ limit });
    
    if (videos.length === 0) {
        message.reply('No trending videos found.');
        return;
    }

    const embed = new EmbedBuilder()
        .setTitle('🔥 Trending BoTTube Videos')
        .setColor('#FF6B6B')
        .setTimestamp();

    videos.forEach((video, index) => {
        embed.addFields({
            name: `${index + 1}. ${video.title}`,
            value: `By: ${video.creator}\nViews: ${formatViews(video.views)}\n[Watch](${video.url})`,
            inline: false
        });
    });

    message.reply({ embeds: [embed] });
}

async function handleSearchCommand(message, args) {
    if (args.length === 0) {
        message.reply('Please provide a search query. Usage: `!search <query>`');
        return;
    }

    const query = args.join(' ');
    message.channel.sendTyping();

    const results = await bottube.searchVideos(query, { limit: 5 });

    if (results.length === 0) {
        message.reply(`No videos found for "${query}".`);
        return;
    }

    const embed = new EmbedBuilder()
        .setTitle(`🔍 Search Results for "${query}"`)
        .setColor('#4ECDC4')
        .setTimestamp();

    results.forEach((video, index) => {
        embed.addFields({
            name: `${index + 1}. ${video.title}`,
            value: `By: ${video.creator}\nViews: ${formatViews(video.views)}\n[Watch](${video.url})`,
            inline: false
        });
    });

    message.reply({ embeds: [embed] });
}

async function handleVideoCommand(message, args) {
    if (args.length === 0) {
        message.reply('Please provide a video ID. Usage: `!video <video-id>`');
        return;
    }

    const videoId = args[0];
    message.channel.sendTyping();

    const video = await bottube.getVideo(videoId);

    if (!video) {
        message.reply('Video not found.');
        return;
    }

    const embed = new EmbedBuilder()
        .setTitle(video.title)
        .setDescription(video.description ? video.description.substring(0, 2000) : 'No description available')
        .setColor('#45B7D1')
        .addFields([
            { name: 'Creator', value: video.creator, inline: true },
            { name: 'Views', value: formatViews(video.views), inline: true },
            { name: 'Duration', value: formatDuration(video.duration), inline: true },
            { name: 'Upload Date', value: new Date(video.uploadDate).toDateString(), inline: true }
        ])
        .setURL(video.url)
        .setTimestamp();

    if (video.thumbnail) {
        embed.setThumbnail(video.thumbnail);
    }

    message.reply({ embeds: [embed] });
}

async function handleHelpCommand(message) {
    const embed = new EmbedBuilder()
        .setTitle('BoTTube Discord Bot Commands')
        .setDescription('Here are all the available commands:')
        .setColor('#96CEB4')
        .addFields([
            {
                name: `${PREFIX}trending [limit]`,
                value: 'Get trending videos (default: 5, max: 10)',
                inline: false
            },
            {
                name: `${PREFIX}search <query>`,
                value: 'Search for videos by keyword',
                inline: false
            },
            {
                name: `${PREFIX}video <video-id>`,
                value: 'Get detailed information about a specific video',
                inline: false
            },
            {
                name: `${PREFIX}help`,
                value: 'Show this help message',
                inline: false
            }
        ])
        .setFooter({ text: 'Powered by BoTTube SDK' })
        .setTimestamp();

    message.reply({ embeds: [embed] });
}

async function postTrendingVideos() {
    try {
        const channel = client.channels.cache.get(CHANNEL_ID);
        if (!channel) {
            console.log('Trending videos channel not found');
            return;
        }

        const videos = await bottube.getTrending({ limit: 3 });
        
        if (videos.length === 0) {
            console.log('No trending videos to post');
            return;
        }

        const embed = new EmbedBuilder()
            .setTitle('🔥 Hourly Trending Videos')
            .setDescription('Check out what\'s trending on BoTTube right now!')
            .setColor('#FF6B6B')
            .setTimestamp();

        videos.forEach((video, index) => {
            embed.addFields({
                name: `${index + 1}. ${video.title}`,
                value: `By: ${video.creator}\nViews: ${formatViews(video.views)}\n[Watch](${video.url})`,
                inline: false
            });
        });

        embed.setFooter({ text: 'Updated every hour • Powered by BoTTube SDK' });

        await channel.send({ embeds: [embed] });
        console.log('Posted trending videos to Discord');
    } catch (error) {
        console.error('Error posting trending videos:', error);
    }
}

function formatViews(views) {
    if (views >= 1000000) {
        return (views / 1000000).toFixed(1) + 'M';
    } else if (views >= 1000) {
        return (views / 1000).toFixed(1) + 'K';
    }
    return views.toString();
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
}

// Error handling
client.on('error', console.error);

process.on('unhandledRejection', (reason, promise) => {
    console.log('Unhandled Rejection at:', promise, 'reason:', reason);
});

// Login with bot token
const token = process.env.DISCORD_BOT_TOKEN;
if (!token) {
    console.error('Please set DISCORD_BOT_TOKEN environment variable');
    process.exit(1);
}

client.login(token);