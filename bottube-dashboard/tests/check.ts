/**
 * BoTTube Dashboard - Basic Check Script
 * Verifies setup and basic functionality
 */

import { BoTTubeDashboard } from '../src/index.js';

interface TestResult {
  name: string;
  passed: boolean;
  message?: string;
}

const results: TestResult[] = [];

async function runTest(name: string, fn: () => Promise<boolean>, message?: string): Promise<void> {
  try {
    const passed = await fn();
    results.push({ name, passed, message: passed ? undefined : message });
  } catch (error) {
    results.push({ name, passed: false, message: message || String(error) });
  }
}

async function runChecks(): Promise<void> {
  console.log('🔍 Running BoTTube Dashboard Checks...\n');

  // Check 1: Environment variables
  const hasApiKey = !!process.env.BOTTUBE_API_KEY && process.env.BOTTUBE_API_KEY !== 'your_api_key_here';
  if (!hasApiKey) {
    console.log('   ⊘ Skipping environment check - no API key set\n');
  } else {
    results.push({ name: 'Environment setup', passed: true });
  }

  // Check 2: Dashboard instantiation
  await runTest(
    'Dashboard instantiation',
    async () => {
      const dashboard = new BoTTubeDashboard();
      return dashboard !== null;
    },
    'Failed to create dashboard instance'
  );

  // Check 3: Health check (requires API)
  await runTest(
    'API health check',
    async () => {
      if (!process.env.BOTTUBE_API_KEY || process.env.BOTTUBE_API_KEY === 'your_api_key_here') {
        console.log('   ⊘ Skipping - no API key');
        return true; // Skip if no key
      }
      const dashboard = new BoTTubeDashboard();
      return await dashboard.healthCheck();
    },
    'API health check failed - check your API key'
  );

  // Check 4: Search functionality (public API, no auth required)
  await runTest(
    'Search functionality',
    async () => {
      const dashboard = new BoTTubeDashboard();
      try {
        await dashboard.searchVideos('test', { limit: 1 });
        return true;
      } catch (e) {
        return false;
      }
    },
    'Search failed - API may be unavailable'
  );

  // Check 5: Trending functionality (public API)
  await runTest(
    'Trending functionality',
    async () => {
      const dashboard = new BoTTubeDashboard();
      try {
        await dashboard.getTrending(5);
        return true;
      } catch (e) {
        return false;
      }
    },
    'Trending failed - API may be unavailable'
  );

  // Check 6: Profile lookup (public API)
  await runTest(
    'Profile lookup',
    async () => {
      const dashboard = new BoTTubeDashboard();
      try {
        await dashboard.showProfile('sophia-elya');
        return true;
      } catch (e) {
        return false;
      }
    },
    'Profile lookup failed'
  );

  console.log('═'.repeat(50));
  console.log('Check Results:');
  console.log('═'.repeat(50));

  let passed = 0;
  let failed = 0;
  let skipped = 0;

  results.forEach((result) => {
    if (result.message?.includes('Skipping')) {
      const status = '⊘';
      console.log(`${status} ${result.name}`);
      console.log(`   └─ ${result.message}`);
      skipped++;
    } else {
      const status = result.passed ? '✅' : '❌';
      console.log(`${status} ${result.name}`);
      if (!result.passed && result.message) {
        console.log(`   └─ ${result.message}`);
      }
      if (result.passed) passed++;
      else failed++;
    }
  });

  console.log('═'.repeat(50));
  console.log(`Total: ${passed} passed, ${failed} failed, ${skipped} skipped`);
  console.log('═'.repeat(50));

  if (failed > 0) {
    console.log('\n💡 Tips:');
    console.log('   - Copy .env.example to .env and add your API key');
    console.log('   - Get an API key from https://bottube.ai or register via SDK');
    console.log('   - Run: npm run dev -- health  (to test API connection)\n');
    process.exit(1);
  } else {
    console.log('\n✅ All checks passed!\n');
    process.exit(0);
  }
}

runChecks().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
