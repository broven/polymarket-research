# Feasibility Spike Plan

> 目标: 用 1-2 天验证三个关键假设，判断策略是否可落地。
> 不写生产代码，只写探索性脚本。

## Spike 1: Polymarket API 数据可用性

**验证问题**: 我们能拿到策略所需的全部数据吗？

### 1.1 拉取活跃加密市场列表
- 调 Polymarket API 获取所有 crypto category 市场
- 确认返回字段: market_id, question, end_date, outcome_prices, token_ids
- 按设计分类: barrier_up / barrier_down / terminal_range
- 记录: 当前有多少个活跃加密价格市场？足够形成交易宇宙吗？

### 1.2 费率查询
- 按 token_id 查询 fee_rate_bps
- 确认: 哪些市场 fee-free，哪些 fee-enabled
- 确认: fee curve 市场能否通过 API 获取具体费率

### 1.3 订单簿深度
- 拉取 2-3 个活跃市场的 order book
- 确认: bid-ask spread 大小、深度（放 $500 单子的滑点大约多少）

### 1.4 历史 resolved 数据
- 查询已 resolve 的加密市场
- 确认: 能否获取 resolve 前的历史价格快照（Q→P 校准需要）
- 如果 API 不直接提供: 评估用 Gamma API / Subgraph 等替代方案
- **这是最关键的验证点** — 如果拿不到历史数据，Q→P 校准只能从零开始积累

### 产出
- `notebooks/spike_01_polymarket.ipynb`
- 结论: API 可用性评估表（每项 OK / 需替代方案 / 不可用）

---

## Spike 2: Deribit 期权数据覆盖

**验证问题**: Deribit 的期权数据能否覆盖 Polymarket 目标市场？

### 2.1 期权链结构
- 拉取 BTC 和 ETH 的完整期权链
- 记录: 可用到期日列表、每个到期日的 strike 范围和密度
- 确认: 最远到期日是多远？（3个月？6个月？）

### 2.2 与 Polymarket 市场的覆盖匹配
- 拿 Spike 1 中的 Polymarket 市场列表
- 逐一检查: 每个市场的 (target_price, expiry_date) 是否在 Deribit 期权链覆盖内
- 计算覆盖率: X% 的 Polymarket 市场可以被 Deribit 数据覆盖
- 不在覆盖内的市场: 只能用 Model B（jump-diffusion），评估是否值得做

### 2.3 IV Surface 数据质量
- 对一个到期日，构建简单的 IV smile
- 检查: 数据点是否足够密（能否做有意义的插值）
- 检查: 是否有明显的无套利违反（bid > ask of butterfly, calendar spread）
- 评估: Dupire 局部波动率提取是否可行，还是数据太稀疏

### 产出
- `notebooks/spike_02_deribit.ipynb`
- 结论: 覆盖率 + IV 数据质量评估

---

## Spike 3: 端到端试算

**验证问题**: 整个 pipeline 在单个市场上能跑通吗？边际大概有多大？

### 3.1 选择一个目标市场
- 从 Spike 1 中挑一个活跃的 barrier_up 市场（如 "Will BTC reach $X by date Y?"）
- 要求: Deribit 有对应到期的期权数据（Spike 2 确认）

### 3.2 Model B 试算 (jump-diffusion)
- 用 Binance 历史数据估计 jump-diffusion 参数
- 跑 100K 条路径，计算 barrier 触达概率
- 输出: P_model_B ± 置信区间

### 3.3 Model A 试算 (IV surface → barrier probability)
- 从 Deribit 数据构建该到期日的 IV smile
- 尝试: 用 SVI 参数化拟合 → Dupire 局部波动率 → 路径模拟
- 如果 Dupire 数值不稳定: 退回到用 flat IV（ATM vol）做简化 barrier 计算
- 输出: P_model_A (Q-measure) ± 置信区间

### 3.4 对比
- 比较: P_model_A vs P_model_B vs Polymarket 市场价
- 计算 edge_gross 和 edge_net（使用实际查询到的 fee + 实际 order book 估算的滑点）
- 关键问题: 扣除成本后还有正的净边际吗？大概多少？

### 产出
- `notebooks/spike_03_e2e_trial.ipynb`
- 结论: 单个市场的 edge_net 估计 + 可行性判断

---

## Go / No-Go 决策矩阵

| 条件 | Go | Adjust | No-Go |
|------|-----|--------|-------|
| Polymarket 活跃加密价格市场数 | >= 10 | 5-9 (宇宙小但可做) | < 5 |
| 历史 resolved 数据可获取 | 有 API 或替代方案 | 需自行从现在积累 | 完全无法获取 |
| Deribit 期权覆盖率 | >= 60% | 30-60% (部分市场只用 Model B) | < 30% |
| IV surface 数据质量 | 足够做 Dupire | 稀疏但可用 flat IV 替代 | 太差无法使用 |
| 端到端 edge_net | > 3% 扣除成本后 | 1-3% (边际薄但存在) | <= 0% (无 edge) |
| Order book 深度 | $500 单子 slippage < 1% | 1-3% (需优化执行) | > 3% (市场太薄) |

**Go**: 全部绿灯，按 v2.2 设计开始实施
**Adjust**: 有黄灯，调整设计后实施（如只用 Model B、缩小交易宇宙）
**No-Go**: 有红灯，这条策略路径不可行，切换到其他方向

---

## 技术栈 (spike 阶段)

- Python 3.11+
- Jupyter notebooks (探索性分析)
- requests / httpx (API 调用)
- numpy / scipy (数值计算)
- matplotlib (可视化)
- 不需要数据库、不需要框架，纯脚本
