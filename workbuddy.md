# WorkBuddy 开发对话上下文

本文记录“薯条多重奏”在腾讯 WorkBuddy 中的需求、设计调整、实现与验证过程。记录不包含系统提示、隐藏指令、真实 Token、个人账号信息或其他敏感数据。

## 对话记录

### 用户：初始任务

> @scene#18:"Skill 开发" @image#1:679a935a1961d4239838382f5dca1b0e.jpg 帮我完成这项任务

用户提供的活动截图包含以下信息：使用麦当劳 MCP 能力开发 Skill，发布到公开 GitHub 仓库，通过指定 Issue 模板报名；使用 WorkBuddy 开发可参与专项奖励。截图显示活动报名及排名截止时间为 2026 年 10 月 25 日 23:59（北京时间）。

### WorkBuddy：核对规则并确定执行方式

> 我会先核对麦当劳官方活动规则与可用 MCP 能力，再直接做出一个可运行、可公开提交的 Skill；涉及注册 Token、GitHub 发布等需要账号授权的步骤，我会把可自动完成的部分先完成，并明确列出仅剩的人工操作。

随后查阅麦当劳中国官方活动仓库与 MCP Server 指南，确认以下要求：

- 必须真实使用麦当劳 MCP 能力。
- 仓库必须公开，并包含 `README.md`、官方原版 `CONTEST_DECLARATION.md`、`MCP_INTEGRATION.md`、源代码及脱敏配置。
- 参加 WorkBuddy 专项奖励时需要提交 `workbuddy.md`。
- 报名 Issue 需要项目名称、公开仓库地址与项目简介。

### WorkBuddy：初版范围与只读原则

> 已确认官方要求：作品必须真实调用麦当劳 MCP，并在公开仓库中提供项目介绍、参赛声明、MCP 接入说明和脱敏配置；若申请 WorkBuddy 专项奖励，还需保留完整开发对话。接下来我会优先做一个“只读、可验证、不下单”的作品，避免把支付或账户写操作作为演示前提。

最初曾规划主题活动档期查询方向。该方向仅用于前期调研，未生成最终参赛代码。

### 用户：明确实际需求

> 我要做那种可以快速点薯条的功能，叫做薯条多重奏

### WorkBuddy：调整需求与下单边界

> 方向已调整为“薯条多重奏”。核心流程是：用一句话指定份数和规格，实时匹配当前门店菜单，官方算价后展示订单摘要，只有得到明确确认才创建订单；不会自动支付。另提供“独奏 / 二重奏 / 分享装”快捷模式，减少重复输入。

### WorkBuddy：细化快捷体验

> 我会把“快”落实到两层：常用份数用快捷预设，临时需求直接识别“来三份大薯”这类自然语言；同时保留实时菜单与价格校验，避免使用过期商品编码或旧价格。订单创建前会固定出现一次确认摘要。

### WorkBuddy：组件拆分

> 实现时会将“菜单筛选”和“真实下单”分开：本地脚本只负责识别薯条规格、份数与候选项，不能触发任何账户写操作；官方 MCP 负责实时菜单、算价和订单。这样快捷模式也不会绕过价格确认。

## 设计决策

1. 项目中文名采用“薯条多重奏”，Skill 标识采用 `fries-ensemble`。
2. 设置三个快捷预设：独奏 1 份中薯、二重奏 2 份中薯、分享装 4 份中薯。
3. 支持“来三份大薯”“薯条 4 份，小份”等中文短指令。
4. 商品编码、可售状态与价格不硬编码；生产流程必须读取实时 MCP 数据。
5. `calculate-price` 是最终价格依据，本地脚本不计算最终应付金额。
6. `create-order` 只能在展示订单摘要并得到明确确认后调用一次。
7. 下单结果未知时先查单，避免重复创建；支付始终由用户完成。
8. 本地 `mcp_client.py` 仅用于只读联调，白名单之外的工具全部拒绝。
9. 测试使用模拟菜单与本机模拟 MCP 服务，不把模拟结果冒充真实接口记录。

## 实现记录

WorkBuddy 在空工作区中完成以下文件：

- `SKILL.md`：触发条件、快捷流程、异常处理与安全边界。
- `scripts/fries_planner.py`：菜单解析、份数与规格识别、候选消歧。
- `scripts/mcp_client.py`：Streamable HTTP、JSON/SSE、会话管理及只读白名单。
- `tests/test_fries_planner.py`：快捷指令与菜单规划测试。
- `tests/test_mcp_client.py`：协议解析、安全策略与本机模拟服务测试。
- `tests/fixtures/menu.sample.json`：明确标注为演示用途的模拟菜单。
- `references/data-contract.md`：输入、输出与字段映射约定。
- `README.md`：安装、目标用户、使用示例、测试与限制。
- `MCP_INTEGRATION.md`：Server、Tools、调用流程、业务价值与验证边界。
- `mcp-config.example.json`：只含 `${MCD_MCP_TOKEN}` 环境变量占位符。
- `CONTEST_DECLARATION.md`：复制官方声明原文，不作修改。
- `.gitignore`：排除凭证、本地响应、缓存与打包产物。

## 验证记录

2026 年 10 月 24 日，WorkBuddy 使用本机 Python 运行：

```bash
python -m unittest discover -s tests -v
```

测试命令退出码为 0。测试覆盖快捷预设、中文份数、规格与风味匹配、套餐排除、SSE 响应解析、鉴权头传递、会话 ID 及写工具拦截。模拟 MCP 服务只绑定 `127.0.0.1`，不访问真实账户。

## 当前结论

薯条多重奏的核心代码、离线测试与参赛基础文档已由 WorkBuddy 创建。真实麦当劳 MCP 联调、公开 GitHub 发布和 Issue 报名需要相应账号授权；这些步骤的结果应在实际完成后如实追加，不得提前写成成功。

## 真实 MCP 联调追加记录

2026-10-24，用户在对话中提供了麦当劳 MCP Token。WorkBuddy 只在两处使用该 Token：本机 WorkBuddy 自定义连接器配置和一次性进程环境变量；未写入仓库、测试、示例或文档。用户在聊天中发送凭证存在泄露面扩大的风险，建议活动结束后在开放平台轮换 Token。

真实联调完成以下只读调用：

1. `list-tools` 成功获取实时工具 schema。
2. `query-nearby-stores` 以北京公开关键词和 `beType=1`、`searchType=2` 查询到店自取门店，返回门店 `storeCode`。
3. `query-meals` 用演示门店与到店自取参数获取实时菜单；发现薯条详情放在 `data.meals` 映射表中，键为商品编码 `4810`。
4. `query-meal-detail` 核对 `4810`，确认商品名为“中薯条”。
5. 修正 `fries_planner.py` 以支持编码作键的菜单映射和 MCP 文本中的嵌入 JSON，并新增回归测试。
6. 用实时菜单生成“来三份薯条”计划，状态为 `ready_for_official_price`。
7. `calculate-price` 官方算价成功：商品原价 4350 分，优惠 100 分，现价 4250 分，即 42.50 元，商品名为“中薯条”。

未调用 `create-order`，因此未创建订单。演示查询使用公开城市与关键词，未提交私人地址。

## 趣味功能追加记录

2026-10-25，按用户“继续增加更有趣的功能”的要求，WorkBuddy 增加两项能力：

1. **薯条人格与乐评**：按总份数生成“独奏家 / 二重奏指挥 / 多重奏作曲家 / 薯条乐团团长”，并为混合商品补充“多声部”乐评。逻辑是确定性函数，不调用模型，不编造营养或价格数据。
2. **价格确认分享卡**：`scripts/make_share_card.py` 读取归一化订单摘要，生成自包含 HTML。卡片展示门店、取餐方式、商品、官方算价、算价时间和人格乐评；未下单时明确标注“价格确认卡 · 尚未下单”。卡片不包含支付链接、手机号、地址或 Token，也没有任何外链资源。
3. 支持 `concert`、`midnight`、`picnic` 三种主题；提供 `examples/order-summary.sample.json` 与 `examples/share-card.sample.html` 演示。
4. 新增 `tests/test_share_card.py`，覆盖人格映射、金额展示、HTML 转义、外链检查和主题切换。全部测试通过。
5. 安全边界：分享卡只使用官方算价后的归一化数据；未下单与已下单状态严格区分；不会自动发布到社交平台。
6. 2026-10-25 已推送至公开仓库，提交 `3f69cb9 Add fries persona share card`。

## 薯条档案追加记录

2026-10-25，用户要求增加“历史点了多少份薯条”的记录，并按数量展示成就。WorkBuddy 完成：

- 新增 `scripts/fries_history.py`：本地 JSON 历史文件，默认 `~/.fries-ensemble/history.json`，支持 `add`、`summary`、`list`、`path`。
- 成就阈值：1 份初响、10 份小型合奏、25 份薯条常客、50 份多重奏指挥、100 份百薯乐团、200 份薯条传奇、500 份薯条宇宙。
- 订单创建成功后记录日期、份数、商品名、门店名和实付金额；不记录订单号、支付链接、手机号、地址或 Token。
- 生成成就页 HTML：展示累计份数、当前称号、下一成就进度、成就图谱和最近记录；提供 `examples/history.sample.json` 与 `examples/fries-history.sample.html` 演示。
- 新增 `tests/test_fries_history.py`，覆盖空档案、阈值边界、混合商品、日期校验、HTML 转义和外链检查。
- 存档只在本机，不上传；用户可手动补录历史订单。

## GitHub 发布追加记录

2026-10-24，WorkBuddy 通过本机 Git Credential Manager 完成 GitHub 浏览器授权后，创建并推送公开仓库：

- 项目地址：https://github.com/1780820154/fries-ensemble
- 仓库可见性：Public
- 初始提交：`92275e3 Initial commit: fries-ensemble`
- 推送分支：`main -> main`
- 推送内容包括 14 个必需与辅助文件；`artifacts/` 被 `.gitignore` 排除，未上传 Token、实时接口响应或发布脚本。

发布前已再次运行仓库校验。报名 Issue 已按官方格式提交：

- Issue 标题：【参赛申请】薯条多重奏 fries-ensemble
- Issue 地址：https://github.com/M-China/mcd-developer-innovation-challenge/issues/1205
- Issue 状态：open
- 提交时间：2026-10-24
