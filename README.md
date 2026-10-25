# 薯条多重奏 Fries Ensemble

一句话快速点薯条的 WorkBuddy Skill。它把“独奏”“二重奏”“分享装”或“来三份大薯”转成待确认订单，使用麦当劳中国 MCP 获取实时门店菜单、执行官方算价，并在明确确认后创建订单。

本项目为参赛作品，不是麦当劳官方产品。不会自动支付，也不会在本地脚本中执行任何账户写操作。

## 功能

- 一句话下单：识别中文或数字份数、规格和风味。
- 三种快捷预设：独奏 1 份中薯、二重奏 2 份中薯、分享装 4 份中薯。
- 薯条人格：根据份数生成“独奏家 / 二重奏指挥 / 多重奏作曲家 / 薯条乐团团长”和一句乐评。
- 分享卡：用官方算价生成离线 HTML 价格确认卡，可复制分享文案，不包含支付信息。
- 薯条档案：本地记录累计点过多少份薯条，按 1 / 10 / 25 / 50 / 100 / 200 / 500 份解锁成就。
- 成就页：生成可分享的本地 HTML 档案页，展示称号、进度、成就图谱和最近记录。
- 实时菜单：按当前门店和时段筛选独立薯条，排除套餐与薯饼。
- 官方算价：最终金额只采用 `calculate-price` 返回结果。
- 防误触：订单摘要确认后才允许 `create-order`；价格变化需重新确认。
- 防重复：下单结果未知时先查单，不盲目重试。
- 可测试：本地规划器与只读 MCP 客户端仅使用 Python 标准库。

## 目标用户

- 已经明确知道要点几份薯条，希望减少多轮菜单选择的用户。
- 需要为两人或小聚快速准备薯条数量的用户。
- 希望用自然语言完成到店自取或外送订单，同时保留价格确认的人。

## 使用前提

1. 支持 Streamable HTTP MCP 的客户端；推荐 WorkBuddy。
2. 在[麦当劳 MCP 开放平台](https://open.mcd.cn/mcp)申请自己的 Token。
3. 按官方说明启用 `mcd-mcp` 连接器。
4. 运行本地脚本时需要 Python 3.10 或更高版本，无第三方依赖。

## 安装

将本项目导入 WorkBuddy 的自定义 Skill，或把 `fries-ensemble` 目录放入你的 Skills 目录。发布包解压后应保证 `SKILL.md` 位于 `fries-ensemble/` 根目录。

MCP 官方接入信息：

- Server：`https://mcp.mcd.cn`
- 协议：Streamable HTTP
- 鉴权：`Authorization: Bearer <Token>`
- 官方指南：[M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)

`mcp-config.example.json` 仅包含 `${MCD_MCP_TOKEN}` 环境变量占位符。若客户端配置页不支持环境变量展开，请只在本机配置界面替换为真实 Token，不要把修改后的配置提交到仓库。

## 在 WorkBuddy 中使用

首次使用建议同时给出门店和就餐方式：

```text
用薯条多重奏，在天通苑附近门店到店自取，来三份大薯。
```

后续可沿用当前对话中已经明确的门店：

```text
薯条二重奏，沿用刚才的门店。
```

指定风味：

```text
来一份海苔摇摇薯条，规格不限；先查可售情况，不要下单。
```

Skill 会返回门店、商品、数量和官方总价摘要。只有当你明确回复“确认下单”后，才会创建订单。支付仍需由你本人完成。

## 本地体验，不需要 Token

仓库中的样例菜单只用于演示和测试，不代表真实商品、编码或价格：

```bash
python scripts/fries_planner.py --menu tests/fixtures/menu.sample.json --text "来三份大薯"
python scripts/fries_planner.py --menu tests/fixtures/menu.sample.json --mode duet
```

输出 `ready_for_official_price` 表示待官方算价，不表示已经下单。

## 真实接口验证摘要

2026-10-24 使用参赛者自己的 MCP Token 完成只读联调：`query-nearby-stores`、`query-meals`、`query-meal-detail`、`calculate-price` 均成功。演示门店的实时菜单将薯条详情放在 `data.meals` 编码映射中；`calculate-price` 返回金额单位为分。三份薯条的官方算价为原价 43.50 元、优惠 1.00 元、应付 42.50 元。项目未调用 `create-order`。详细边界见 `MCP_INTEGRATION.md`。

## 真实 MCP 联调

在本机安全设置 `MCD_MCP_TOKEN` 环境变量。不要把 Token 粘贴到聊天、命令记录、参数文件或仓库中。

```bash
python scripts/mcp_client.py list-tools
python scripts/mcp_client.py call --tool now-time-info
python scripts/mcp_client.py call --tool query-meals --args-file <按实时schema准备的参数.json>
```

先通过 `list-tools` 核对实时参数 schema。联调客户端只允许白名单内的查询和算价工具，会拒绝 `create-order`、领券、抽奖等写工具。真实下单应通过 WorkBuddy 的受控确认流程完成。

配置好 Token 后，可运行只读端到端冒烟测试，验证时间、门店、菜单、详情到官方算价的完整链路（不会创建订单）：

```bash
python scripts/smoke_test.py
```

## 薯条人格分享卡

官方算价成功后，把门店、商品、金额和算价时间归一化为 JSON，即可生成一张离线分享卡：

```bash
python scripts/make_share_card.py \
  --summary examples/order-summary.sample.json \
  --output examples/share-card.sample.html
```

示例摘要中的数据仅用于演示。真实使用时，`total_yuan` 必须来自 `calculate-price` 返回值除以 100。卡片会显示“价格确认卡 · 尚未下单”，除非订单确实已经创建；不包含支付链接、手机号、地址或 Token。

可选主题：`concert`（默认）、`midnight`、`picnic`。

## 薯条档案与成就

订单创建成功后记录本次份数：

```bash
python scripts/fries_history.py add --quantity 3 --name "中薯条" --store "<门店名>" --total 42.50 --source order
```

查看累计份数、当前称号和下一成就：

```bash
python scripts/fries_history.py summary
```

生成成就页：

```bash
python scripts/fries_history.py summary --html examples/fries-history.sample.html
```

历史文件默认位于 `~/.fries-ensemble/history.json`，可用 `FRIES_HISTORY_PATH` 覆盖。只保存日期、份数、商品名、门店名和实付金额；不保存订单号、支付链接、手机号、详细地址或 Token。补录旧订单时使用 `--date YYYY-MM-DD --source manual`。

| 累计份数 | 称号 |
|---:|---|
| 1 | 初响 |
| 10 | 小型合奏 |
| 25 | 薯条常客 |
| 50 | 多重奏指挥 |
| 100 | 百薯乐团 |
| 200 | 薯条传奇 |
| 500 | 薯条宇宙 |

示例成就页见 `examples/fries-history.sample.html`，其中的门店和记录均为演示数据。

## 测试

```bash
python -m unittest discover -s tests -v
python scripts/validate_repo.py
```

测试覆盖快捷指令、中文份数、规格与风味选择、套餐排除、歧义处理、SSE 解析、鉴权头传递、会话 ID、写操作拦截、分享卡 HTML 转义以及历史成就阈值。模拟 MCP 服务仅在本机回环地址运行。

## 项目结构

```text
fries-ensemble/
├── SKILL.md
├── README.md
├── CONTEST_DECLARATION.md
├── MCP_INTEGRATION.md
├── mcp-config.example.json
├── workbuddy.md
├── scripts/
│   ├── fries_planner.py
│   ├── mcp_client.py
│   ├── smoke_test.py
│   ├── make_share_card.py
│   ├── fries_history.py
│   └── validate_repo.py
├── references/
│   └── data-contract.md
├── examples/
│   ├── order-summary.sample.json
│   ├── share-card.sample.html
│   ├── history.sample.json
│   └── fries-history.sample.html
└── tests/
    ├── fixtures/menu.sample.json
    ├── test_fries_planner.py
    ├── test_mcp_client.py
    ├── test_share_card.py
    └── test_fries_history.py
```

## 边界与故障处理

- 门店菜单、价格、优惠和供应状态可能随时变化，以官方实时结果为准。
- 无法识别商品字段时会要求检查原始响应，不会编造商品编码。
- 遇到 401 时检查 Token；遇到 429 时停止密集请求。官方限制为每 Token 每分钟最多 600 次请求。
- 下单超时后先核查订单，避免重复创建。
- 本地规划器不支持支付、地址修改、自动领券或订单取消。

## 参赛材料

- `CONTEST_DECLARATION.md`：官方原文，未修改。
- `MCP_INTEGRATION.md`：Server、Tool、调用链、业务价值及验证记录。
- `mcp-config.example.json`：脱敏配置。
- `workbuddy.md`：WorkBuddy 开发对话上下文。

活动规则以 [M-China/mcd-developer-innovation-challenge](https://github.com/M-China/mcd-developer-innovation-challenge) 为准。

## 仓库地址

https://github.com/1780820154/fries-ensemble
