# AGENTS.md - 麦麦细说插件

给在本目录工作的 agent 与贡献者的说明。用户文档见 [README.md](README.md)，改动记录见 [CHANGELOG.md](CHANGELOG.md)。

MaiBot 1.x 插件（`maibot_sdk` 2.8.1+ / MaiBot 1.2.0+）：直连模型生成结构化长文，分段后逐段发送。旧版 0.x 实现见 `maibot-0.x` 分支。

## 契约坑位

- Command 的 `response` 只写日志，不会自动发出；消息必须自己 `ctx.send.text`。
- Hook 载荷只有 `message` 字典，stream 取 `message["session_id"]`，不是 `kwargs["stream_id"]`。
- Hook 里禁止阻塞：生成长文用 `asyncio.create_task` 放到后台，任务句柄收进集合，`on_unload` 统一取消。
- `@Tool` 返回 `{"success", "content", "stop_after_execution"}`；`@Command` 返回 `(success, response, intercept)`，`intercept=1` 阻断主链。
- 插件跑在独立子进程，不能 `import src.*`；能力经 `self.ctx` 代理，用到新能力先写进 `_manifest.json` 的 `capabilities`。

## 开发规范

- 中文注释与日志；日志用 `self.ctx.logger`，不要 `print`。
- import 分组：`from ... import` 优先、按字母序，再普通 `import`，本地相对导入空行分隔。
- 纯逻辑（分段、关键词匹配、上下文摘录）放模块级纯函数，便于脱离 SDK 测试。
- 配置一律走 `PluginConfigBase` + `Field`，不要手写 TOML schema。
- 生命周期三方法必须实现：`on_load` / `on_unload` / `on_config_update(scope, config_data, version)`。
- 改 `_manifest.json` 后必须过宿主校验（严格模式，多余字段直接报错）。

## 常用命令

```bash
python -m pytest tests -q
python -m compileall plugin.py segmentation.py keyword_rules.py
```

## 版本与发布

- `_manifest.json` 的 `version` 严格三段式，与 `CHANGELOG.md` 对应。
- 配置结构变化时提升 `[plugin].config_version`，让宿主重建配置文件。
- `host_application` / `sdk` 是闭区间：用到的 API 必须在 `min_version` 中已存在。

## 已知限制

- 情绪注入（`mood_manager`）在 1.x 已移除，插件不再注入心情文案。
- 插件不能执行宿主工具，联网增强改为 `ctx.api.call` 调其他插件公开的 `@API`，默认关闭。
