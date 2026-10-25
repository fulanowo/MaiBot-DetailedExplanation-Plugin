# 更新日志 (Changelog)

## [2.0.1] - 2026-10-26

### 修复 (Fixed)
- `search_mode = "auto"` 曾叠加一条「问题长度 >= 12 字」的判据。12 字以上的提问几乎都满足，auto 实际等价于 `always`。现在 auto 只按时效和知识性线索词判断，与配置语义一致。

### 变更 (Changed)
- `activation_probability` 从 `[activation]` 移回 `[detailed_explanation]`，回到 1.4.2 及更早版本的位置。

### 清理 (Chore)
- `segmentation.py` 移除 Pydantic 已经保证的重复下限钳制。
- 测试统一放进 `tests/`，导入路径收进一个 `tests/conftest.py`。
- `AGENTS.md` 只留 agent 需要的契约和规范，功能说明交给 README。
- 移除本地残留的 `config.toml` 和 `.vscode/settings.json`。两者都在 `.gitignore` 里，不影响仓库。
- 重写 README、AGENTS.md 和本文件的句子：拆开长句，去掉绕口的说法，同一件事统一用词。

## [2.0.0] - 2026-10-26

### 破坏性变更 (Breaking)
- 适配 MaiBot 1.x 的 Host/Runner 插件体系（`maibot-plugin-sdk` 2.8.1+）。不再是 0.x 的 `src.plugin_system` 插件。
- `_manifest.json` 升到 Manifest v2：新增 `id`、`sdk`、`capabilities`、`i18n`，仓库链接改为 `fulanowo/MaiBot-DetailedExplanation-Plugin`。
- 配置模型改用 `PluginConfigBase`，由 WebUI 渲染。`config.toml` 改为运行时生成，并加进 `.gitignore`。
- 移除 `FEATURE_IMPLEMENTATION.md`。它描述的是 0.x 的内部实现，那部分代码已经不在。

### 变更 (Changed)
- `Action`（`LLM_JUDGE`）和独立的 `Tool` 合成一个 `@Tool("detailed_explanation")`。SDK 已经把 Action 归一成 Tool。
- 关键词触发和概率触发改由 `@HookHandler` 实现，挂在 `chat.receive.after_process` 上。命中后在后台生成，并中止本轮回复。
- 命令组件改用 `@Command(pattern=...)`。topic 从 `matched_groups` 取，返回值改成 `(success, response, intercept)`。
- 人设改用 `ctx.config.get("bot.nickname" / "bot.alias_names" / "personality.*")` 读取。
- `activation_mode` 去掉 `mixed`，新增 `never`。
- `conversation_context` 去掉 `max_intercept_level`，1.x 没有这个过滤层级。
- `content_generation` 去掉 `enable_tools` 和 `enable_chinese_typo`。`search_tool_names` 改名为 `search_api_names`。

### 移除 (Removed)
- `mood_manager` 情绪注入。1.x 已移除 mood 模块。

### 新增 (Added)
- `on_load`、`on_unload`、`on_config_update` 生命周期实现。卸载时取消全部后台任务。
- 模型任务校验：`model_task` 不在宿主可用任务列表里时写一条明确的错误，不再静默回退。
- 纯函数模块 `segmentation.py` 和 `keyword_rules.py`。测试不再 stub `src.*`。

## [1.4.2] - 2025-12-23

### 修复 (Fixed)
- 适配 MaiBot 0.12+：`mood` 模块移除后，插件不再因为 `No module named 'src.mood'` 加载失败。

### 兼容性 (Compatibility)
- `main` 分支面向 MaiBot 0.12+。情绪注入自动降级为默认心情文案。
- 需要 MaiBot 0.11 及更早版本的完整情绪注入，请用 `maibot-0.11` 分支。

## [1.4.1] - 2025-12-19

### 新增功能 (Added)
- **会话上下文注入**：新增 `[conversation_context]` 配置节。生成长文前自动带入一段「最近对话摘录」，适合多轮追问和承接上文的场景。

### 优化 (Improved)
- **性能**：上下文消息查询移到线程里执行，不再阻塞事件循环。
- **效果**：挑上下文时加入去噪、去重、保留最近结尾、按相关性挑选，并优先保留回复链上的消息。

### 兼容性 (Compatibility)
- **联网插件适配**：支持 `google_search_plugin` 的 `web_search` 工具名。保留 `search_online` 回退，可用 `content_generation.search_tool_names` 配置尝试顺序。

## [1.4.0] - 2025-12-07

### 新增功能 (Added)
- **关键词检测与动态 Prompt**：新增 `[keyword_prompts]` 配置节，按用户输入里的关键词挑选对应的 prompt。
  - 可以自定义关键词和 prompt 的对应关系。
  - 每条规则可配关键词列表、prompt 和优先级。
  - 三种匹配策略：first（第一个命中）、highest（优先级最高）、merge（合并全部命中）。
  - 支持区分大小写和不区分大小写两种模式。
  - 预置 6 个领域规则：技术、历史文化、科学、商业经济、医学健康、艺术设计。

### 实现细节 (Implementation)
- `DetailedExplanationAction` 和 `DetailedExplanationCommand` 各加一个 `_detect_keyword_prompt()` 方法。
- `_generate_detailed_content()` 接入动态 prompt 选择。
- `config_schema` 加上 `keyword_prompts` 配置节。
- 配置文件里补上完整的关键词规则示例。

### 配置示例 (Configuration)
```toml
[keyword_prompts]
enable = true
case_sensitive = false
match_strategy = "highest"

[[keyword_prompts.rules]]
keywords = ["技术", "编程", "代码", "算法", "开发", "程序"]
prompt = "请以技术专家的角度进行深入的技术解释..."
priority = 10
```

### 兼容性 (Compatibility)
- 向后兼容，不影响现有功能。
- 原有的 LLM 判断和关键词激活机制照常工作。
- 原有的 persona 保留和 mood 注入照常工作。
- 默认开启。不需要时把 `enable` 设为 `false` 关掉。

### 测试 (Testing)
- 代码语法校验通过。
- 配置文件 TOML 语法校验通过。
- 关键词检测单测 6/6 通过。
  - 技术关键词、历史关键词、科学关键词
  - 多关键词优先级、无匹配关键词、大小写不敏感

### 文档更新 (Documentation)
- README.md 补上关键词检测的说明。
- 主要特性部分列出这个新功能。
- 配置说明部分补上完整的参数说明。
- 补上使用场景示例。

---

## [1.3.0] - 之前版本

### 主要特性
- 智能激活，并融合人设风格
- 直接调用 LLM 生成长文
- 使用 replyer 模型集合
- 分段发送
- 可选联网搜索增强
- 自动迁移配置

---

**注：本版本由 Snow AI CLI 协助开发**
