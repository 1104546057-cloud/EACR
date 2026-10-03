# EACR v0.2：经验演化信念空间主动恢复

## 1. 论文定位

**英文题目：** EACR: Experience-Evolving Belief-Space Active Recovery for Mobile Robot Navigation

**中文题目：** EACR：面向移动机器人导航故障的经验演化信念空间主动恢复方法

本文研究导航故障根因不可直接观测、恢复动作结果存在不确定性时的主动恢复问题。系统不把历史经验仅作为检索结果，而是将其建模为 intervention–outcome experience model，并让该模型直接参与下一步干预决策。经验经过环境反馈持续更新；经验模型的变化必须能够改变后续 intervention policy。

本文第一阶段不把 MiniLLM 蒸馏作为主体贡献，也不宣称已经完成完整的因果识别。Strong LLM 负责开放集故障假设和候选干预生成，EACR 负责 belief 更新、风险约束、动作排序和最终执行。

## 2. 核心科学问题

在部分可观测的导航故障下，如何利用持续积累的干预—结果经验，更新故障 belief 和干预结果预测，并主动选择兼顾诊断价值、恢复收益、干预成本与安全约束的下一步动作？

核心可检验命题是：

> 经验积累不仅提高经验检索质量，而且会改变相同 fault belief 下的干预排序，并由此减少无效探测、降低恢复成本和缩短恢复时间。

## 3. 问题形式化

### 3.1 状态、证据与故障假设

设导航系统的潜在故障根因为：

```text
H = {h_1, h_2, ..., h_K}
```

系统无法直接观测真实根因，只能获得多源证据：

```text
e_t = {log_t, scan_t, odom_t, pose_t, tf_t, costmap_t, planner_t, controller_t}
```

上下文定义为：

```text
c_t = {map, robot_state, task, environment, software_config}
```

系统维护故障 belief：

```text
b_t(h) = P(h | e_1:t, c_1:t)
```

### 3.2 干预动作

候选动作集合记为 `A_t^cand`，安全动作集合记为 `A_safe(c_t)`。动作可以包括：

- 采集或检查某类诊断证据；
- 清理局部或全局 costmap；
- 小范围、边界内参数扰动；
- 重定位或重发目标；
- 降低速度或限制角速度；
- 重启指定节点；
- 执行受控的短时恢复测试。

实际动作必须满足：

```text
a_t ∈ A_safe(c_t)
Risk(a_t, c_t) ≤ ε
```

安全集合由人工规则、系统约束和动作前置条件共同定义。Strong LLM 不得绕过安全投影直接执行动作。

### 3.3 反馈、收益与成本

执行动作后获得反馈：

```text
o_{t+1} = {new evidence, execution status, navigation status, stability window}
```

定义恢复收益 `ΔR_t`、干预成本 `C_t` 和安全风险 `Risk_t`。恢复状态分为：

1. `diagnosis_correct`：根因判断正确；
2. `recovery_success`：导航功能恢复；
3. `sustained_recovery`：在预设稳定窗口内持续正常。

只有达到预先规定的验证标准，轨迹才可进入 verified experience buffer。

## 4. Experience-Evolving Intervention Model

### 4.1 经验记录

在线记录不要求知道真实根因，不把未知的 `h_i` 当作事实。单条经验定义为：

```json
{
  "context": "c_i",
  "evidence_before": "e_i",
  "belief_before": "b_i",
  "candidate_action": "a_i",
  "observed_outcome": "o_i",
  "recovery_gain": "delta_R_i",
  "intervention_cost": "C_i",
  "risk_observed": "risk_i",
  "verification_status": "verified_success | verified_failure | inconclusive",
  "confidence": 0.0,
  "source": "simulation | robot | replay",
  "timestamp": "..."
}
```

真实故障标签只用于仿真评估、离线监督或误差分析，不作为在线 belief 的直接输入。

### 4.2 结果模型

经验模型 `M_t` 预测动作在当前 belief 和上下文下的可能结果：

```text
P(o, ΔR, C | b_t, c_t, a, M_t)
```

第一版可以采用分层模型：

```text
P(o | b_t, c_t, a, M_t)
P(ΔR | o, b_t, c_t, a, M_t)
P(C | c_t, a, M_t)
```

模型不要求第一版完成严格的结构因果识别。论文中使用 `intervention-outcome prediction` 和 `intervention-verified recovery`，并明确历史动作选择可能造成混杂。

### 4.3 在线更新

执行动作并完成反馈后：

```text
M_{t+1} = Update(M_t, m_{t+1})
```

更新可以采用带上下文的 Beta/Dirichlet 统计模型、分组回归模型或贝叶斯后验更新。第一版优先使用可解释、可复现实验的分组统计模型，避免模型复杂度掩盖经验演化效果。

## 5. Fault belief 更新

动作产生新观测后，使用结果模型计算似然：

```text
b_{t+1}(h) ∝ P(o_{t+1} | h, b_t, c_t, a_t, M_t) · b_t(h)
```

如果某类证据只支持“动作是否有效”，而不直接支持具体根因，可以先更新结果状态，再通过故障—结果映射更新 belief。每次更新必须保留：

- 更新前 belief；
- 观测结果；
- 更新后 belief；
- belief 校准误差。

## 6. Strong LLM 接口

Strong LLM 只负责开放集候选生成，不直接决定执行动作。

### 输入

```text
{e_t, c_t, b_t, recent_trajectory, available_tools, safety_spec}
```

### 输出

```json
{
  "hypotheses": [
    {"id": "H1", "description": "localization drift", "supporting_evidence": []}
  ],
  "candidate_interventions": [
    {
      "id": "a1",
      "description": "inspect localization consistency",
      "required_evidence": [],
      "preconditions": [],
      "expected_observable": []
    }
  ],
  "abstain": false,
  "uncertainty_note": "..."
}
```

LLM 输出的假设和动作必须经过：

1. schema 校验；
2. 动作白名单匹配；
3. 前置条件检查；
4. 安全投影；
5. 去重和动作可执行性检查。

LLM 不提供最终动作概率。其作用通过“开放集候选覆盖率”和“候选质量”评估，而不是通过最终恢复率单独归因。

## 7. EACR 主动干预选择

对每个安全候选动作定义：

```text
J_t(a) = α IG_t(a)
       + β E[ΔR_t(a)]
       - γ C_t(a)
       - η U_M(a)
```

其中：

- `IG_t(a)`：动作对 fault belief 的期望信息增益；
- `E[ΔR_t(a)]`：预期恢复收益；
- `C_t(a)`：时间、资源和系统扰动成本；
- `U_M(a)`：经验模型在当前上下文中的预测不确定性。

动作选择为：

```text
a_t* = argmax_{a ∈ A_safe(c_t)} J_t(a)
```

同时满足：

```text
Risk(a_t*, c_t) ≤ ε
```

停止条件包括：

- 最大 belief 超过诊断阈值且恢复已验证；
- 达到 sustained recovery；
- 预算耗尽；
- 所有安全候选动作的预期收益低于阈值；
- 当前状态应升级给 Strong LLM 或人工处理。

## 8. EACR 主循环伪代码

```text
Input: initial evidence e_0, context c_0, experience model M_0
Output: recovery result and updated model M_T

1. b_0 ← InitializeBelief(e_0, c_0)
2. for t = 0 ... T-1:
3.     if NeedOpenSetExpansion(b_t, M_t):
4.         LLM_output ← StrongLLM(e_t, c_t, b_t, trajectory_t)
5.         A_cand ← ValidateAndProject(LLM_output, safety_spec)
6.     else:
7.         A_cand ← RetrieveKnownActions(b_t, M_t)
8.
9.     A_safe ← ApplyPreconditionsAndRiskFilter(A_cand, c_t)
10.    if A_safe is empty:
11.        return Escalate("no safe intervention")
12.
13.    for a in A_safe:
14.        score[a] ← IG(a) + recovery_utility(a)
15.                     - intervention_cost(a) - model_uncertainty(a)
16.    a_star ← argmax(score)
17.    o_next ← ExecuteAndObserve(a_star)
18.    b_next ← BayesianBeliefUpdate(b_t, o_next, a_star, M_t)
19.    m_next ← BuildExperience(b_t, a_star, o_next, verification_result)
20.    M_{t+1} ← UpdateExperienceModel(M_t, m_next)
21.
22.    if SustainedRecovery(o_next, b_next):
23.        return VerifiedSuccess(b_next, M_{t+1})
24.    if ShouldAbstain(b_next, M_{t+1}):
25.        return Escalate("insufficient confidence")
26.    e_t ← o_next.evidence
27.    b_t ← b_next
```

## 9. 主要实验假设

### H1：经验演化改变策略

在相同 fault belief、相同上下文和相同候选动作集合下：

```text
π(a | b, M_0) ≠ π(a | b, M_20) ≠ π(a | b, M_50)
```

需要报告动作排名变化、动作概率变化和策略 KL divergence。

### H2：经验演化改善结果预测

随着 verified experience 增加：

- outcome prediction NLL 下降；
- Brier score 下降；
- calibration ECE 下降；
- action outcome ranking accuracy 提高。

### H3：策略改善降低恢复代价

随着经验增加：

- 无效干预次数下降；
- 平均干预成本下降；
- MTTR 下降；
- recovery success 和 sustained recovery 提高。

### H4：Strong LLM 提高开放集覆盖

Strong LLM 候选生成只应主要改善未知故障和组合故障的候选覆盖，不应替代 EACR 的安全决策和动作排序。

## 10. 实验版本与消融

### 主比较

1. Rule-based recovery；
2. Bayesian diagnosis + fixed recovery；
3. IG active diagnosis without experience model；
4. EACR-Static：使用历史模型但不在线更新；
5. EACR-Evolving：经验更新并改变动作选择；
6. EACR + Strong LLM：加入开放集候选生成。

### 消融

- w/o Memory Update；
- w/o IG；
- w/o Recovery Utility；
- w/o Risk Constraint；
- w/o Belief Update；
- w/o Model Uncertainty；
- Fixed candidate set vs Strong LLM candidate set。

### 关键控制实验

固定：

- fault belief；
- context；
- candidate action set；
- random seed；
- evaluation fault sequence。

只改变 `M_t` 的经验量，比较 action ranking 和最终恢复结果。该实验直接检验“经验模型改变策略”的核心主张。

## 11. 评价指标

### 诊断

- Root Cause Accuracy；
- Top-k Recall；
- ECE、Brier、NLL；
- belief convergence steps。

### 恢复

- Recovery Success Rate；
- Sustained Recovery Rate；
- MTTR；
- 平均干预次数；
- Cumulative Intervention Cost；
- Risk Violations。

### 经验演化

- outcome prediction NLL 随经验量的变化；
- action ranking stability/change；
- policy KL divergence；
- useless probe rate；
- experience-to-policy improvement curve。

### Strong LLM

- open-set hypothesis recall；
- valid candidate rate；
- unsafe candidate rejection rate；
- candidate coverage；
- escalation rate；
- token cost 和 latency。

## 12. 论文贡献边界

本文可以主张：

1. 提出一种将 intervention–outcome 经验直接纳入 belief-space 主动恢复决策的 EACR 机制；
2. 提出同时考虑信息增益、恢复收益、干预成本、模型不确定性和硬安全约束的动作选择目标；
3. 通过时间顺序实验验证经验积累改变了 intervention policy，并改善恢复效率；
4. 将 Strong LLM 限定为开放集假设和候选动作生成器，由 EACR 完成最终决策。

本文暂不主张：

- 已完成一般意义上的因果识别；
- 首次提出机器人故障恢复、经验记忆或环境验证；
- MiniLLM 蒸馏本身构成主要算法创新。

## 13. EACR-D 扩展

EACR-D 在 EACR 成立后加入 Environment-Verified Distillation：

```text
Strong LLM exploration
        ↓
EACR intervention selection
        ↓
environment verification
        ↓
verified trajectory buffer
        ↓
MiniLLM SFT / LoRA
        ↓
known-fault local handling
        ↓
low confidence or OOD → Strong LLM escalation
```

EACR-D 的新增评价指标包括：

- MiniLLM accuracy 和 calibration；
- Strong LLM escalation rate；
- local inference latency；
- API/token cost；
- continual learning 后的旧故障保持率；
- OOD abstention precision。

## 14. 最小可行实现顺序

1. 固定 4 类故障和 8–12 个安全动作；
2. 实现 fault belief estimator；
3. 实现可解释的 intervention–outcome 统计模型；
4. 实现 EACR 动作选择器和硬风险过滤；
5. 完成 EACR-Static 与 EACR-Evolving 对比；
6. 画出 experience-to-policy improvement curve；
7. 加入 Strong LLM 开放集候选生成；
8. 最后再实现 EACR-D verified distillation。

