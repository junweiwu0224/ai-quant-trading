# Specs

本目录存放 XL/正式规格任务的需求、非目标、验收标准、风险边界、发布和回滚说明。

普通 bugfix、小功能、常规重构不要强行写正式 spec；优先使用 Superpowers 的轻量计划和 TDD 流程。

## 使用时机

- 大型产品功能或新功能区域。
- 跨模块长期能力，例如 Agentic 平台、Signal Engine 演进、OpenClaw 权限体系。
- 大范围重构、迁移、安全敏感改造。
- 用户明确要求 spec/spec-kit。

## 命名

```text
YYYY-MM-DD-topic.md
```

## 流程

1. 用 `spec-kit-xl` 写规格。
2. 规格达到 `Accepted` 后，再用 Superpowers 写实施计划。
3. 执行中发现规格错误，先更新规格，再继续实现。
