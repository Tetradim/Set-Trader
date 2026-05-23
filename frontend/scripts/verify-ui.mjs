import { chromium } from 'playwright';
import { WebSocketServer } from 'ws';
import { execFile, spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';

const root = process.cwd();
const frontendPort = 3001;
const backendPort = 8765;
const artifactDir = path.join(root, 'test-artifacts');
const screenshotPath = path.join(artifactDir, 'sentinel-ui.png');

function ticker(symbol, sortOrder, price) {
  return {
    id: symbol,
    symbol,
    base_power: 1000,
    avg_days: 7,
    buy_offset: 1,
    buy_percent: true,
    buy_order_type: 'MARKET',
    sell_offset: 2,
    sell_percent: true,
    sell_order_type: 'MARKET',
    stop_offset: 1.5,
    stop_percent: true,
    stop_order_type: 'MARKET',
    trailing_enabled: sortOrder === 1,
    trailing_percent: 1,
    trailing_percent_mode: true,
    trailing_order_type: 'MARKET',
    wait_day_after_buy: false,
    compound_profits: false,
    max_daily_loss: 500,
    max_consecutive_losses: 3,
    auto_stopped: false,
    auto_stop_reason: '',
    auto_rebracket: false,
    rebracket_threshold: 1,
    rebracket_spread: 1,
    rebracket_cooldown: 60,
    rebracket_lookback: 20,
    rebracket_buffer: 0.1,
    enabled: true,
    strategy: sortOrder === 2 ? 'paper' : 'live',
    broker_id: 'mock',
    broker_ids: ['mock'],
    broker_allocations: { mock: 100 },
    sort_order: sortOrder,
    created_at: new Date().toISOString(),
    partial_fills_enabled: false,
    buy_legs: [],
    sell_legs: [],
    lock_trailing_at_open: false,
    halve_stop_at_open: false,
    opening_bell_enabled: false,
    opening_bell_trail_value: 0,
    opening_bell_trail_is_percent: false,
    market: 'NASDAQ',
    strategy_config: {},
    _price: price,
  };
}

const tickers = [
  ticker('AAPL', 0, 189.12),
  ticker('MSFT', 1, 421.55),
  ticker('TSLA', 2, 174.88),
];

const prices = Object.fromEntries(tickers.map((item) => [item.symbol, item._price]));
const profits = { AAPL: 42.2, MSFT: 18.4, TSLA: -9.8 };

const server = http.createServer((request, response) => {
  response.setHeader('Access-Control-Allow-Origin', '*');
  response.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  response.setHeader('Access-Control-Allow-Headers', 'content-type');

  if (request.method === 'OPTIONS') {
    response.writeHead(204);
    response.end();
    return;
  }

  const url = request.url ?? '';
  response.setHeader('Content-Type', 'application/json');

  if (url.startsWith('/api/fx-rates')) {
    response.end(JSON.stringify({ rates: { USD: 1 } }));
    return;
  }

  if (url.startsWith('/api/settings/currency-display')) {
    response.end(JSON.stringify({ mode: 'usd' }));
    return;
  }

  if (url.startsWith('/api/orders/stats')) {
    response.end(JSON.stringify({ total: 0, filled: 0, pending: 0, rejected: 0 }));
    return;
  }

  if (url.startsWith('/api/orders')) {
    response.end(JSON.stringify({ orders: [] }));
    return;
  }

  if (url.startsWith('/api/logs/client-error')) {
    response.end(JSON.stringify({ ok: true }));
    return;
  }

  response.end(JSON.stringify({ ok: true }));
});

const wss = new WebSocketServer({ noServer: true });
const wsClients = new Set();
server.on('upgrade', (request, socket, head) => {
  if (request.url === '/api/ws') {
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit('connection', ws, request);
    });
    return;
  }
  socket.destroy();
});

wss.on('connection', (ws) => {
  wsClients.add(ws);
  ws.on('close', () => wsClients.delete(ws));

  ws.send(JSON.stringify({
    type: 'INITIAL_STATE',
    tickers,
    prices,
    profits,
    account_balance: 25000,
    allocated: 3000,
    available: 22000,
    running: true,
    paused: false,
    market_open: true,
  }));

  setTimeout(() => {
    ws.send(JSON.stringify({
      type: 'PRICE_UPDATE',
      prices: { AAPL: 190.35, MSFT: 420.92, TSLA: 172.4 },
      profits: { AAPL: 49.1, MSFT: 16.2, TSLA: -12.5 },
    }));
  }, 350);

  setTimeout(() => {
    ws.send(JSON.stringify({
      type: 'PRICE_UPDATE',
      prices: { AAPL: 191.04, MSFT: 423.1, TSLA: 173.2 },
      profits: { AAPL: 53.6, MSFT: 22.7, TSLA: -8.1 },
    }));
  }, 700);
});

await new Promise((resolve) => server.listen(backendPort, '127.0.0.1', resolve));

const viteCommand = process.platform === 'win32'
  ? ['cmd.exe', ['/d', '/s', '/c', `npm.cmd run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`]]
  : ['npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort']];

const vite = spawn(
  viteCommand[0],
  viteCommand[1],
  {
    cwd: root,
    env: {
      ...process.env,
      VITE_BACKEND_URL: `http://127.0.0.1:${backendPort}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  },
);

let viteOutput = '';
vite.stdout.on('data', (chunk) => {
  viteOutput += chunk.toString();
});
vite.stderr.on('data', (chunk) => {
  viteOutput += chunk.toString();
});

async function waitForServer() {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${frontendPort}`);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  throw new Error(`Vite did not start.\n${viteOutput}`);
}

async function run() {
  console.log('verify-ui: preparing artifacts');
  await fs.mkdir(artifactDir, { recursive: true });
  console.log('verify-ui: waiting for Vite');
  await waitForServer();
  console.log('verify-ui: launching browser');

  const browser = await chromium.launch({
    executablePath: process.platform === 'win32'
      ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
      : undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  const consoleErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  console.log('verify-ui: loading app');
  await page.goto(`http://127.0.0.1:${frontendPort}`, { waitUntil: 'domcontentloaded' });
  console.log('verify-ui: waiting for dashboard');
  await page.getByTestId('tab-bar').waitFor({ state: 'visible', timeout: 10_000 });
  await page.getByTestId('ticker-card-AAPL').waitFor({ state: 'visible', timeout: 10_000 });
  await page.waitForTimeout(1000);
  console.log('verify-ui: checking tabs and charts');

  const tabCount = await page.locator('[data-testid^="tab-"]').count();
  if (tabCount < 17) throw new Error(`Expected at least 17 dashboard tabs, found ${tabCount}`);

  const chartCount = await page.locator('.sp-chart-container').count();
  if (chartCount < 3) throw new Error(`Expected chart containers for ticker cards, found ${chartCount}`);

  console.log('verify-ui: switching tabs');
  await page.getByTestId('tab-orders').click();
  await page.getByTestId('tab-watchlist').click();
  await page.getByTestId('ticker-card-AAPL').waitFor({ state: 'visible', timeout: 10_000 });

  console.log('verify-ui: resizing card');
  const card = page.getByTestId('ticker-card-AAPL');
  const before = await card.boundingBox();
  if (!before) throw new Error('AAPL card has no bounding box before resize');
  const handle = card.locator('.sp-resize-se');
  const handleBox = await handle.boundingBox();
  if (!handleBox) throw new Error('AAPL resize handle has no bounding box');

  await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(handleBox.x + handleBox.width / 2 + 70, handleBox.y + handleBox.height / 2 + 40, { steps: 8 });
  await page.mouse.up();

  const after = await card.boundingBox();
  if (!after) throw new Error('AAPL card has no bounding box after resize');
  if (after.width <= before.width || after.height <= before.height) {
    throw new Error(`Resize did not expand the card. Before ${before.width}x${before.height}, after ${after.width}x${after.height}`);
  }

  const nextCard = await page.getByTestId('ticker-card-MSFT').boundingBox();
  if (!nextCard) throw new Error('MSFT card has no bounding box after AAPL resize');
  const sameRow = Math.abs(after.y - nextCard.y) < 20;
  const overlapsNextCard = sameRow && after.x + after.width > nextCard.x;
  if (overlapsNextCard) {
    throw new Error(`Resized AAPL overlaps MSFT. AAPL right=${after.x + after.width}, MSFT left=${nextCard.x}`);
  }

  console.log('verify-ui: taking screenshot');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log('verify-ui: closing browser');
  await browser.close();

  const relevantErrors = consoleErrors.filter((message) => (
    !message.includes('/api/logs/client-error')
    && !message.includes('WebSocket connection')
  ));
  if (relevantErrors.length > 0) {
    throw new Error(`Console errors:\n${relevantErrors.join('\n')}`);
  }

  console.log(`UI verification passed. Screenshot: ${screenshotPath}`);
}

try {
  await run();
} finally {
  for (const client of wsClients) {
    client.terminate();
  }
  wss.close();
  await new Promise((resolve) => server.close(resolve));
  await stopProcessTree(vite.pid);
}

function stopProcessTree(pid) {
  if (!pid) return Promise.resolve();

  if (process.platform !== 'win32') {
    vite.kill();
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    execFile('taskkill.exe', ['/PID', String(pid), '/T', '/F'], () => resolve());
  });
}
