const { chromium } = require('/Users/mac/.workbuddy/binaries/node/workspace/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--no-sandbox', '--disable-gpu']
  });
  const page = await browser.newPage({ viewport: { width: 720, height: 1600 }, deviceScaleFactor: 4 });
  await page.goto('file:///Users/mac/WorkBuddy/Claw/poster_v3.html', { waitUntil: 'networkidle' });
  await page.screenshot({ path: '/Users/mac/WorkBuddy/Claw/poster_v3.png', type: 'png', fullPage: true });
  await browser.close();
  console.log('saved poster_v3.png');
})().catch(e => { console.error(e); process.exit(1); });
