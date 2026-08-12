const { chromium } = require('/Users/mac/.workbuddy/binaries/node/workspace/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 720, height: 900 }, deviceScaleFactor: 4 });
  await page.goto('file:///Users/mac/WorkBuddy/Claw/b_card.html', { waitUntil: 'networkidle0' });
  const el = await page.$('.card');
  await el.screenshot({ path: '/Users/mac/WorkBuddy/Claw/b_card.png' });
  await browser.close();
  console.log('saved b_card.png');
})();
