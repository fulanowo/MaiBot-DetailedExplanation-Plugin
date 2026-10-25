# AGENTS.md - 麦麦细说插件

给在本目录工作的 agent 与贡献者的说明。用户文档见 [README.md](README.md)，改动记录见 [CHANGELOG.md](CHANGELOG.md)。

## 这是什么

MaiBot 1.x 插件：用户需要长文解释时，直连模型生成结构化长文，按段落切分后逐段发送，并保留麦麦的人设与表达风格。

适配目标：MaiBot 1.2.0+ / `maibot-plugin-sdk` 2.8.1+。旧版 0.x 实现在 `maibot-0.x` 分支。

## 技术栈

- Python 3.11+，全异步
- `maibot_sdk`：`MaiBotPlugin` 基类、`@Tool` / `@Command` / `@HookHandler` 装饰器、`PluginConfigBase` 配置模型
- Host/Runner IPC：插件跑在独立子进程，所有主程序能力经 `self.ctx` 代理，不可 `import src.*`
- 测试：pytest，仅覆盖纯函数模块

## 目录结构

```
.
├── plugin.py                    # 插件主类 + 配置模型 + 三个组件
├── segmentation.py              # 分段算法（纯函数）
├── keyword_rules.py             # 关键词 → 领域 Prompt（纯函数）
├── _manifest.json               # Manifest v2
├── config.toml                  # 运行时生成，已 gitignore
├── tests/test_segmentation.py   # 分段算法测试
├── test_keyword_detection.py    # 关键词规则测试
├── README.md                    # 中文用户文档
└── CHANGELOG.md                 # 更新日志
```

## 组件契约

| 组件 | 要点 |
| --- | --- |
| `@Tool("detailed_explanation")` | 参数 `topic` / `context`，上下文取自 `kwargs` 的 `stream_id` / `group_id` / `user_id`；返回 `{"success", "content", "stop_after_execution"}` |
| `@Command("detailed_explanation")` | topic 取 `kwargs["matched_groups"]["topic"]`，stream 取 `kwargs["stream_id"]`；返回 `(success, response, intercept)`，`intercept=1` 表示阻断后续链路 |
| `@HookHandler("chat.receive.after_process")` | 载荷只有 `message` 字典，stream 取 `message["session_id"]`；命中返回 `{"action": "abort"}`，否则 `{"action": "continue"}` |

注意：

- Command 的 `response` 只写日志，不会自动发到聊天，消息必须自己 `ctx.send.text` 发出。
- Hook 里禁止阻塞：生成长文要用 `asyncio.create_task` 放到后台，并把任务句柄收进集合。
- 所有后台任务在 `on_unload` 中取消，避免重载后残留。

## 开发规范

- 中文注释与日志；日志用 `self.ctx.logger`，不要 `print`。
- import 分组：`from ... import` 优先、按字母序，再普通 `import`，本地相对导入空行分隔。
- 纯逻辑（分段、关键词匹配、上下文摘录）放模块级函数，便于脱离 SDK 测试；不要在函数里偷偷兜底。
- 配置一律走 `PluginConfigBase` + `Field`，WebUI 由 `Literal` 自动生成下拉框、由 `list[PluginConfigBase]` 生成可编辑列表；不要再手写 TOML schema。
- 生命周期三方法必须实现：`on_load` / `on_unload` / `on_config_update(scope, config_data, version)`。
- 修改 `_manifest.json` 后必须通过宿主校验（严格模式，多余字段直接报错）。

## 常用命令

```bash
# 纯函数单测
python -m pytest tests/test_segmentation.py test_keyword_detection.py -q

# 语法检查
python -m compileall plugin.py segmentation.py keyword_rules.py
```

## 版本与发布

- `_manifest.json` 的 `version` 必须是严格三段式，并与 `CHANGELOG.md` 对应。
- 破坏性改动（配置结构变化）时同步提升 `[plugin].config_version`，让宿主重建配置文件。
- `host_application` / `sdk` 是闭区间：确认新用到的 API 至少在 `min_version` 中存在再调低。

## 已知限制

- 情绪注入（`mood_manager`）在 1.x 已移除，插件不再注入心情文案。
- 插件不能执行宿主工具，联网增强改为 `ctx.api.call` 调用其他插件公开的 `@API`，默认关闭。
