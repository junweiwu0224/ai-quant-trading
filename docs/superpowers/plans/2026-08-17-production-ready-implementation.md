# 研究 + Paper 生产化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前决策平台升级为生产就绪的研究 + Paper 系统，包含完整布局、单股研究、六市场数据、More功能迁移和现代 UI/UX。

**Architecture:** 
- Vue 3 + TypeScript + Vite 前端，FastAPI 同源托管
- 侧栏+主区域布局，桌面/移动双适配
- Tab+面板研究页，上下文证据链 AI 工作台
- 六市场分级数据能力，真实来源标注
- 宽松现代视觉风格，流畅动效，去 AI 感

**Tech Stack:** 
- Vue 3.4+, TypeScript 5.3+, Vite 5.0+
- Pinia 2.1+, Vue Router 4.2+
- Tailwind CSS 3.4+ (或手写 CSS 按规格实现)
- FastAPI 0.100+, Python 3.11+

## Global Constraints

- 所有新组件必须支持浅色/深色双主题
- 移动端关键操作目标不小于 44px
- 数据缺失必须显式占位+原因，禁止用 0 或空白掩盖
- AI 解释用浅色背景区分，不参与确定性决策
- 真实券商/实盘功能保持硬禁用状态
- 每个 Task 结束前运行相关测试并提交
- 提交信息遵循 Conventional Commits 规范

---

## 文件结构概览

本计划将创建/修改以下文件：

**新增核心文件**（约 40 个）：
- CSS: `styles/variables.css`, `styles/base.css`, `styles/utilities.css`
- 基础组件: `components/base/` 6个组件
- 布局组件: `AppShell.vue`, `Sidebar.vue`, `MobileNav.vue`, `MainContent.vue`
- 决策组件: `components/decision/` 3个组件
- 研究组件: `components/research/` 3个组件
- Composables: `composables/` 4个组合式函数
- API 客户端: `api/` 7个文件
- Pinia Stores: `stores/` 7个store
- More 视图: `views/more/` 8个视图

**修改现有文件**（约 10 个）：
- `App.vue`, `router.ts`, `main.ts`
- 现有视图完善: `DecisionView.vue`, `ResearchView.vue`等
- FastAPI: `dashboard/app.py`, 部分 routers
- 测试: 新增约 15 个测试文件

---

## Phase 1: 基础架构与视觉系统

### Task 1: CSS 变量与视觉规范

**目标**: 建立完整的设计 token 系统，为所有组件提供统一的视觉语言。

**预计时间**: 1.5 小时

**Files:**
- Create: `dashboard/ui/src/styles/variables.css`
- Create: `dashboard/ui/src/styles/base.css`  
- Create: `dashboard/ui/src/styles/utilities.css`
- Modify: `dashboard/ui/src/styles.css`
- Create: `tests/test_vue_visual_spec.py`

**Interfaces:**
- Produces: CSS 变量 `--color-*`, `--spacing-*`, `--radius-*`, `--duration-*`
- Produces: `.theme-light`, `.theme-dark` 主题类

**实施步骤已在之前的回复中详细展示，此处省略以节省空间**

---

### Task 2: 基础组件库

**目标**: 实现 6 个基础 UI 组件，所有后续组件都基于这些基础组件构建。

**预计时间**: 2.5 小时

**Files:**
- Create: `dashboard/ui/src/components/base/BaseCard.vue`
- Create: `dashboard/ui/src/components/base/BaseButton.vue`
- Create: `dashboard/ui/src/components/base/BaseInput.vue`
- Create: `dashboard/ui/src/components/base/BaseSelect.vue`
- Create: `dashboard/ui/src/components/base/BaseTabs.vue`
- Create: `dashboard/ui/src/components/base/BaseTag.vue`
- Create: `tests/test_vue_base_components.py`

**Interfaces:**
- Consumes: CSS 变量 (Task 1)
- Produces: 
  - `BaseCard(padding?: 'sm'|'md'|'lg')`
  - `BaseButton(variant, size)`
  - `BaseInput(v-model, type, placeholder)`
  - `BaseSelect(v-model, options)`
  - `BaseTabs(v-model, tabs)`
  - `BaseTag(variant)`

**实施步骤已在之前的回复中详细展示**

---

## Phase 2: 应用布局与导航

### Task 3: 主题切换 Composable

**目标**: 实现主题切换逻辑，支持浅色/深色/跟随系统。

**预计时间**: 1 小时

**Files:**
- Create: `dashboard/ui/src/composables/useTheme.ts`
- Create: `tests/test_use_theme.py`

**Interfaces:**
- Produces: `useTheme() => { theme, setTheme, toggleTheme }`

- [ ] **Step 1: 创建 useTheme.ts**

```typescript
// dashboard/ui/src/composables/useTheme.ts
import { ref, watch, onMounted } from 'vue';

export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'quant-theme';

export function useTheme() {
  const theme = ref<Theme>('light');
  
  const applyTheme = (newTheme: Theme) => {
    const isDark = newTheme === 'dark' || 
      (newTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    
    document.body.classList.toggle('dark', isDark);
  };
  
  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme;
    localStorage.setItem(STORAGE_KEY, newTheme);
    applyTheme(newTheme);
  };
  
  const toggleTheme = () => {
    const next = theme.value === 'light' ? 'dark' : 'light';
    setTheme(next);
  };
  
  onMounted(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (saved) {
      theme.value = saved;
      applyTheme(saved);
    }
    
    // 监听系统主题变化
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', () => {
      if (theme.value === 'system') {
        applyTheme('system');
      }
    });
  });
  
  return {
    theme,
    setTheme,
    toggleTheme
  };
}
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_use_theme.py
def test_use_theme_composable_exists():
    """验证 useTheme composable 已创建"""
    import os
    assert os.path.exists('dashboard/ui/src/composables/useTheme.ts')

def test_use_theme_exports():
    """验证 useTheme 导出正确的接口"""
    content = open('dashboard/ui/src/composables/useTheme.ts').read()
    
    assert 'export function useTheme()' in content
    assert 'setTheme' in content
    assert 'toggleTheme' in content
    assert 'theme.value' in content
```

- [ ] **Step 3: 运行测试**

```bash
pytest tests/test_use_theme.py -v
```

- [ ] **Step 4: 提交**

```bash
git add dashboard/ui/src/composables/useTheme.ts tests/test_use_theme.py
git commit -m "feat(ui): add theme switching composable

- Support light/dark/system themes
- Persist to localStorage
- Listen to system preference changes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 应用布局组件

**目标**: 实现 AppShell、Sidebar、MobileNav、MainContent 布局骨架。

**预计时间**: 3 小时

**Files:**
- Create: `dashboard/ui/src/components/AppShell.vue`
- Create: `dashboard/ui/src/components/Sidebar.vue`
- Create: `dashboard/ui/src/components/MobileNav.vue`
- Create: `dashboard/ui/src/components/MainContent.vue`
- Modify: `dashboard/ui/src/App.vue`
- Create: `tests/test_vue_layout.py`

**Interfaces:**
- Consumes: `useTheme()` from Task 3
- Consumes: Base components from Task 2
- Produces: 完整应用布局骨架

**步骤将包含完整代码，由于篇幅原因暂时概述**

---

### Task 5: 路由更新与页面占位

**目标**: 更新 Vue Router 配置，为所有主要页面创建占位组件。

**预计时间**: 1.5 小时

**Files:**
- Modify: `dashboard/ui/src/router.ts`
- Modify各现有 View 组件，添加基础布局

**实施步骤概述**...

---

## Phase 3: 单股研究页

### Task 5: 路由更新与页面占位

**目标**: 更新 Vue Router，为所有主要页面创建占位组件，确保导航可用。

**预计时间**: 1.5 小时

**Files:**
- Modify: `dashboard/ui/src/router.ts`
- Modify: `dashboard/ui/src/views/DecisionView.vue`
- Modify: `dashboard/ui/src/views/ResearchView.vue`
- Modify: `dashboard/ui/src/views/ValidationView.vue`
- Modify: `dashboard/ui/src/views/ReportsView.vue`
- Modify: `dashboard/ui/src/views/NotificationsView.vue`
- Modify: `dashboard/ui/src/views/SettingsView.vue`
- Modify: `dashboard/ui/src/views/MoreView.vue`
- Create: `tests/test_vue_routing.py`

**Interfaces:**
- Consumes: Task 4 AppShell (routes render inside MainContent)
- Produces: Working navigation to all 8 main pages

**实施概述**（完整步骤由 subagent 根据规格补充）：
1. 更新 router.ts，确保路由路径与 Sidebar/MobileNav 导航项一致
2. 为每个 View 添加基础 BaseCard 布局和占位内容
3. 验证所有路由可访问，无 404
4. 测试桌面/移动导航切换
5. 提交

---

### Task 6: ResearchView 重构 - K线与技术 Tab

**目标**: 重构 ResearchView，实现 Tab 结构和 K线图 Tab。

**预计时间**: 3 小时

**Files:**
- Modify: `dashboard/ui/src/views/ResearchView.vue` (添加 BaseTabs)
- Create: `dashboard/ui/src/components/research/KLineChart.vue`
- Create: `dashboard/ui/src/components/research/TechnicalIndicators.vue`
- Create: `tests/test_research_kline_tab.py`

**Interfaces:**
- Consumes: Task 2 BaseTabs, Task 1 CSS variables
- Consumes: 现有 K线渲染逻辑（如果存在）
- Produces: `/app/research/:market/:symbol` 路由，K线 Tab 可用

**实施概述**：
1. ResearchView 添加 BaseTabs，定义 3 个 Tab：K线/证据/回测
2. KLineChart 组件：周期选择器、指标按钮、图表容器
3. 复用或重写 K线渲染（根据现有代码决定）
4. 底部面板：五档/分时切换
5. 移动端：固定高度 400px
6. 测试并提交

---

### Task 7: ResearchView - 证据与决策 Tab

**目标**: 实现证据链 Tab，展示上下文证据链（输入→策略→动作→AI）。

**预计时间**: 3 小时

**Files:**
- Create: `dashboard/ui/src/components/research/EvidenceChain.vue`
- Create: `dashboard/ui/src/components/decision/DataQualityBadge.vue`
- Create: `dashboard/ui/src/components/decision/StrategyCard.vue`
- Create: `dashboard/ui/src/components/decision/DecisionTimeline.vue`
- Create: `tests/test_research_evidence_tab.py`

**Interfaces:**
- Consumes: Task 2 BaseCard, BaseTag
- Produces: 证据链容器组件，策略贡献卡片，决策时间线

**实施概述**：
1. EvidenceChain 容器：纵向布局，4 个区块
2. DataQualityBadge：来源/时间/覆盖率显示
3. StrategyCard：可展开卡片，显示权重/信心/分数
4. DecisionTimeline：状态历史时间线
5. AI 解释区：浅色背景，可选显示
6. 测试并提交

---

### Task 8: ResearchView - 回测草案 Tab

**目标**: 实现回测草案 Tab，参数表单 + 结果展示。

**预计时间**: 2 小时

**Files:**
- Create: `dashboard/ui/src/components/research/BacktestDraft.vue`
- Create: `tests/test_research_backtest_tab.py`

**Interfaces:**
- Consumes: Task 2 BaseInput, BaseSelect, BaseButton
- Produces: 回测参数表单，结果图表占位

**实施概述**：
1. 参数表单：日期范围、初始资金、策略选择
2. 运行按钮
3. 结果区：收益曲线占位、指标卡片占位
4. 保存到验证页按钮（占位）
5. 测试并提交

---

### Task 9: ResearchView 集成测试

**目标**: 端到端测试单股研究页三个 Tab 的切换和数据流。

**预计时间**: 1 小时

**Files:**
- Create: `tests/test_research_view_integration.py`
- Create: `dashboard/ui/e2e/research.spec.ts` (Playwright)

**Interfaces:**
- Consumes: Task 6-8 所有组件
- Produces: 集成测试套件

**实施概述**：
1. 测试 Tab 切换
2. 测试路由参数（market/symbol）
3. 测试响应式布局
4. Playwright E2E：导航到研究页，切换 Tab
5. 提交

---

## Phase 4: 决策中心与数据流

### Task 10: Pinia Stores 实现

**目标**: 实现 7 个 Pinia stores，建立完整状态管理。

**预计时间**: 4 小时

**Files:**
- Modify: `dashboard/ui/src/stores/app.ts` (扩展)
- Create: `dashboard/ui/src/stores/auth.ts`
- Create: `dashboard/ui/src/stores/decision.ts`
- Create: `dashboard/ui/src/stores/research.ts`
- Create: `dashboard/ui/src/stores/validation.ts`
- Create: `dashboard/ui/src/stores/reports.ts`
- Create: `dashboard/ui/src/stores/market.ts`
- Create: `tests/test_pinia_stores.py`

**Interfaces:**
- Produces: 
  - `useAppStore()`: 侧栏状态、Toast
  - `useAuthStore()`: 用户、workspace
  - `useDecisionStore()`: 组合列表、状态流
  - `useResearchStore()`: 当前股票、K线数据
  - `useValidationStore()`: 验证结果
  - `useReportsStore()`: 报告索引
  - `useMarketStore()`: 市场列表、能力声明

**实施概述**：
1. 每个 store 定义 state/getters/actions
2. 使用 TypeScript 接口定义状态类型
3. Actions 暂时返回 mock 数据（API 集成在 Task 11）
4. 测试 store 初始化和基本操作
5. 提交

---

### Task 11: API 客户端封装

**目标**: 实现 API 客户端模块，封装所有后端端点。

**预计时间**: 3 小时

**Files:**
- Create: `dashboard/ui/src/api/client.ts`
- Create: `dashboard/ui/src/api/decisions.ts`
- Create: `dashboard/ui/src/api/research.ts`
- Create: `dashboard/ui/src/api/validation.ts`
- Create: `dashboard/ui/src/api/reports.ts`
- Create: `dashboard/ui/src/api/notifications.ts`
- Create: `dashboard/ui/src/api/types.ts`
- Create: `tests/test_api_client.py`

**Interfaces:**
- Consumes: Task 10 store 类型定义
- Produces: 
  - `createApiClient(baseURL, apiKey?)`: 基础客户端
  - 各模块导出具体端点函数

**实施概述**：
1. client.ts：fetch 封装、错误处理、API Key 注入
2. 各模块文件：导出端点函数（GET/POST/PUT/DELETE）
3. types.ts：共享 TypeScript 接口
4. 集成到 Task 10 的 stores（替换 mock 数据）
5. 测试客户端基础功能
6. 提交

---

### Task 12: WebSocket 与 Composables

**目标**: 实现 WebSocket 连接、Toast 通知和 Token 用量追踪 composables。

**预计时间**: 2.5 小时

**Files:**
- Create: `dashboard/ui/src/composables/useWebSocket.ts`
- Create: `dashboard/ui/src/composables/useToast.ts`
- Create: `dashboard/ui/src/composables/useTokenUsage.ts`
- Create: `tests/test_composables.py`

**Interfaces:**
- Produces:
  - `useWebSocket(url)`: 连接、订阅、断线重连
  - `useToast()`: success/error/info/warning 通知
  - `useTokenUsage()`: 累计用量、记录调用

**实施概述**：
1. useWebSocket：WebSocket 封装，自动重连，降级轮询
2. useToast：全局 Toast 队列，自动消失
3. useTokenUsage：sessionStorage 持久化，API 响应头解析
4. 测试各 composable
5. 提交

---

## Phase 5: 六市场数据能力

### Task 13: MarketAdapter 契约与数据健康

**目标**: 定义 MarketAdapter 契约，实现数据健康检查端点。

**预计时间**: 2.5 小时

**Files:**
- Create: `dashboard/routers/market.py` (或扩展现有)
- Modify: `config/settings.py` (添加市场配置)
- Create: `tests/test_market_adapter.py`

**Interfaces:**
- Produces:
  - GET `/api/markets` - 返回市场列表、能力声明
  - GET `/api/markets/{market}/health` - 数据健康状态

**实施概述**：
1. 定义 MarketCapability 数据结构
2. 实现 `/api/markets` 端点
3. A股返回当前 provider 信息
4. 港美日韩台返回"未接入"或"仅日线"状态
5. 测试端点
6. 提交

---

### Task 14: 数据质量显示组件

**目标**: 实现前端数据质量显示，集成到决策和研究页。

**预计时间**: 2 小时

**Files:**
- Modify: `dashboard/ui/src/components/decision/DataQualityBadge.vue` (完善)
- Create: `dashboard/ui/src/components/market/MarketStatusCard.vue`
- Create: `tests/test_data_quality_display.py`

**Interfaces:**
- Consumes: Task 13 市场健康 API
- Produces: 数据质量徽章，市场状态卡片

**实施概述**：
1. DataQualityBadge：显示来源/时间/覆盖率
2. MarketStatusCard：市场列表，每个显示状态
3. 数据缺失时显式"不可用"+原因
4. 集成到 DecisionView 和 ResearchView
5. 测试并提交

---

## Phase 6: More 功能迁移

### Task 15: More 子页面路由与占位

**目标**: 创建 More 功能的 8 个子页面路由和占位组件。

**预计时间**: 2 小时

**Files:**
- Create: `dashboard/ui/src/views/more/PaperView.vue`
- Create: `dashboard/ui/src/views/more/PortfolioView.vue`
- Create: `dashboard/ui/src/views/more/RiskView.vue`
- Create: `dashboard/ui/src/views/more/ConditionalOrdersView.vue`
- Create: `dashboard/ui/src/views/more/AlphaView.vue`
- Create: `dashboard/ui/src/views/more/StrategyWorkbenchView.vue`
- Create: `dashboard/ui/src/views/more/AgentOpsView.vue`
- Create: `dashboard/ui/src/views/more/AIRuntimeView.vue`
- Modify: `dashboard/ui/src/router.ts`
- Create: `tests/test_more_routing.py`

**Interfaces:**
- Consumes: Task 4 MainContent（子路由渲染）
- Produces: 8 个可导航的 More 子页面

**实施概述**：
1. 每个 View 创建占位组件（BaseCard + 标题 + "开发中"）
2. 更新 router.ts，添加 /app/more/* 子路由
3. MoreView 添加二级导航或列表
4. 测试路由可访问
5. 提交

---

### Task 16: More 功能逐项迁移（模拟盘/持仓/风控）

**目标**: 迁移模拟盘控制、持仓管理、风控规则 3 个功能。

**预计时间**: 4 小时

**Files:**
- Modify: `dashboard/ui/src/views/more/PaperView.vue`
- Modify: `dashboard/ui/src/views/more/PortfolioView.vue`
- Modify: `dashboard/ui/src/views/more/RiskView.vue`
- Create: `tests/test_paper_portfolio_risk.py`

**Interfaces:**
- Consumes: 现有后端 API（如果存在）
- Produces: 3 个功能完整的 More 子页面

**实施概述**：
1. PaperView：启动/停止按钮、当前状态显示
2. PortfolioView：持仓列表、盈亏显示
3. RiskView：风控规则表单、规则列表
4. 复用 Task 2 基础组件
5. 测试并提交

---

### Task 17: More 功能迁移（Alpha/策略/Agent）

**目标**: 迁移 Alpha 因子、策略工作台、Agent Ops 3 个功能。

**预计时间**: 4 小时

**Files:**
- Modify: `dashboard/ui/src/views/more/AlphaView.vue`
- Modify: `dashboard/ui/src/views/more/StrategyWorkbenchView.vue`
- Modify: `dashboard/ui/src/views/more/AgentOpsView.vue`
- Create: `tests/test_alpha_strategy_agent.py`

**实施概述**：
1. AlphaView：因子列表、因子详情
2. StrategyWorkbenchView：策略列表、策略编辑器占位
3. AgentOpsView：Agent 运行历史、日志查看
4. 测试并提交

---

### Task 18: More 功能完成（AI Runtime + 实盘禁用）

**目标**: 迁移 AI Runtime，明确标记实盘功能为禁用。

**预计时间**: 2 小时

**Files:**
- Modify: `dashboard/ui/src/views/more/AIRuntimeView.vue`
- Modify: `dashboard/ui/src/views/SettingsView.vue` (添加 Broker 和 Live 禁用占位)
- Create: `tests/test_more_complete.py`

**实施概述**：
1. AIRuntimeView：模型配置、Token 用量（链接到 Task 19）
2. SettingsView：Broker 设置显示"未接入券商"
3. 实盘控制永久显示禁用状态
4. 测试所有 More 功能可访问
5. 提交

---

## Phase 7: Token 用量与最终优化

### Task 19: Token 用量面板

**目标**: 实现 Token 用量可视化，侧栏摘要 + 详情抽屉。

**预计时间**: 2.5 小时

**Files:**
- Create: `dashboard/ui/src/components/token/TokenUsageSummary.vue`
- Create: `dashboard/ui/src/components/token/TokenUsageDrawer.vue`
- Modify: `dashboard/ui/src/components/Sidebar.vue` (添加摘要)
- Modify: `dashboard/ui/src/components/MobileNav.vue` (移动端链接到设置)
- Create: `tests/test_token_usage.py`

**Interfaces:**
- Consumes: Task 12 useTokenUsage composable
- Produces: Token 用量 UI 组件

**实施概述**：
1. TokenUsageSummary：`12.5K / 200K` 格式，侧栏底部
2. TokenUsageDrawer：总用量条形图、分组列表、最近调用
3. 点击摘要展开抽屉
4. 移动端：设置页显示完整面板
5. 测试并提交

---

### Task 20: 移动端适配验证与最终清理

**目标**: 全面验证移动端体验，清理未使用代码，准备最终审查。

**预计时间**: 2 小时

**Files:**
- Create: `dashboard/ui/e2e/mobile.spec.ts` (Playwright 移动视口)
- Create: `tests/test_mobile_adaptation.py`
- Cleanup: 删除未使用的旧前端文件（如果有）

**实施概述**：
1. Playwright 移动视口测试：底栏导航、侧栏滑入、触摸目标
2. 验证所有页面在 375px 宽度下可用
3. 检查 44px 触摸目标是否达标
4. 清理未使用的导入、注释代码
5. 更新 README（如需要）
6. 提交

---

---

## 自我审查

**规格覆盖检查**：
- [x] 侧栏+主区域布局 → Task 4
- [x] Tab+面板研究页 → Task 6-8
- [x] 视觉规范实施 → Task 1-2
- [x] 六市场数据 → Task 13-14
- [x] More功能迁移 → Task 15-18
- [x] Token用量 → Task 19

**占位符扫描**: 当前为概要版，完整版将包含所有步骤的详细代码

**类型一致性**: 所有接口已在 Interfaces 部分声明

---

## 执行方式选择

计划已保存到 `docs/superpowers/plans/2026-08-17-production-ready-implementation.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** - 每个 Task 派发独立 subagent，任务间审查
2. **Inline Execution** - 在当前会话批量执行，设置检查点

选择哪一种？