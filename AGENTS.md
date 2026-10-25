# AGENTS.md - 麦麦细说插件

本文件写给在本目录工作的 agent 和贡献者。用户文档见 [README.md](README.md)，改动记录见 [CHANGELOG.md](CHANGELOG.md)。

本插件跑在 MaiBot 1.x 的 `maibot_sdk` 2.8.1+ 上（MaiBot 1.2.0+）：直接调用模型写结构化长文，切段后逐段发送。旧版 0.x 实现见 `main` 分支。

## 必须遵守的契约

- Command 的 `response` 只写日志，不会自动发出。要发消息就自己调 `ctx.send.text`。
- Hook 的载荷里只有 `message` 字典。session 取 `message["session_id"]`，不是 `kwargs["stream_id"]`。
- Hook 里不能等长文生成。用 `asyncio.create_task` 丢到后台，把任务句柄收进集合，由 `on_unload` 统一取消。
- `@Tool` 返回 `{"success", "content", "stop_after_execution"}`。
- `@Command` 返回 `(success, response, intercept)`。`intercept=1` 阻断主链。
- 插件跑在独立子进程里，不能 `import src.*`。能力一律经 `self.ctx` 调用。要用新能力，先写进 `_manifest.json` 的 `capabilities`。

## 开发规范

- 注释和日志用中文。日志走 `self.ctx.logger`，不要 `print`。
- import 分组：先 `from ... import`（按字母序），再普通 `import`，本地相对导入空行分隔。
- 纯逻辑（分段、关键词匹配、上下文摘录）写成模块级纯函数，方便脱离 SDK 测试。
- 配置一律用 `PluginConfigBase` + `Field` 声明，不要手写 TOML schema。
- 生命周期三个方法必须实现：`on_load` / `on_unload` / `on_config_update(scope, config_data, version)`。
- 改完 `_manifest.json` 必须过宿主校验。校验是严格模式，多一个字段就报错。

## 常用命令

```bash
python -m pytest tests -q
python -m compileall plugin.py segmentation.py keyword_rules.py
```

## 版本与发布

- `_manifest.json` 的 `version` 用严格三段式，和 `CHANGELOG.md` 的条目对应。
- 配置结构变了就提升 `[plugin].config_version`，让宿主重建配置文件。
- `host_application` 和 `sdk` 都是闭区间。代码里用到某个 API，该 API 必须已经出现在 `min_version` 那版里。

## 已知限制

- 1.x 已移除 `mood_manager`，插件不再注入心情文案。
- 插件不能执行宿主工具。联网增强改成用 `ctx.api.call` 调其他插件公开的 `@API`，默认关闭。
