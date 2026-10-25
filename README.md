# 麦麦细说插件 (Detailed Explanation Plugin)

用户提出需要长文回答的问题时（科普、技术、概念等），本插件直接调用模型写一篇结构化长文。长文按段落切开，逐段发送。它不经过默认回复链路的长度限制和风格改写，因此能写得更长，更接近专栏文章。麦麦的人设和表达风格照旧保留。

> 本版本适配 **MaiBot 1.x**（Host/Runner 插件体系，`maibot_sdk` 2.8.1+）。旧版 0.x 实现见 `main` 分支。需要 MaiBot 0.11 及更早版本的实现，见 `maibot-0.11` 分支。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| MaiBot | 1.2.0 ~ 1.9.x |
| Plugin SDK | 2.8.1 ~ 2.99.x |
| Python | 3.11+ |

## 组件一览

| 组件类型 | 名称 | 说明 |
| --- | --- | --- |
| `Tool` | `detailed_explanation` | 注册为核心工具。模型判断需要长文解释时直接调用。调用后发出长文，并阻止本轮再走一遍默认回复 |
| `Command` | `detailed_explanation` | `/细说 <主题>`、`/explain`、`/详细`、`/科普`。手动触发，触发后拦截后续链路 |
| `HookHandler` | `detailed_explanation_auto` | 挂在 `chat.receive.after_process`。按 `activation` 配置判断本条消息要不要自动生成。命中后在后台生成长文，并中止本轮回复 |

## 触发方式

`[activation].activation_mode` 有五个取值：

| 取值 | 行为 |
| --- | --- |
| `llm_judge` | 默认。是否触发全交给模型：模型调用 `detailed_explanation` 工具才触发 |
| `keyword` | 消息命中关键词就自动触发。内置 16 个，另加 `custom_keywords` |
| `always` | 每条普通消息都触发，只用于调试 |
| `random` | 按 `[detailed_explanation].activation_probability` 的概率触发 |
| `never` | 关掉自动触发，只留手动命令和工具调用 |

内置触发关键词：`详细 / 科普 / 解释 / 说明 / 原理 / 深入 / 具体 / 详细说说 / 展开讲讲 / 多讲讲 / 详细介绍 / 深入分析 / 详细阐述 / 深度解析 / 请详细 / 请展开`。

## 使用示例

模型工具调用（默认）

```
用户：详细解释一下 RAG 的完整工作流程
麦麦：让我详细说明一下...
麦麦：(1/3) 概览：RAG（Retrieval-Augmented Generation）通过「检索 + 生成」两阶段...
麦麦：(2/3) 工作原理：① 检索准备 ② 查询扩展 ③ 召回候选 ④ 重排 ⑤ 上下文构建 ⑥ 生成...
麦麦：(3/3) 常见误区与实践建议：...
```

手动命令

```
用户：/细说 量子计算
麦麦：让我详细说明一下...
麦麦：(1/2) 量子计算基础概念...
麦麦：(2/2) 应用与前景...
```

## 安装

1. 把本目录放进 `MaiBot/plugins/`，目录名随意，例如 `MaiBot-DetailedExplanation-Plugin`。
2. 启动 MaiBot。宿主会另起一个子进程加载插件，首次加载自动生成 `config.toml`。
3. 在 WebUI 的插件页确认插件已加载，需要时到配置页改参数。

> 1.x 起配置在 WebUI 里改。`config.toml` 只是保存结果，手工改文件后要重载插件才生效。

## 权限声明

`_manifest.json` 声明的能力与用途：

| 能力 | 用途 |
| --- | --- |
| `send.text` | 逐段发送长文，以及开场提示 |
| `llm.generate` | 写长文与扩写内容 |
| `llm.get_available_models` | 确认 `model_task` 在宿主可用的任务里 |
| `config.get` | 读 `bot.nickname`、`bot.alias_names`、`personality.*`，用于注入人设 |
| `message.get_by_time_in_chat` | 拉最近对话当上下文 |
| `api.call` | 可选。调用其他插件公开的检索 API 做联网增强 |

## 配置说明

### `[plugin]`

- `enabled`：总开关（默认 `true`）
- `config_version`：配置文件版本，由插件维护。升级时靠它判断要不要重建配置

### `[detailed_explanation]`

- `enable`：是否启用详细解释功能（默认 `true`）
- `max_total_length`：全文最大字符数，超出截断（默认 `3000`）
- `min_total_length`：全文最小字符数，不足时自动扩写，最多扩两次（默认 `200`）
- `segment_length`：每段的目标字符数（默认 `400`）
- `min_segments`：分段数下限。切出来的段数少于它，就整篇一次发出（默认 `1`）
- `max_segments`：分段数上限。多出来的段并进最后一段（默认 `4`）
- `send_delay`：段与段之间的发送间隔，单位秒（默认 `1.5`）
- `show_progress`：是否给每段加 `(1/3)` 这样的进度前缀（默认 `true`）
- `show_start_hint`：是否在生成前先发一条开场提示（默认 `true`）
- `start_hint_message`：开场提示的文案
- `activation_probability`：`random` 模式下每条消息的触发概率（默认 `0.1`）

### `[activation]`

- `activation_mode`：`llm_judge | keyword | always | random | never`（默认 `llm_judge`）。含义见「触发方式」
- `strict_mode`：关键词匹配是否区分大小写（默认 `false`）
- `custom_keywords`：在内置关键词之外追加的触发词

### `[content_generation]`

- `model_task`：用哪个模型任务写长文。取 `model_config.toml` 里 `model_task_config` 的名字（默认 `replyer`）
- `extra_prompt`：追加在结构化要求后面的额外指令
- `generation_timeout`：单次生成的等待上限，单位秒。扩写同样适用（默认 `120`）
- `enable_search`：生成前是否先联网检索（默认 `false`）
- `search_mode`：`auto | always | never`（默认 `auto`）。`auto` 只在问题出现时效或具体信息线索时才检索，例如「最新」「为什么」「如何」。`always` 每次都检索。`never` 从不检索
- `search_api_names`：要调用的插件 API 全名，按顺序尝试（默认空）。例如 `search_plugin.web_search`
- `search_timeout`：单次检索的等待上限，单位秒（默认 `20`）

### `[segmentation]`

- `algorithm`：`smart | sentence | length`（默认 `smart`）
  - `smart`：先保住整段，段落超长再按句切
  - `sentence`：按句子往段里装
  - `length`：按字符数硬切
- `sentence_separators`：算作句末的标点集合（默认 `["。", "！", "？", ".", "!", "?"]`）
- `keep_paragraph_integrity`：是否保持段落完整、不跨段切开（默认 `true`）
- `min_paragraph_length`：短于这个长度的段落并入下一段（默认 `50`）

### `[keyword_prompts]`

- `enable`：是否启用关键词规则（默认 `true`）
- `case_sensitive`：是否区分大小写（默认 `false`）
- `match_strategy`：`first` 用第一条命中的规则。`highest` 用优先级最高的规则（默认）。`merge` 把命中的 prompt 全部合并
- `rules`：规则列表。每条含 `keywords`、`prompt`、`priority`

预置六条规则：技术（10）、科学（9）、医学健康（9）、历史文化（8）、商业经济（7）、艺术设计（6）。

命中后，插件用该规则的 `prompt` 顶替默认的结构化要求。例如：

```
用户：详细解释一下 Python 编程的核心概念
-> 命中「编程」，改用技术专家视角的要求（核心原理 + 代码示例 + 最佳实践 + 方案对比）
```

### `[conversation_context]`

- `enable`：生成前是否摘录最近对话（默认 `true`）
- `scope`：`chat`（默认）取整段会话。`user` 只取当前用户和机器人的消息，群聊里噪声更少
- `max_messages`：最多带几条历史消息，`0` 表示不带上下文（默认 `12`）
- `time_window_seconds`：往回看多久，单位秒（默认 `1800`）
- `max_chars`：上下文文本的字符上限（默认 `1200`）
- `per_message_max_chars`：单条历史消息的字符上限（默认 `240`）
- `include_bot_messages`：是否带上机器人自己说过的话（默认 `true`）

挑上下文时，插件先去掉噪声和重复消息。噪声指单字、纯符号、`嗯/哦/好的` 这类内容。剩下的消息里先留最近 4 条，再按与问题的用词重合度补足。本条消息回复的那条历史消息，一定会带上。

## 关于联网增强

MaiBot 1.x 的联网检索由主程序提供。在 `model_config.toml` 里打开 `[web]`，配好 `model_task_config.web_search`，主程序的 Planner（规划器）就能用 `web_search` / `web_fetch` 工具。

插件自己**不能**执行宿主工具，所以本插件的联网增强改成调用**其他插件公开的 `@API`**：

1. 确认目标插件已加载，它的 `@API` 里有一个接受 `query` 参数的检索接口。
2. 把 API 全名填进 `content_generation.search_api_names`，例如 `search_plugin.web_search`。
3. 打开 `content_generation.enable_search`。

没有配 `search_api_names` 时，插件只写一条警告日志并跳过检索，长文照常生成。

## 开发

```bash
# 纯函数单测，不需要 MaiBot 运行时
python -m pytest tests -q
```

代码结构：

| 文件 | 职责 |
| --- | --- |
| `plugin.py` | 插件主类、配置模型、Tool / Command / HookHandler 组件 |
| `segmentation.py` | 分段算法的纯函数 |
| `keyword_rules.py` | 关键词到领域 prompt 的匹配纯函数 |
| `tests/test_segmentation.py` | 分段算法测试 |
| `tests/test_keyword_detection.py` | 关键词规则测试 |

约定：

- 纯逻辑放独立模块，方便脱离运行时测试。
- 组件返回值必须符合 Host 契约：Command 返回 `(success, response, intercept)`，Tool 返回字典。
- 后台任务在 `on_unload` 里统一取消，不留模块级状态。

## 故障排查

| 现象 | 排查方向 |
| --- | --- |
| 插件没加载 | 查 `_manifest.json` 的 `id` / `version` / `host_application` 区间有没有覆盖当前 MaiBot 版本 |
| 生成失败 | 日志里找「配置的模型任务 X 不在可用任务 [...] 中」，按提示改 `model_task`。也可以确认模型本身连得上 |
| 长文没发出来 | 查插件有没有 `send.text` 权限，以及调用时有没有传 `stream_id` |
| 分段不理想 | 调 `segment_length`、`max_segments` 或 `algorithm`。实在不行关掉 `keep_paragraph_integrity` |
| 关键词触发太频繁 | 换成 `llm_judge`，或者收紧 `custom_keywords` |

## 项目信息

- 许可证：GPL-3.0-or-later
- 仓库：https://github.com/fulanowo/MaiBot-DetailedExplanation-Plugin
- 反馈：https://github.com/fulanowo/MaiBot-DetailedExplanation-Plugin/issues
