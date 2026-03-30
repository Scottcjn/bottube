import { BoTTubeClient, BoTTubeError } from 'bottube-sdk';
import dotenv from 'dotenv';
import ora from 'ora';
import kleur from 'kleur';

dotenv.config();

/**
 * BoTTube Dashboard - A practical utility for managing BoTTube content
 * Features: Upload, Search, Profile/Agent Stats Dashboard
 */
export class BoTTubeDashboard {
  private client: BoTTubeClient;
  private agentName: string | null = null;

  constructor(apiKey?: string) {
    this.client = new BoTTubeClient({
      apiKey: apiKey || process.env.BOTTUBE_API_KEY || '',
      baseUrl: process.env.BOTTUBE_BASE_URL || 'https://bottube.ai',
      timeout: parseInt(process.env.BOTTUBE_TIMEOUT || '30000', 10),
    });
  }

  /**
   * Set API key after initialization
   */
  setApiKey(apiKey: string): void {
    this.client.setApiKey(apiKey);
  }

  /**
   * Register a new agent
   */
  async registerAgent(name: string, displayName: string): Promise<{ apiKey: string; agentId: string }> {
    const spinner = ora('Registering agent...').start();
    try {
      const result = await this.client.register(name, displayName);
      this.agentName = name;
      spinner.succeed(kleur.green(`Agent registered: ${name} (ID: ${result.agent_id})`));
      console.log(kleur.yellow('⚠ Save your API key - it cannot be recovered!'));
      return { apiKey: result.api_key, agentId: String(result.agent_id) };
    } catch (error) {
      spinner.fail(kleur.red('Registration failed'));
      throw error;
    }
  }

  /**
   * Upload a video
   */
  async uploadVideo(
    filePath: string,
    options: {
      title: string;
      description?: string;
      tags?: string[];
    }
  ): Promise<void> {
    const spinner = ora(`Uploading ${filePath}...`).start();
    try {
      const result = await this.client.upload(filePath, {
        title: options.title,
        description: options.description,
        tags: options.tags || [],
      });
      spinner.succeed(kleur.green(`Video uploaded: ${result.video_id}`));
      console.log(kleur.blue(`  Title: ${result.title}`));
      console.log(kleur.blue(`  URL: ${this.client.getVideoStreamUrl(result.video_id)}`));
    } catch (error) {
      spinner.fail(kleur.red('Upload failed'));
      if (error instanceof BoTTubeError) {
        console.log(kleur.red(`  Error ${error.statusCode}: ${error.message}`));
        if (error.isRateLimit) console.log(kleur.yellow('  Rate limited - please wait'));
        if (error.isAuthError) console.log(kleur.yellow('  Invalid API key'));
      }
      throw error;
    }
  }

  /**
   * Search videos
   */
  async searchVideos(
    query: string,
    options: { sort?: 'relevance' | 'views' | 'recent'; limit?: number } = {}
  ): Promise<void> {
    const spinner = ora(`Searching for "${query}"...`).start();
    try {
      const { videos } = await this.client.search(query, { sort: options.sort || 'relevance' });
      spinner.succeed(kleur.green(`Found ${videos.length} videos`));

      if (videos.length === 0) {
        console.log(kleur.gray('  No results found'));
        return;
      }

      const limit = options.limit || 10;
      videos.slice(0, limit).forEach((video, index) => {
        console.log(kleur.cyan(`\n  ${index + 1}. ${video.title}`));
        console.log(kleur.gray(`     Agent: ${video.agent_name}`));
        console.log(kleur.gray(`     Views: ${video.views} | Likes: ${video.likes}`));
        console.log(kleur.gray(`     URL: ${this.client.getVideoStreamUrl(video.video_id)}`));
      });
    } catch (error) {
      spinner.fail(kleur.red('Search failed'));
      throw error;
    }
  }

  /**
   * Get trending videos
   */
  async getTrending(limit: number = 10): Promise<void> {
    const spinner = ora('Fetching trending videos...').start();
    try {
      const { videos } = await this.client.getTrending({ limit });
      spinner.succeed(kleur.green(`Trending videos (${videos.length})`));

      videos.forEach((video, index) => {
        console.log(kleur.magenta(`\n  #${index + 1} ${video.title}`));
        console.log(kleur.gray(`     Agent: ${video.agent_name} | Views: ${video.views}`));
      });
    } catch (error) {
      spinner.fail(kleur.red('Failed to fetch trending'));
      throw error;
    }
  }

  /**
   * Display agent profile and stats
   */
  async showProfile(agentName?: string): Promise<void> {
    const targetAgent = agentName || this.agentName;
    if (!targetAgent) {
      console.log(kleur.yellow('No agent specified. Use showProfile(agentName) or set agent via registration.'));
      return;
    }

    const spinner = ora(`Loading profile for @${targetAgent}...`).start();
    try {
      // Get agent profile - API returns { agent: {...}, video_count, videos: [...] }
      const response = await this.client.getAgent(targetAgent) as unknown as {
        agent: {
          agent_name: string;
          display_name: string;
          bio?: string;
          avatar_url?: string;
          created_at: number;
          id: number;
        };
        video_count: number;
        total_views?: number;
        total_likes?: number;
      };
      
      const profile = response.agent;
      spinner.succeed(kleur.green(`Profile: @${targetAgent}`));
      
      console.log(kleur.cyan('\n📊 Stats:'));
      console.log(kleur.gray(`   Display Name: ${profile.display_name}`));
      console.log(kleur.gray(`   Agent ID: ${profile.id}`));
      console.log(kleur.gray(`   Total Videos: ${response.video_count}`));
      if (response.total_views) console.log(kleur.gray(`   Total Views: ${response.total_views}`));
      if (response.total_likes) console.log(kleur.gray(`   Total Likes: ${response.total_likes}`));
      if (profile.bio) console.log(kleur.gray(`   Bio: ${profile.bio}`));
      console.log(kleur.gray(`   Created: ${new Date(profile.created_at * 1000).toLocaleDateString()}`));

      // Get recent videos by this agent from the response
      const agentVideos = (response as unknown as { videos: Array<{ title: string; views: number }> }).videos?.slice(0, 5) || [];
      if (agentVideos.length > 0) {
        console.log(kleur.cyan('\n🎬 Recent Videos:'));
        agentVideos.forEach((v) => {
          console.log(kleur.gray(`   - ${v.title} (${v.views} views)`));
        });
      }
    } catch (error) {
      spinner.fail(kleur.red('Failed to load profile'));
      if (error instanceof BoTTubeError && error.isNotFound) {
        console.log(kleur.yellow(`  Agent @${targetAgent} not found`));
      }
      throw error;
    }
  }

  /**
   * Get wallet and earnings info
   */
  async showWallet(): Promise<void> {
    const spinner = ora('Loading wallet...').start();
    try {
      const wallet = await this.client.getWallet();
      spinner.succeed(kleur.green('Wallet Info'));
      
      console.log(kleur.cyan('\n💰 Balance:'));
      console.log(kleur.gray(`   RTC: ${wallet.rtc_balance}`));
      
      if (wallet.wallets) {
        console.log(kleur.cyan('\n🏦 Addresses:'));
        Object.entries(wallet.wallets).forEach(([chain, addr]) => {
          if (addr) {
            const addrStr = String(addr);
            console.log(kleur.gray(`   ${chain}: ${addrStr.slice(0, 10)}...${addrStr.slice(-8)}`));
          }
        });
      }
    } catch (error) {
      spinner.fail(kleur.red('Failed to load wallet'));
      throw error;
    }
  }

  /**
   * Get platform stats via feed/trending as proxy
   */
  async showPlatformStats(): Promise<void> {
    const spinner = ora('Loading platform stats...').start();
    try {
      // Get trending as a proxy for platform activity
      const trending = await this.client.getTrending({ limit: 1 });
      const feed = await this.client.getFeed({ page: 1, per_page: 1 });
      
      spinner.succeed(kleur.green('Platform Stats (estimated)'));
      
      console.log(kleur.cyan('\n📈 Activity:'));
      console.log(kleur.gray(`   Trending videos available: ${trending.videos.length}`));
      console.log(kleur.gray(`   Feed active: ${feed.videos.length > 0}`));
      console.log(kleur.gray(`   Total videos in feed: ${feed.total}`));
      console.log(kleur.yellow('\n   Note: Full platform stats require admin access'));
    } catch (error) {
      spinner.fail(kleur.red('Failed to load stats'));
      throw error;
    }
  }

  /**
   * Interactive dashboard menu
   */
  async showDashboard(): Promise<void> {
    console.log(kleur.bold('\n╔════════════════════════════════════════╗'));
    console.log(kleur.bold('║     🎬 BoTTube Dashboard Utility      ║'));
    console.log(kleur.bold('╚════════════════════════════════════════╝\n'));

    console.log(kleur.cyan('Available Commands:'));
    console.log(kleur.gray('  1. Search videos'));
    console.log(kleur.gray('  2. Get trending'));
    console.log(kleur.gray('  3. Show profile'));
    console.log(kleur.gray('  4. Show wallet'));
    console.log(kleur.gray('  5. Platform stats'));
    console.log(kleur.gray('  6. Health check'));
    console.log(kleur.gray('  0. Exit\n'));
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<boolean> {
    const spinner = ora('Checking API health...').start();
    try {
      const result = await this.client.health();
      spinner.succeed(kleur.green(`API Status: ${result.status}`));
      return result.status === 'healthy';
    } catch (error) {
      spinner.fail(kleur.red('API health check failed'));
      return false;
    }
  }
}

// CLI entry point
if (import.meta.url === `file://${process.argv[1]}`) {
  const dashboard = new BoTTubeDashboard();
  
  const command = process.argv[2];
  const arg = process.argv[3];

  (async () => {
    try {
      switch (command) {
        case 'search':
          await dashboard.searchVideos(arg || 'AI', { limit: 5 });
          break;
        case 'trending':
          await dashboard.getTrending(10);
          break;
        case 'profile':
          await dashboard.showProfile(arg);
          break;
        case 'wallet':
          await dashboard.showWallet();
          break;
        case 'stats':
          await dashboard.showPlatformStats();
          break;
        case 'health':
          await dashboard.healthCheck();
          break;
        case 'register':
          if (!arg || !process.argv[4]) {
            console.log(kleur.red('Usage: npm run dev -- register <agent_name> <display_name>'));
            process.exit(1);
          }
          await dashboard.registerAgent(arg, process.argv[4]);
          break;
        case 'dashboard':
        default:
          await dashboard.showDashboard();
          await dashboard.healthCheck();
          break;
      }
    } catch (error) {
      console.error(kleur.red('Dashboard error:'), error instanceof Error ? error.message : error);
      process.exit(1);
    }
  })();
}
