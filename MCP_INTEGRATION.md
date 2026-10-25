# 麦当劳 MCP 接入说明

## 1. 接入目标

“薯条多重奏”使用麦当劳中国官方 MCP 完成快速薯条点餐。Skill 负责理解短指令、编排调用与确认边界；本地脚本只处理菜单和份数，不提供伪造的菜单、价格或订单结果。

## 2. Server 与协议

| 项目 | 值 |
|---|---|
| 官方 Server | `https://mcp.mcd.cn` |
| 开放平台 | `https://open.mcd.cn/mcp` |
| 传输协议 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}` |
| 官方限流 | 每 Token 每分钟最多 600 次请求 |
| 官方文档 | https://github.com/M-China/mcd-mcp-server |

真实 Token 只应存在于用户的本机连接器配置或环境变量中。仓库内的配置文件、文档、测试和样例均不包含真实 Token。

## 3. 使用的 Tools

### 主流程

| Tool | 用途 | 何时调用 | 是否写操作 |
|---|---|---|---|
| `query-nearby-stores` | 查询地址附近的可用门店 | 未明确门店或需更换门店 | 否 |
| `query-meals` | 获取当前门店、时段的可售菜单 | 每次形成新订单计划前 | 否 |
| `query-meal-detail` | 核对商品详情、组成或特制能力 | 独立薯条以外的详情确有需要时 | 否 |
| `calculate-price` | 获取商品金额、优惠、费用和应付总价 | 每次展示确认摘要前 | 否 |
| `create-order` | 创建真实订单并返回支付信息 | 用户明确确认当前摘要后，仅一次 | 是 |

### 按需流程

| Tool | 用途 | 使用限制 |
|---|---|---|
| `now-time-info` | 获取服务器当前时间 | 需要官方时间上下文时使用 |
| `query-store-coupons` | 查询当前门店可用券 | 仅用户要求优惠比较时 |
| `query-my-coupons` | 查询账户券 | 仅用户明确授权该次查询时 |
| `query-order` | 查询订单状态 | 下单结果未知或用户查单时 |
| `order-list` | 辅助排查未知下单结果 | 仅在避免重复订单或用户要求时 |
| `delivery-query-addresses` | 获取外送地址候选 | 仅外送场景且用户要求时 |
| `delivery-query-stores` | 查询可配送门店 | 仅外送场景 |

不调用 `auto-bind-coupons`、`cancel-order`、`delivery-create-address`、`draw-lottery`、`mall-create-order` 或其他与本任务无关的工具。

## 4. 调用流程

```text
用户短指令
  ↓
解析份数 / 规格 / 风味 / 快捷预设
  ↓
query-nearby-stores（门店未明确时）
  ↓
query-meals
  ↓
fries_planner.py：筛选独立薯条，处理数量与歧义
  ↓
query-meal-detail（仅详情确有需要时）
  ↓
calculate-price
  ↓
展示门店 + 就餐方式 + 商品 + 数量 + 官方总价
  ↓
用户明确确认当前摘要
  ↓
create-order（仅一次）
  ↓
返回订单号与支付链接，由用户自行支付
```

若 `create-order` 超时或结果未知，先调用 `query-order` 或 `order-list` 核查，不能直接重试创建。任何门店、商品、数量或价格变化都会使旧确认失效。

## 5. 本地组件职责

### `scripts/fries_planner.py`

- 读取 `query-meals` 原始或归一化 JSON。
- 识别“独奏 / 二重奏 / 分享装”和“来三份大薯”等输入。
- 排除套餐、薯饼、停售商品和不相关组合。
- 输出 `ready_for_official_price`、`needs_clarification` 或 `no_fries_found`。
- 不联网、不计算最终应付价、不创建订单。

### `scripts/mcp_client.py`

- 使用 Streamable HTTP 完成初始化、会话 ID 传递、`tools/list` 和 `tools/call`。
- 支持 JSON 与 SSE 响应。
- Token 只从 `MCD_MCP_TOKEN` 环境变量读取。
- 使用白名单显式限制为查询和算价工具；拒绝所有写工具。
- 用于开发联调，不替代 WorkBuddy 的确认后下单流程。

## 6. 业务价值

普通点餐链路需要逐级打开分类、寻找商品、选择规格和数量。薯条多重奏把高频、低歧义的薯条需求压缩成一句短指令，同时保留三项关键校验：实时菜单、官方价格、明确下单确认。快捷预设减少输入，歧义检测防止错选风味或商品编码，未知结果查单策略降低重复订单风险。

官方算价后还可以生成“薯条人格”分享卡：把份数映射为独奏家、二重奏指挥、多重奏作曲家和薯条乐团团长，配一句确定性乐评。分享卡是可选的本地增强，不额外调用 MCP，不写入账户信息，也不自动发布到社交平台。它让价格确认从一段纯文本变成可分享的轻量内容，同时保持“尚未下单”和“订单已创建”的状态区分。

订单创建成功后，可把本次份数写入本机“薯条档案”。档案按 1 / 10 / 25 / 50 / 100 / 200 / 500 份解锁称号，生成终端摘要或 HTML 成就页。历史文件只保存日期、份数、商品名、门店名和实付金额，不保存订单号、支付链接、手机号、详细地址或 Token；该功能不额外请求 MCP，也不会上传历史。

## 7. 验证记录

### 离线验证

2026-10-24 在本机使用 Python 标准库 `unittest` 执行测试，覆盖：

- 快捷预设与中英文数字份数解析。
- 规格、风味、停售、套餐与薯饼筛选。
- 多候选歧义和无结果处理。
- MCP JSON/SSE 解析、Bearer 鉴权头、会话 ID 传递。
- 本机模拟 MCP 的 initialize、tools/list 和只读 tools/call。
- `create-order` 等非只读工具的无网络拦截。

模拟数据只用于验证代码逻辑，不代表真实麦当劳菜单、商品编码、价格或供应状态。

### 真实接口验证

2026-10-24，使用参赛者自己的 MCP Token 在本机完成真实只读联调。记录不包含 Token、手机号、账户凭证或支付信息。

- `list-tools`：成功获取官方 MCP 工具列表和实时 schema。
- `query-nearby-stores`：以 `beType=1`、`searchType=2`、城市和关键词查询到店自取门店，成功返回门店名称、地址、距离、营业状态、`storeCode`；`beType=1` 返回的门店没有 `beCode`，后续不传。
- `query-meals`：使用演示门店 `storeCode`、`orderType=1`、`beType=1` 成功获取实时菜单。菜单把商品详情放在 `data.meals` 映射表中，键为商品编码；本次菜单包含编码为 `4810` 的“薯条”，菜单价为 14.5 元。
- `query-meal-detail`：对 `4810` 成功核对详情，确认商品名为“中薯条”，无套餐选配轮次，不支持特调。
- `fries_planner.py`：先用该实时菜单生成“来三份薯条”的计划，返回 `ready_for_official_price`；商品编码 `4810`，数量 3，状态未算价、未下单。
- `calculate-price`：使用 `storeCode`、`orderType=1`、`beType=1`、`items=[{productCode:"4810", quantity:3}]` 和 `needTableware=false` 成功算价。返回金额单位为分：商品原价 4350 分，优惠 100 分，现价 4250 分，即官方应付 42.50 元；返回商品名为“中薯条”，并给出到店取餐方式选项。
- 结果边界：上述结果只证明真实接口链路可用，不表示已创建订单，也不保证其他门店、日期或时段可售同样商品。演示查询使用了公开城市与关键词，未提交用户私人地址。
