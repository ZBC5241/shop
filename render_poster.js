const { chromium } = require('/Users/mac/.workbuddy/binaries/node/workspace/node_modules/playwright');
const args = process.argv.slice(2);
const htmlPath = args[0];
const outPath = args[1] || '/Users/mac/WorkBuddy/Claw/poster_today.png';
(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--no-sandbox']
  });
  const page = await browser.newPage({ viewport: { width: 1450, height: 720 }, deviceScaleFactor: 2 });
  await page.goto('file://' + htmlPath, { waitUntil: 'networkidle0' });
  const el = await page.$('.phone');
  await el.screenshot({ path: outPath });
  await browser.close();
  console.log('saved ' + outPath);
})();
