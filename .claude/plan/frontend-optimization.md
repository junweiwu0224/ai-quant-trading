# 前端优化实施计划

## 概述
全面优化量化交易系统前端，涵盖结构优化(A)、UX增强(B)、性能+可访问性(C)三个方面。

## Phase 1: 结构优化（代码拆分 + 质量修复）

### 1.1 拆分 app.js 为模块
当前 app.js 1815 行，拆分为：
- `app.js` - 核心入口（init、tab路由、工具函数）~200行
- `backtest.js` - 回测相关（bindBacktest、showResults、loadCharts、compare）~300行
- `overview.js` - 总览相关（loadOverview、renderEquity、renderMarket）~250行
- `portfolio.js` - 持仓相关（loadPortfolio、renderCharts）~150行
- `alpha.js` - AI Alpha（loadAlpha、renderCharts）~150行
- `optimization.js` - 优化+敏感性+蒙特卡洛 ~200行
- `charts.js` - 已有，ChartFactory 统一管理

### 1.2 Chart 实例管理
- ChartFactory 统一 destroy 旧实例再创建新实例
- 添加 `ChartFactory.destroy(key)` 方法

### 1.3 WebSocket 去重
- backtest WS 和 optimization WS 逻辑重复，提取为 `WSManager.connect(url, handlers)`

### 1.4 CSS 清理
- 移除 `!important` 滥用
- 统一使用 CSS 变量

## Phase 2: UX 增强

### 2.1 骨架屏
- 为 overview、portfolio、backtest results 添加 skeleton loading 状态

### 2.2 表格排序
- 为数据表格添加点击表头排序功能

### 2.3 图表交互增强
- Tooltip 优化：显示更多上下文信息
- 添加数据点点击事件（跳转详情）

### 2.4 移动端响应式修复
- 修复 sidebar 和 bottom-nav 重复问题
- 优化小屏幕表格横向滚动

## Phase 3: 性能 + 可访问性

### 3.1 CDN 异步加载
- Chart.js、Lightweight Charts 改为 defer/async

### 3.2 ARIA 标签补充
- 表格添加 aria-label
- 图表添加 aria-describedby

### 3.3 键盘导航
- 添加 :focus-visible 样式
- 确保所有交互元素可 Tab 访问

### 3.4 Skip-to-content
- 添加跳过导航链接

## 执行顺序
1. 先拆分 JS（不改功能，纯重构）
2. 修复 CSS 质量问题
3. 添加骨架屏和表格排序
4. 添加可访问性改进
5. 性能优化（CDN 异步）
6. 测试验证

## 风险评估
- 纯前端改动，不影响后端
- 模块拆分需要确保加载顺序正确
- 需要保持现有功能不变
