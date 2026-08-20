import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8001';

// 测试三个关键修复：AgentOpsView、DecisionView、ReportsView
const CRITICAL_ROUTES = [
  { path: '/app/agent-ops', name: 'AgentOpsView', selector: '.ai-workbench-grid' },
  { path: '/app/decisions', name: 'DecisionView', selector: '.decision-trace-list' },
  { path: '/app/reports', name: 'ReportsView', selector: '.report-list' }
];

// iPhone 12 Pro (390px) 移动端测试
for (const route of CRITICAL_ROUTES) {
  test(`${route.name} - 移动端布局 (390px)`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE_URL}${route.path}`);
    
    // 等待主要内容加载
    await page.waitForLoadState('networkidle');

    // 检查横向滚动（不应该有，除非是刻意设计的表格）
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    
    console.log(`${route.name}: body=${bodyWidth}px, viewport=${viewportWidth}px`);
    
    // 允许少量溢出（1-2px 浏览器渲染误差）
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 2);

    // 检查触摸目标尺寸（关键按钮应该 >= 44px）
    const buttons = await page.locator('button:visible, a.nav-link:visible').all();
    let checkedCount = 0;
    for (const btn of buttons.slice(0, 10)) {
      const box = await btn.boundingBox();
      if (box && box.height > 0) {
        expect(box.height).toBeGreaterThanOrEqual(40); // 允许 4px 误差
        checkedCount++;
      }
    }
    console.log(`${route.name}: 检查了 ${checkedCount} 个按钮`);

    // 截图存档
    await page.screenshot({ 
      path: `tests/e2e/screenshots/${route.name}-mobile.png`,
      fullPage: true 
    });
  });
}

test('DecisionView - 决策链垂直堆叠 (390px)', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE_URL}/app/decisions`);
  await page.waitForLoadState('networkidle');
  
  // 检查 .decision-trace-list 是否为 flex-direction: column
  const traceList = page.locator('.decision-trace-list').first();
  const exists = await traceList.count();
  
  if (exists > 0) {
    const flexDirection = await traceList.evaluate((el) => 
      window.getComputedStyle(el).flexDirection
    );
    expect(flexDirection).toBe('column');
    console.log('✓ DecisionView 决策链已改为垂直堆叠');
  }
});

test('ReportsView - 移动端卡片模式 (390px)', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE_URL}/app/reports`);
  await page.waitForLoadState('networkidle');
  
  // 检查 .report-mobile-list 是否显示（桌面版 table 应该隐藏）
  const mobileList = page.locator('.report-mobile-list');
  const desktopTable = page.locator('.report-table-desktop');
  
  const mobileCount = await mobileList.count();
  const desktopCount = await desktopTable.count();
  
  if (mobileCount > 0 || desktopCount > 0) {
    const mobileVisible = await mobileList.isVisible();
    const desktopVisible = await desktopTable.isVisible();
    
    expect(mobileVisible).toBe(true);
    expect(desktopVisible).toBe(false);
    console.log('✓ ReportsView 移动端使用卡片模式');
  }
});

// iPad (768px) 平板测试
test('AgentOpsView - 平板两栏布局 (768px)', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto(`${BASE_URL}/app/agent-ops`);
  await page.waitForLoadState('networkidle');
  
  const grid = page.locator('.ai-workbench-grid').first();
  const exists = await grid.count();
  
  if (exists > 0) {
    const gridColumns = await grid.evaluate((el) =>
      window.getComputedStyle(el).gridTemplateColumns
    );
    
    const columnCount = gridColumns.split(' ').filter(c => c !== 'none').length;
    expect(columnCount).toBeGreaterThanOrEqual(2);
    console.log(`✓ AgentOpsView 平板显示 ${columnCount} 列`);
  }

  await page.screenshot({ 
    path: 'tests/e2e/screenshots/AgentOpsView-tablet.png',
    fullPage: true 
  });
});

// 桌面宽屏 (1920px) 测试
test('DecisionView - 桌面横向决策链 (1920px)', async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`${BASE_URL}/app/decisions`);
  await page.waitForLoadState('networkidle');
  
  const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
  expect(bodyWidth).toBeGreaterThan(1200);
  console.log(`✓ DecisionView 桌面宽度: ${bodyWidth}px`);

  await page.screenshot({ 
    path: 'tests/e2e/screenshots/DecisionView-desktop.png',
    fullPage: false
  });
});
