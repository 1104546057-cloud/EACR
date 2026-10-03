# EACR v0.3：算法规格书

## 1. 目标与边界

EACR 解决部分可观测导航故障下的顺序主动恢复问题。系统维护故障 belief，利用历史干预—结果反馈更新经验模型，并在安全动作集合中选择下一步干预。

本版本采用可解释的 Beta-Bernoulli / Dirichlet 统计模型，不引入神经网络预测器、强化学习策略或 MiniLLM 蒸馏。Strong LLM 只负责开放集故障假设和候选动作生成，不负责最终动作选择。

核心闭环：

```text
b_t → M_t → action scoring → a_t → o_{t+1} → b_{t+1}, M_{t+1}
```

## 2. 状态变量

### 2.1 故障集合

```text
H = {h_1, ..., h_K}
```

第一版仿真至少包含四类故障族：

- localization；
- costmap；
- planner；
- sensor / TF / control。

每个故障族可以包含多个具体故障。真实根因 `h*` 只在仿真评估时可见，在线决策不得直接读取。

### 2.2 上下文

```text
c_t = (map_id, task_id, robot_state, environment_bin, software_state)
```

上下文用于经验分组。第一版不把连续变量直接全部输入模型，而是进行可解释离散化，例如：

```text
environment_bin ∈ {open, corridor, cluttered}
robot_state ∈ {stationary, moving, degraded}
```

### 2.3 证据与 belief

```text
e_t = {logs, scan_features, odom_features, pose_features,
       tf_status, costmap_status, planner_status, controller_status}
```

```text
b_t(h) = P(h | e_{0:t}, c_{0:t})
```

### 2.4 动作

```text
A_t^cand = LLM 候选动作 ∪ 已知动作库
A_safe(c_t) ⊆ A_t^cand
```

动作经过白名单、前置条件和风险过滤后，只有 `A_safe(c_t)` 中的动作可以被选择。

## 3. Belief 初始化与更新

### 3.1 初始化

没有历史证据时，使用先验：

```text
b_0(h) = P(h | c_0)
```

第一版可以使用均匀先验：

```text
b_0(h) = 1 / |H|
```

如果训练集提供了不同故障的基准频率，可以使用故障频率先验，但测试集不得使用测试故障标签修正先验。

### 3.2 观测似然

经验模型为每个故障—动作—上下文组合提供观测结果分布：

```text
L_t(h, a, o) = P(o | h, c_t, a, M_t)
```

这里的 likelihood 不再包含 `b_t`。`b_t` 只作为 Bayesian prior。

### 3.3 标准 Bayesian 更新

动作 `a_t` 执行后得到观测 `o_{t+1}`：

```text
b_{t+1}(h) =
    [L_t(h, a_t, o_{t+1}) · b_t(h)]
    /
    [Σ_{h'} L_t(h', a_t, o_{t+1}) · b_t(h')]
```

若观测为多个条件独立证据，可使用：

```text
L_t(h, a, o) = Π_j P(o_j | h, c_t, a, M_t)
```

第一版应记录每次更新前后的 belief，并计算 belief entropy：

```text
H(b_t) = -Σ_h b_t(h) log b_t(h)
```

## 4. Experience Model

### 4.1 结果变量

将每次动作结果离散为有限结果类别：

```text
O = {diagnostic_support, diagnostic_conflict,
     recovery_success, recovery_failure,
     unsafe_or_blocked, inconclusive}
```

恢复收益使用单独变量：

```text
Y_rec ∈ {0, 1}
```

持续恢复使用验证窗口 `W` 判断：

```text
Y_sustain ∈ {0, 1}
```

### 4.2 Beta-Bernoulli 恢复模型

对每个 `(h, context_bin, action)` 维护成功概率后验：

```text
p_rec(h, c, a) ~ Beta(α_rec(h,c,a), β_rec(h,c,a))
```

初始无信息先验：

```text
α_rec = 1, β_rec = 1
```

观察到恢复成功：

```text
α_rec ← α_rec + 1
```

观察到恢复失败：

```text
β_rec ← β_rec + 1
```

后验均值：

```text
E[p_rec] = α_rec / (α_rec + β_rec)
```

后验方差作为经验不确定性：

```text
Var[p_rec] =
  α_rec β_rec /
  [(α_rec + β_rec)^2 (α_rec + β_rec + 1)]
```

### 4.3 Dirichlet 结果模型

对每个 `(h, context_bin, action)` 维护结果类别分布：

```text
θ(h,c,a) ~ Dirichlet(α_o(h,c,a,1), ..., α_o(h,c,a,|O|))
```

观察到结果类别 `o_j` 后：

```text
α_o(h,c,a,j) ← α_o(h,c,a,j) + 1
```

结果概率后验均值：

```text
E[P(o_j | h,c,a)] = α_o,j / Σ_k α_o,k
```

### 4.4 从 belief 到结果预测

在线时真实 `h` 未知，因此按当前 belief 混合各故障模型：

```text
P(o | b_t,c_t,a,M_t)
  = Σ_h b_t(h) · E[P(o | h,c_t,a,M_t)]
```

恢复成功概率同样为：

```text
P(Y_rec=1 | b_t,c_t,a,M_t)
  = Σ_h b_t(h) · E[p_rec(h,c_t,a)]
```

### 4.5 经验更新

执行动作后构造：

```text
m_t = (b_t, c_t, a_t, o_{t+1}, Y_rec, Y_sustain,
       cost_t, risk_t, verification_status)
```

使用 `m_t` 更新对应的 Beta 和 Dirichlet 参数：

```text
M_{t+1} = Update(M_t, m_t)
```

若反馈为 `inconclusive`，不直接记为失败；可以只更新结果分布，不更新恢复成功的 Beta 计数。

## 5. Information Gain

### 5.1 预测观测分布

```text
P(o | b_t,c_t,a,M_t)
  = Σ_h b_t(h) P(o | h,c_t,a,M_t)
```

### 5.2 观测后的预测 belief

对每个可能结果 `o`：

```text
b_{t+1}^{(o)}(h) =
  [P(o | h,c_t,a,M_t) b_t(h)]
  /
  [Σ_{h'} P(o | h',c_t,a,M_t)b_t(h')]
```

### 5.3 期望信息增益

```text
IG_t(a) = H(b_t)
  - Σ_o P(o | b_t,c_t,a,M_t) H(b_{t+1}^{(o)})
```

其中：

```text
H(b) = -Σ_h b(h) log b(h)
```

`IG_t(a)` 表示执行动作后预计减少多少根因不确定性。结果类别有限时，求和可以直接计算；连续观测可以先离散化或使用 Monte Carlo 近似。

## 6. 恢复收益、成本与不确定性

### 6.1 预期恢复收益

```text
E[ΔR_t(a)] =
  w_rec · P(Y_rec=1 | b_t,c_t,a,M_t)
  + w_sustain · P(Y_sustain=1 | b_t,c_t,a,M_t)
```

第一版可以只使用恢复成功项，待持续恢复验证稳定后再加入 `w_sustain`。

### 6.2 干预成本

```text
C_t(a) =
  w_time · expected_time(a)
  + w_compute · expected_compute(a)
  + w_disturbance · expected_disturbance(a)
```

所有成本项必须在实验开始前固定定义，不能根据测试结果临时调权重。

### 6.3 经验模型不确定性

第一版使用恢复概率后验方差：

```text
U_M(a) = Σ_h b_t(h) Var[p_rec(h,c_t,a)]
```

也可以将 Dirichlet 结果分布的熵加入不确定性项，但必须在所有 baseline 中使用同一计算方式。

## 7. 主动动作选择

目标函数：

```text
J_t(a) = α IG_t(a)
       + β E[ΔR_t(a)]
       - γ C_t(a)
       - η U_M(a)
```

安全过滤在优化前执行：

```text
A_safe(c_t) = {
  a ∈ A_t^cand : Preconditions(a,c_t)=true
                  and Risk(a,c_t) ≤ ε
}
```

最终动作：

```text
a_t* = argmax_{a ∈ A_safe(c_t)} J_t(a)
```

若 `A_safe(c_t)` 为空，系统必须 abstain 或升级，不得从危险动作中强行选择一个。

## 8. 完整算法伪代码

```text
Algorithm EACR

Input:
    initial evidence e_0
    context c_0
    fault set H
    safe action specification S
    prior model M_0
    risk threshold ε

1.  b_0 ← InitializeBelief(e_0, c_0)
2.  t ← 0

3.  while t < T_max:
4.      if OpenSetCondition(b_t, M_t, e_t):
5.          q_t ← StrongLLM(e_t, c_t, b_t, S)
6.          A_raw ← q_t.candidate_interventions ∪ KnownActionLibrary
7.      else:
8.          A_raw ← RetrieveKnownActions(b_t, M_t)

9.      A_safe ← FilterBySchemaPreconditionsAndRisk(A_raw, c_t, ε)
10.     if A_safe = ∅:
11.         return AbstainOrEscalate(reason="no safe action")

12.     for each a in A_safe:
13.         P_o[a] ← PredictOutcomeDistribution(b_t,c_t,a,M_t)
14.         IG[a] ← ExpectedInformationGain(b_t,P_o[a])
15.         R[a] ← ExpectedRecoveryGain(b_t,c_t,a,M_t)
16.         C[a] ← InterventionCost(a,c_t)
17.         U[a] ← ExperienceUncertainty(b_t,c_t,a,M_t)
18.         J[a] ← α·IG[a] + β·R[a] - γ·C[a] - η·U[a]

19.     a_t ← argmax_a J[a]
20.     o_{t+1}, status_t ← ExecuteAndObserve(a_t)
21.     verification_t ← VerifyOutcome(o_{t+1}, status_t, W)

22.     b_{t+1} ← BayesianUpdate(b_t, o_{t+1}, c_t, a_t, M_t)
23.     m_t ← BuildExperience(b_t,c_t,a_t,o_{t+1},verification_t)
24.     M_{t+1} ← UpdateBetaDirichlet(M_t,m_t)

25.     if verification_t = sustained_recovery:
26.         return VerifiedSuccess(b_{t+1}, M_{t+1})
27.     if StopCondition(b_{t+1}, M_{t+1}, t):
28.         return AbstainOrEscalate(reason="insufficient confidence")

29.     e_t ← o_{t+1}.evidence
30.     c_t ← UpdateContext(o_{t+1})
31.     b_t ← b_{t+1}
32.     M_t ← M_{t+1}
33.     t ← t + 1
```

## 9. 经验演化实验协议

### 9.1 策略变化实验

固定：

- fault belief `b`；
- context `c`；
- candidate action set；
- action costs；
- random seed。

仅替换经验量：

```text
M_0, M_20, M_50
```

记录每个动作的：

- `J(a)`；
- normalized action probability；
- action rank；
- posterior mean；
- posterior variance。

指标包括：

```text
policy KL(M_i || M_j)
rank correlation
top-1 action change rate
```

### 9.2 过时经验与分布迁移实验

训练阶段让旧环境中某动作有效：

```text
P_old(success | a_B, c_old) = 0.9
```

测试阶段切换到新环境：

```text
P_new(success | a_B, c_new) = 0.3
```

要求记录：

1. 初始旧经验导致的动作偏好；
2. 前几轮错误选择；
3. 新反馈进入后的 Beta posterior；
4. posterior variance 变化；
5. action ranking 改变；
6. 恢复性能重新上升所需的交互次数。

该实验验证 EACR 不仅积累经验，也能在环境变化后修正过时经验。

### 9.3 必须避免的数据泄漏

- 测试环境的成功率不得用于初始化 `M_0`；
- 未来时间段反馈不得提前进入当前模型；
- 同一故障实例的连续轨迹不得同时作为训练和独立测试；
- baseline 与 EACR 必须使用相同故障序列、随机种子和动作安全边界。

## 10. 第一版实现顺序

1. 实现故障注入和安全动作执行器；
2. 实现均匀 belief 初始化；
3. 实现离散结果类别与标准 Bayesian update；
4. 实现 Beta-Bernoulli 恢复模型；
5. 实现 Dirichlet outcome model；
6. 实现 IG、恢复收益、成本和不确定性计算；
7. 实现 EACR-Static / EACR-Evolving；
8. 完成策略变化和过时经验纠正实验；
9. 再接入 Strong LLM 开放集候选生成。

