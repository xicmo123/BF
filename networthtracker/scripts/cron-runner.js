const cron = require('node-cron');

async function runSequence() {
  const endpoints = [
    'http://localhost:8000/api/test-fetch-prices',
    'http://localhost:8000/api/cron/auto-deduct',
    'http://localhost:8000/api/cron/snapshot',
  ];

  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint);
      const data = await response.json();
      console.log(`[cron] ${endpoint} ->`, response.status, data.message || 'ok');
    } catch (error) {
      console.error(`[cron] Failed to call ${endpoint}:`, error);
    }
  }
}

cron.schedule('0 0 * * *', () => {
  console.log('[cron] Running daily scheduled tasks...');
  runSequence();
});

console.log('[cron] Scheduler started.');
