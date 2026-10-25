---
name: fries-ensemble
description: This skill should be used when a user wants to quickly order McDonald's fries in China, says 薯条多重奏, asks for 独奏/二重奏/分享装 fries presets, or gives a short request such as 来三份大薯. It matches live store menus, calculates the official price, and creates an order only after explicit confirmation.
---

# 薯条多重奏

## 目标

把一句短指令转成可核对的薯条订单。默认支持“独奏”1 份中薯、“二重奏”2 份中薯、“分享装”4 份中薯；允许覆盖规格、份数和风味关键词。使用麦当劳中国 MCP 的实时数据，不硬编码商品编码、菜单价格或供应状态。

## 安全边界

- 将 `create-order` 视为真实写操作。必须在展示订单摘要后，获得用户对当前摘要的明确确认，再调用一次。
- 不把最初的“我要点薯条”视为对尚未展示的价格和门店的确认。
- 不自动支付，不保存支付信息，不自动领券，不取消订单，不修改地址。
- 未经用户要求，不读取历史订单、账户优惠券或配送地址。
- 价格、供应状态和可售规格以实时 MCP 返回为准。不得用本地脚本结果替代官方算价。
- 不在日志、文档、截图或仓库中写入真实 Token、手机号、详细地址或支付信息。

## 快速流程

1. 解析份数、规格和风味。识别“独奏 / 二重奏 / 分享装”以及“来三份大薯”等短句。信息足够时不要追问偏好。
2. 确认履约上下文。优先沿用当前对话已明确的门店与就餐方式；缺失时只询问必要项。默认推荐到店自取，但在订单摘要中明确展示，不得隐藏默认值。
3. 调用 `query-nearby-stores` 获取可用门店。用户指定门店时精确匹配；仅有模糊区域且返回多个差异明显的门店时，列出少量选项供选择。外送场景改用官方工具 schema 所要求的地址与配送门店查询流程。
4. 调用 `query-meals` 获取当前门店、当前时段的实时菜单。不要从记忆推测薯条是否可售。
5. 筛选独立薯条商品，排除套餐、汉堡、薯饼和含薯条的组合餐。规格或风味不明确且存在多个候选时，只追问这一个差异点。
6. 需要核对套餐组成、替换项或特制选项时调用 `query-meal-detail`。独立薯条无需为了凑流程额外调用。
7. 调用 `calculate-price`，按该工具当前 schema 映射门店、就餐方式、商品编码与数量。只有用户明确要求优惠比较时，才先调用 `query-store-coupons` 或 `query-my-coupons`。
8. 展示确认摘要：门店、就餐方式、商品名称、规格、份数、官方原价、优惠、费用、应付总价及价格更新时间。价格变化时重新展示摘要并再次确认。
9. 用户明确回复“确认下单”或等价表述后，调用 `create-order` 一次。返回订单号和支付链接；说明支付由用户完成。
10. 下单调用超时或结果未知时，不得直接重试。先通过 `query-order` 或 `order-list` 核查是否已创建，避免重复订单。
11. 用户想分享时，可在官方算价后生成“薯条人格”分享卡。卡片中的金额必须来自 `calculate-price`，未下单时明确写“价格确认卡 · 尚未下单”。不把支付链接、手机号、地址或 Token 写入卡片，也不自动发到任何社交平台。

## 使用本地菜单规划器

当需要稳定解析 MCP 菜单 JSON 或复用快捷预设时，运行：

```bash
python scripts/fries_planner.py --menu <query-meals结果.json> --text "来三份大薯"
```

快捷模式示例：

```bash
python scripts/fries_planner.py --menu <query-meals结果.json> --mode duet
python scripts/fries_planner.py --menu <query-meals结果.json> --mode share --size large
```

未指定规格的普通短句默认按 `auto` 处理：优先中薯、再大薯、小薯，最后接受菜单里的未知规格名称（例如菜单只写“薯条”但详情为“中薯条”）。这样不会把“来三份薯条”误判成规格缺失。

将输出中的商品编码和数量映射到 `calculate-price` 当前工具 schema。`ready_for_official_price` 仅表示本地候选已确定，不表示价格已核实，也不表示订单已创建。`needs_clarification` 表示必须由用户消除歧义。

菜单原始数据与返回字段可能随服务端演进。解析失败时读取 `references/data-contract.md`，保留原始响应并检查字段，不得编造商品编码。

## 使用只读 MCP 联调客户端

开发调试可运行 `scripts/mcp_client.py`。Token 只从环境变量 `MCD_MCP_TOKEN` 读取；客户端显式拒绝所有写工具。

```bash
python scripts/mcp_client.py list-tools
python scripts/mcp_client.py call --tool query-meals --args-file <参数.json>
```

先查看 `list-tools` 返回的实时 schema，再构造参数文件。不要把 Token 写入命令行、参数文件或版本库。

### 端到端只读冒烟测试

配置好 `MCD_MCP_TOKEN` 后，运行只读冒烟测试，验证从时间、门店、菜单、详情到官方算价的完整链路（不会创建订单）：

```bash
python scripts/smoke_test.py
```

可通过 `MCD_CITY`、`MCD_KEYWORD`、`MCD_QUANTITY`、`MCD_STORE_CODE`、`MCD_REPORT` 环境变量覆盖默认参数。冒烟测试绝不调用 `create-order`。

## 薯条人格分享卡

官方算价成功后，可把订单摘要归一化为 JSON，并生成一张离线 HTML 分享卡：

```bash
python scripts/make_share_card.py --summary <摘要.json> --output <分享卡.html>
```

摘要至少包含 `store`、`order_type`、`items`、`original_price_yuan`、`discount_yuan`、`total_yuan`、`price_verified_at`、`created_order`。金额必须来自 `calculate-price` 返回值除以 100，不得使用菜单原始价或估算值。

卡片自动生成“独奏家 / 二重奏指挥 / 多重奏作曲家 / 薯条乐团团长”人格和一句乐评。可选主题为 `concert`、`midnight`、`picnic`。未创建订单时必须保持 `created_order=false`，卡片会显示“价格确认卡 · 尚未下单”。示例见 `examples/share-card.sample.html`。

## 异常处理

- 401：提示 Token 无效、过期或未配置，停止调用并引导重新配置。
- 429：停止密集请求，降低频率后由用户决定是否重试；不并发轰炸接口。
- 菜单为空或商品下架：说明实时结果，提供规格或门店备选，不用旧缓存冒充可售数据。
- 本地解析出现多个风味候选：列出名称与规格，不擅自选择。
- 算价与菜单展示价不一致：以 `calculate-price` 为确认依据，并清楚展示差异。
- 下单结果未知：先查单，再决定是否继续，严禁盲目重复创建。

## 资源

- `scripts/fries_planner.py`：解析快捷指令、筛选实时菜单并生成待算价计划。
- `scripts/mcp_client.py`：仅用于开发联调的只读 Streamable HTTP MCP 客户端。
- `scripts/smoke_test.py`：只读端到端冒烟测试，验证整条链路但不创建订单。
- `scripts/make_share_card.py`：根据官方算价摘要生成“薯条人格”分享卡。
- `examples/share-card.sample.html`：使用演示数据的分享卡样例。
- `references/data-contract.md`：菜单归一化、输出状态和字段映射约定。
- `tests/`：离线单元测试与模拟 MCP 服务测试；测试数据不代表实时菜单或价格。
