# astrbot_plugin_jx3

基于 [AstrBot](https://docs.astrbot.app/) 框架开发的剑网三游戏数据查询插件。插件主要通过 JX3API、JX3BOX、茶馆等外部接口获取游戏数据，整理为文本消息、富媒体消息，或通过 `HTML + Jinja2` 模板渲染成图片后发送。

当前插件以“查询型功能”为主，覆盖日常、官方、角色、职业、休闲、阵营、副本、活动、交易、杂项、排行、推送和本地避雷等场景。部分功能需要配置 JX3API Token，少量职业/角色类接口还需要推栏 ticket。

## 功能概览

插件内置 `功能` 指令，会以图片形式展示完整指令列表、参数说明和是否需要令牌。当前帮助页按 13 个功能分组维护，约 88 条指令。

主要功能包括：

- 日常功能：日常、月历、名望、诛恶。
- 官方功能：公告、维护、技改、区服、开服、状态。
- 角色功能：角色、资历、名片、所有名片、奇遇、未做奇遇、战绩、精耐。
- 职业功能：小药、宏、配装、阵眼、奇穴、技能。
- 休闲功能：烟花、拜师、收徒、随机名片、攻略、奇遇统计、近期奇遇、奇遇汇总。
- 阵营功能：沙盘、阵营拍卖、阵营事件、关隘首领、帮战记录、统战 YY。
- 副本功能：百战、招募、掉落、解密。
- 活动功能：扶摇、本日赤兔、本周赤兔、刷马、的卢。
- 交易功能：金价、物价、交易行、贴吧物价。
- 杂项功能：科举、花价、装饰、器物、八卦、骗子、骚话。
- 排行功能：名剑统计、名剑排行、资历排行、试炼排行和各类风云录榜单。
- 推送功能：开服推送、新闻推送、刷马推送、赤兔推送。
- 避雷功能：避雷查看、添加、删除、修改、查询。

## 安装与依赖

将插件目录放入 AstrBot 的插件目录中，例如：

```text
data/plugins/astrbot_plugin_jx3
```

安装依赖：

```bash
pip install -r requirements.txt
```

当前依赖：

- `aiohttp`：异步 HTTP 请求。
- `aiofiles`：异步文件处理。
- `aiosqlite`：本地 SQLite 数据库。
- `apscheduler`：后台推送任务调度。
- `matplotlib`：部分图像/数据展示依赖。

插件元信息在 `metadata.yaml` 中维护，当前版本为 `v2.7`，要求 AstrBot 版本 `>=4.11.0`。

## 插件配置

配置结构由 `_conf_schema.json` 定义，主要配置项如下。

### 指令前缀

```json
{
  "prefix": {
    "enable": true,
    "text": "剑三"
  }
}
```

- `enable`：是否启用指令前缀检查。
- `text`：指令前缀内容，默认 `剑三`。

启用后，用户需要发送类似 `剑三 日常`、`剑三 奇遇 角色名` 才能触发。关闭后可直接发送 `日常`、`奇遇 角色名`。

### 默认服务器

```json
{
  "server": "梦江南"
}
```

许多指令都带有 `[服务器]` 可选参数。用户未填写服务器时，插件会使用这里配置的默认服务器。

示例：

```text
奇遇 飞翔大野猪
```

等价于：

```text
奇遇 飞翔大野猪 梦江南
```

前提是默认服务器配置为 `梦江南`。

### JX3API Token

```json
{
  "jx3api_token": ""
}
```

需要令牌的功能必须配置该字段。Token 需要在 [JX3API](https://www.jx3api.com/) 注册并购买后获取。

帮助页中标记为“需令牌”的指令，如果未配置 Token，可能无法正常返回数据。

### 推栏 Ticket

```json
{
  "jx3api_ticket": ""
}
```

部分接口需要推栏 ticket，例如部分职业、角色、学校类接口。该值通常需要通过抓包推栏 App 的请求参数获得。

### 推送配置

插件支持 4 类后台推送：

- `kfts`：开服监控。
- `xwts`：新闻资讯。
- `smts`：刷马消息。
- `ctts`：赤兔消息。

每类推送配置都包含：

- `enable`：是否启用。
- `time`：轮询间隔，单位秒。
- `umos`：推送目标会话 ID 列表。

示例：

```json
{
  "kfts": {
    "enable": false,
    "time": 60,
    "umos": ["QQ:GroupMessage:123456"]
  }
}
```

`umos` 需要填写完整会话 ID，可通过 AstrBot 的 `/std` 等方式获取。推送本质是后台定时请求接口，检测状态变化后向配置的会话发送消息，不建议将轮询间隔设置得过短。

## 使用方式

发送：

```text
功能
```

即可获取完整指令帮助图。

如果开启了指令前缀，则发送：

```text
剑三 功能
```

指令参数说明：

- `[]` 表示可选参数。
- `[服务器]` 未填写时使用插件默认服务器。
- 数量、天数、模式等参数未填写时使用对应功能的默认值。

示例：

```text
日常
诛恶
资历 飞翔大野猪
交易行 五行石 梦江南
奇遇 飞翔大野猪
未做奇遇 飞翔大野猪 梦江南
战绩 飞翔大野猪 梦江南 33
名剑排行 50 33
贴吧物价 狐金 5 梦江南
统战 梦江南
```

## 目录结构

```text
astrbot_plugin_jx3/
├─ main.py                  # AstrBot 插件入口，初始化配置、资源、服务和指令分发
├─ metadata.yaml            # 插件元信息
├─ _conf_schema.json        # AstrBot 后台配置 schema
├─ requirements.txt         # Python 依赖
├─ data/
│  ├─ api_config.json       # 外部接口配置，按功能 key 维护 URL、method、默认参数
│  └─ plugin_data.db        # 插件随包数据，主要用于内置数据
├─ core/
│  ├─ jx3_data.py           # 业务数据层，调用接口、整理数据、选择模板
│  ├─ message.py            # 消息构建层，负责文本、图片、富媒体回复
│  ├─ request.py            # aiohttp 请求封装，统一处理 GET/POST 和接口返回
│  ├─ async_task.py         # APScheduler 后台推送任务
│  ├─ bilei_data.py         # 本地避雷数据增删改查
│  ├─ sqlite.py             # SQLite 异步封装
│  └─ fun_basic.py          # 模板加载、图片 base64、通用格式化工具
└─ templates/
   ├─ helps.html            # 功能帮助页
   ├─ *.html                # 各图片指令的 HTML/Jinja2 模板
   ├─ img/                  # 通用图片资源
   ├─ sect/                 # 门派/心法图标
   └─ serendipity/          # 奇遇图标
```

## 核心实现逻辑

### 1. 插件初始化

`main.py` 中的 `Jx3ApiPlugin` 是插件入口。

初始化时会完成以下工作：

1. 读取 AstrBot 插件配置，包括前缀、默认服务器、Token、Ticket 和推送配置。
2. 计算本地数据目录、插件数据目录、模板目录和接口配置文件路径。
3. 加载 `templates/img`、`templates/sect`、`templates/serendipity` 中的图片，并转为 base64，供 HTML 模板直接引用。
4. 初始化 SQLite、JX3Service、AsyncTask、BiLeidata、MessageBuilder。
5. 在异步初始化阶段创建本地表，并启动后台推送任务。
6. 构建 `command_map`，将中文触发词映射到对应的消息处理函数。

### 2. 指令分发

用户消息进入插件后，`main.py` 会：

1. 根据配置判断是否需要指令前缀。
2. 将消息按空格切分为 `指令 + 参数`。
3. 在 `command_map` 中查找对应处理函数。
4. 使用 `inspect.signature` 根据函数参数数量自动传入用户参数。
5. 找不到指令时不处理，参数错误时返回提示。

### 3. 消息构建

`core/message.py` 的 `MessageBuilder` 负责把业务数据发出去，主要有几类输出：

- `plain_msg()`：发送纯文本。
- `T2I_image_msg()`：把业务数据传入 HTML 模板，调用 AstrBot 的 HTML 渲染能力生成图片。
- `image_msg()`：直接发送图片 URL 或图片数据。
- `plain_chain()`：发送文本 + 图片等富媒体消息链。
- `handler_plain_image_msg()`：先发文本，再发图片，适用于部分组合型功能。
- `handler_zili_msg()`：资历查询专用两轮会话，先发送 `0-18` 分类菜单，再按用户选择渲染资历进度图片。

所有可选服务器参数都会通过 `serverdefault()` 补齐默认服务器。

### 4. 数据请求与业务处理

`core/jx3_data.py` 是主要业务层。每个功能通常对应一个异步方法，例如：

```python
async def jinqiqiyu(self, server: str) -> Dict[str, Any]:
    ...
```

业务方法通常遵循统一结构：

1. 调用 `_init_return_data()` 创建标准返回对象。
2. 构造接口参数，填入 `server`、`name`、`token`、`ticket` 等。
3. 通过 `_base_request(config_key, method, params)` 读取 `data/api_config.json` 中的接口配置并发起请求。
4. 判断接口返回是否为空或结构异常。
5. 整理时间戳、字段名、分组、列表、统计值等模板需要的数据。
6. 文本功能直接写入 `return_data["data"]`。
7. 图片功能额外加载对应 HTML 模板并写入 `return_data["temp"]`。
8. 成功时设置 `return_data["code"] = 200`。

标准返回结构大致为：

```python
{
    "code": 0,
    "msg": "错误提示",
    "data": {},
    "temp": "",
    "icons": {}
}
```

### 5. 接口请求封装

`core/request.py` 中的 `APIClient` 负责实际 HTTP 请求。

实现特点：

- 复用 `aiohttp.ClientSession`。
- 支持 GET 和 POST。
- 自动识别 JSON、图片或二进制响应。
- 对 JX3API 常见返回结构做基础校验。
- 支持通过 `out_key` 抽取返回对象中的指定字段，默认通常取 `data`。

`JX3Service._base_request()` 会在业务层进一步统一：

- 根据 `data/api_config.json` 查找接口。
- 合并接口默认参数和运行时参数。
- 根据配置 method 调用 GET 或 POST。
- 捕获异常并输出日志。

### 6. 图片渲染

图片输出功能使用 `templates/*.html`。

典型数据流：

```text
JX3Service 整理数据
        ↓
MessageBuilder.T2I_image_msg()
        ↓
注入 icons
        ↓
html_renderer.render_custom_template()
        ↓
发送图片
```

模板里可以使用：

- `icons.img`：通用图标。
- `icons.sect`：门派/心法图标。
- `icons.serendipity`：奇遇图标。

例如门派图标常见写法：

```jinja2
{% set icon = icons.sect.get(item.forceName) %}
{% if icon %}
<img src="{{ icon }}">
{% endif %}
```

### 7. 本地数据库

插件使用两个 SQLite 数据库：

- 插件目录下的 `data/plugin_data.db`：随插件提供的内置数据。
- AstrBot 数据目录中的 `local_data.db`：运行期本地数据。

本地数据主要用于：

- 避雷记录。
- 推送任务状态缓存。
- 资历菜单与资历点数基础数据缓存，默认缓存 30 天，接口失败时可使用旧缓存兜底。
- 交易行物品库基础数据缓存，默认缓存 30 天，接口失败时可使用旧缓存兜底。

`core/sqlite.py` 封装了异步增删改查；`core/bilei_data.py` 基于该封装实现避雷数据管理。

### 8. 资历查询

`资历 角色名称 [服务器]` 是 2.6 新增的两轮对话功能。

第一轮会发送固定分类菜单，用户输入 `0-18` 后进入第二轮：

- `0`：展示角色资历总览，并列出 18 个大类的完成进度。
- `1-18`：展示对应大类总览，并列出该大类下所有子类的完成进度。

实现流程：

1. 通过角色信息接口 `jx3_jueshexinxi` 获取角色 `globalId`。
2. 用 `globalId` 请求 JX3BOX 角色资历接口，获取已完成资历 ID 列表。
3. 从资历菜单接口和资历点数接口读取基础数据，并缓存到本地 SQLite。
4. 展开菜单中单个 ID 和数组 ID，按资历点数计算 `已完成点数 / 总点数` 与百分比。
5. 使用 `templates/zili.html` 渲染进度条图片。

### 9. 交易行查询

`交易行 物品名称 [服务器]` 在 2.7 中完成重构，属于交易功能，免令牌，输出为图片。

实现流程：

1. 从 JX3BOX 交易行物品库接口读取所有可查询物品，并缓存到本地 SQLite。
2. 用户输入物品名后，在本地物品库中按名称进行模糊匹配。
3. 匹配结果按“完全匹配、前缀匹配、包含匹配”排序，默认最多取前 50 个物品 ID。
4. 调用 `https://next2.jx3box.com/api/auction/` 批量查询指定服务器的交易行价格。
5. 价格接口未返回的物品不展示；全部无价格数据时直接返回文本提示。
6. 使用 `templates/jiaoyihang.html` 渲染列表图片，展示物品图标、物品名称、价格、数量和数据时间。

价格单位按铜钱换算为砖、金、银、铜，并使用 `templates/img` 下的 `zhuang.png`、`jin.png`、`yin.png`、`tong.png` 图标展示；0 砖不会显示砖图标。

### 10. 后台推送

`core/async_task.py` 使用 APScheduler 实现轮询推送。

当前支持：

- 开服监控。
- 新闻资讯。
- 刷马消息。
- 赤兔消息。

推送逻辑是：

1. 初始化时读取配置和本地旧状态。
2. 对启用且配置了推送目标的任务创建 interval job。
3. 定时调用对应业务方法。
4. 比较新旧状态。
5. 状态变化时向配置会话发送消息，并更新本地状态。

## 新增功能开发流程

新增一个查询功能通常需要改动 4 到 5 个位置：

1. 在 `data/api_config.json` 添加接口配置。
2. 在 `core/jx3_data.py` 添加业务方法，完成请求、数据整理和错误处理。
3. 在 `core/message.py` 添加消息包装方法，选择文本、图片或富媒体输出。
4. 在 `main.py` 的 `command_map` 注册中文触发指令。
5. 如果是图片输出，新增 `templates/xxx.html`。
6. 在 `templates/helps.html` 增加帮助卡片并更新统计。

建议保持以下约定：

- 方法名使用拼音或稳定英文名，避免与现有方法冲突。
- 接口配置 key 使用 `jx3_功能名` 形式。
- 文本功能失败时返回清晰的 `msg`。
- 图片功能返回空数据时不要渲染空图，直接返回文本提示。
- 可选服务器统一通过 `MessageBuilder.serverdefault()` 处理。
- 时间戳尽量在业务层格式化后传给模板。

## 注意事项

- 本插件依赖多个外部接口，接口变更、网络异常、Token 权限不足都会影响结果。
- JX3API 数据源可能存在延迟或遗漏，奇遇、掉落、排行榜等数据不保证 100% 完整。
- Token 与 Ticket 属于敏感配置，不要提交到仓库或公开日志。
- 后台推送会持续请求接口，轮询间隔不要设置过短。
- HTML 模板渲染依赖 AstrBot 的文转图能力，运行环境需要支持对应渲染服务。

## License

本项目遵循仓库内 `LICENSE` 文件声明的许可协议。
