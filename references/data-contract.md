# 数据约定

## 原则

- `query-meals` 是唯一菜单事实来源；样例数据只用于离线测试。
- 本地规划器不发起网络请求，不调用任何 MCP 写工具。
- 商品编码和价格字段按实时响应提取，不在代码中保存生产编码。
- `menu_price_raw` 只保留菜单原始值，不推断币种、单位或最终应付金额。
- 最终确认价格只能来自 `calculate-price`。

## 菜单识别

规划器递归读取 JSON、JSON 数组以及 MCP `content[].text` 中嵌入的 JSON 文本。支持以下常见字段别名：

| 含义 | 字段 |
|---|---|
| 商品名 | `mealName`、`productName`、`itemName`、`skuName`、`displayName`、`name`、`title` |
| 商品编码 | `mealCode`、`productCode`、`itemCode`、`skuCode`、`code`、`id` |
| 菜单原价字段 | `price`、`salePrice`、`currentPrice`、`mealPrice`、`sellPrice`、`amount` |

仅有分类 `id` 和分类名、没有价格或明确商品编码字段的对象不会被当作商品。当服务端使用 `data.meals` 这类映射表，且商品编码是 JSON 对象键而不是对象内部字段时，规划器会把该键作为商品编码；对象仍必须同时提供商品名和价格或明确商品编码字段，避免把分类误判成商品。`available=false`、`sellable=false`、`soldOut=true`、零库存和明确下架状态会被排除。MCP 可能把 JSON 嵌入说明文本；规划器会尝试解析文本中的 JSON 对象或数组。

匹配独立薯条商品时排除套餐、汉堡、薯饼及其他组合餐。若服务端使用新的命名或字段导致零匹配，应检查原始响应并扩充解析规则，不得将零匹配解释为门店一定没有薯条。

## 快捷预设

| 模式 | 份数 | 默认规格 |
|---|---:|---|
| `solo` / 独奏 | 1 | 中薯 |
| `duet` / 二重奏 | 2 | 中薯 |
| `share` / 分享装 / 多重奏 | 4 | 中薯 |

自定义文本和命令行参数可覆盖份数、规格及风味。份数限制为 1 至 20；更大的需求应拆分并人工核对。

## 输出状态

### `ready_for_official_price`

表示候选商品和份数已确定。输出包括：

```json
{
  "status": "ready_for_official_price",
  "items": [
    {
      "code": "DEMO-CODE",
      "name": "薯条（中）",
      "quantity": 2
    }
  ],
  "official_price_verified": false,
  "order_created": false
}
```

`DEMO-CODE` 只是结构示例，不是生产商品编码。调用方仍需按 `calculate-price` 的实时 schema 映射字段。

### `needs_clarification`

表示风味、规格或商品编码存在歧义。读取 `candidates`，向用户展示少量可区分选项，得到答复后再继续。

### `no_fries_found`

表示当前解析规则未找到可售候选。检查门店、时段、供应状态和响应字段；不要声称接口返回空菜单，除非原始响应确实为空。

## 分享卡摘要约定

分享卡输入为归一化 JSON，最小字段如下：

```json
{
  "store": "门店名称",
  "order_type": "到店自取",
  "take_way": "外带",
  "items": [{"name": "中薯条", "quantity": 3}],
  "original_price_yuan": 43.5,
  "discount_yuan": 1.0,
  "total_yuan": 42.5,
  "price_verified_at": "2026-10-24 12:54",
  "created_order": false
}
```

`total_yuan`、`original_price_yuan` 和 `discount_yuan` 必须由 `calculate-price` 返回的分值除以 100 得到。`created_order=false` 时卡片显示“价格确认卡 · 尚未下单”；只有实际创建订单后才能设为 `true`。摘要不得包含支付链接、手机号、收货地址、Token 或账户标识。

## 历史档案约定

历史文件默认位于 `~/.fries-ensemble/history.json`，可通过 `FRIES_HISTORY_PATH` 覆盖。结构如下：

```json
{
  "version": 1,
  "records": [
    {
      "id": "本地随机标识",
      "date": "2026-10-24",
      "recorded_at": "2026-10-24T12:54:00+08:00",
      "quantity": 3,
      "items": [{"name": "中薯条", "quantity": 3}],
      "source": "order",
      "store": "门店名称",
      "total_yuan": 42.5
    }
  ]
}
```

记录只允许 `source=order|manual`，`quantity` 为 1 至 100，商品份数之和必须等于 `quantity`。`store` 只保存门店名称，`note` 最多 80 字。禁止写入订单号、支付链接、手机号、详细地址、Token 或账户标识。累计份数决定称号，阈值见 `scripts/fries_history.py` 的 `MILESTONES`。

## 写操作边界

规划器与只读联调客户端都不会调用 `create-order`。在 WorkBuddy 中执行真实下单时，必须先展示当前门店、就餐方式、商品、数量和官方总价，再获得明确确认。任何价格或商品变化都会使旧确认失效。

## 实测结构要点

2026-10-24 的真实接口验证显示：

- 到店自取使用 `query-nearby-stores` 的 `beType=1` 与 `searchType=2`，返回 `storeCode`；`beType=1` 不传 `beCode`。
- `query-meals` 需要 `storeCode`、`orderType=1`、`beType=1`。它可能把商品详情放在 `data.meals` 映射表中，键为商品编码，同时 `data.categories[].meals[]` 只含 `code` 与标签。
- 菜单中的商品名可能省略规格。例如菜单显示“薯条”，而 `query-meal-detail` 与 `calculate-price` 返回“中薯条”。规划器不把未知规格冒充指定规格；未指定规格时可使用 `--size auto`，指定“大薯”但候选缺失时必须向用户澄清。
- `calculate-price` 的返回金额单位是分。展示时除以 100 并保留两位小数；`data.takeWayList` 会给出到店下单需要携带的取餐方式编码。
