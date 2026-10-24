# 薯条多重奏 Fries Ensemble

一句话快速点薯条的 WorkBuddy Skill。它把“独奏”“二重奏”“分享装”或“来三份大薯”转成待确认订单，使用麦当劳中国 MCP 获取实时门店菜单、执行官方算价，并在明确确认后创建订单。

本项目为参赛作品，不是麦当劳官方产品。不会自动支付，也不会在本地脚本中执行任何账户写操作。

## 功能

- 一句话下单：识别中文或数字份数、规格和风味。
- 三种快捷预设：独奏 1 份中薯、二重奏 2 份中薯、分享装 4 份中薯。
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

## 测试

```bash
python -m unittest discover -s tests -v
python scripts/validate_repo.py
```

测试覆盖快捷指令、中文份数、规格与风味选择、套餐排除、歧义处理、SSE 解析、鉴权头传递、会话 ID 以及写操作拦截。模拟 MCP 服务仅在本机回环地址运行。

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
│   └── validate_repo.py
├── references/
│   └── data-contract.md
└── tests/
    ├── fixtures/menu.sample.json
    ├── test_fries_planner.py
    └── test_mcp_client.py
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
