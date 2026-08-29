---
description: Evaluate an LLM-based multi-agent simulation project in this repo (e.g. playgrounds/mbti-werewolf/) against the singulab-official hackathon rubric. Reads source code and README.md, then writes a scored Markdown report to docs/evaluations/. Runs scoring up to 3 times and averages the results to reduce evaluation variance.
---

# evaluate-hackathon-submission

> 出典: このスキルは [ryukih/2026-05-14-SD-Hackathon-Reviewer](https://github.com/ryukih/2026-05-14-SD-Hackathon-Reviewer)
> （フォーク: [singulab-official/2026-05-14-SD-Hackathon-Reviewer](https://github.com/singulab-official/2026-05-14-SD-Hackathon-Reviewer)）
> の `.claude/skills/evaluate-submission/SKILL.md` を、この `hackathon-test` リポジトリの
> ディレクトリ構造（`submissions/<name>/` ではなく `playgrounds/<name>/`、
> `evaluations/` ではなく `docs/evaluations/`）に合わせて移植したもの。
> ルーブリック本文・プロトコルは原文のまま。最初の実施例: `docs/evaluations/20260823_mbti-werewolf_eval.md`。

You are a hackathon judge evaluating an LLM-based multi-agent simulation project.

## Input

The user will provide a target directory name (e.g. `mbti-werewolf`). The project files are located at:
`playgrounds/<target_name>/`

If no target name is given, ask the user for it. If there is only one project under `playgrounds/`, you may assume that one and confirm with the user before proceeding.

## Your Task

Execute the multi-run evaluation protocol below, then write a Markdown report to:
`docs/evaluations/<YYYYMMDD>_<target_name>_eval.md`

(`YYYYMMDD` = today's date. If a report for the same target already exists from a previous date, keep it — do not overwrite — so score history over iterations stays comparable.)

---

## Evaluation Protocol

### Phase 0: Read all files (once only)

Read in this order:
1. `playgrounds/<target_name>/README.md` — understand stated goals, architecture, and scenario
2. Any upper-level docs this repo's own README points to (e.g. `docs/requirements.md`, `docs/design.md`, top-level `CLAUDE.md`) — these often state the project's actual purpose, which may differ from what this rubric assumes (this repo's projects are learning rehearsals, not hackathon submissions optimizing for this rubric)
3. All source code files (`.py`, `.ts`, `.js`, `.yaml`, `.json`, `.toml`, etc.) in the target directory, especially agent/prompt logic, the simulation loop, and memory handling
4. Prompt template files if present (e.g. `agents/prompts/**/*.md`) — these are what the LLM actually sees and are essential evidence

Use the Read tool for each file. If a file is large, focus on the most relevant sections (agent logic, prompts, simulation loop, memory handling).

Before scoring, note:
- What scenario/world is simulated?
- How is LLM used? What information is given to agents vs. what is left to their judgment?
- Are LLM calls actually present in the code?
- Are agents plural and interacting?
- Is memory implemented, and how?
- Is there a simulation loop?
- Does the project's own stated purpose (from its docs) actually aim at what this rubric measures (emergent multi-agent behavior)? If not, say so explicitly in the report — a low score may reflect a mismatch of goals rather than a design failure.

---

### Phase 1: Scoring — Run 1

Score each rubric category independently. Record scores as **Run 1**.

For each category, you MUST cite specific evidence:
- Code: `` `filename.py:line_number` — description ``
- README: `README.md — "quoted text"`

Output format (internal, not written to file yet):
```
Run 1: A=X, B=X, C=X, D=X
```

---

### Phase 2: Scoring — Run 2 (independent)

**Important**: Do NOT refer back to your Run 1 scores. Approach the code and README as if you are reading them for the first time and score each category fresh.

Output format:
```
Run 2: A=X, B=X, C=X, D=X
```

---

### Phase 3: Variance check

Calculate the absolute difference for each category:
```
diff_A = |Run1.A - Run2.A|
diff_B = |Run1.B - Run2.B|
diff_C = |Run1.C - Run2.C|
diff_D = |Run1.D - Run2.D|
```

- If **any** diff ≥ 3 → proceed to Phase 4
- If **all** diffs < 3 → skip to Phase 5 (use 2-run average)

---

### Phase 4: Scoring — Run 3 (only if variance was detected)

Again, do NOT refer back to Run 1 or Run 2 scores. Score each category independently.

Output format:
```
Run 3: A=X, B=X, C=X, D=X
```

---

### Phase 5: Compute final scores and write report

**Final score per category** = average of all runs conducted (2 or 3), rounded to 1 decimal place.

Write the complete Markdown report to `docs/evaluations/<YYYYMMDD>_<target_name>_eval.md` using the format below.

---

## Rubric (40 points total)

### A. 創発設計 (Emergent Design) — /10

**What to evaluate**: The balance between **世界ルールの設計精度 (precision of world rule design)** and **行動の自由度 (degree of freedom in agent behavior)**. The goal is to assess the system's **設計上の創発ポテンシャル (design-level emergence potential)** — not whether emergence was actually observed, but whether the design makes emergent collective behavior structurally possible.

The ideal design:
- Defines world rules with precision: clear constraints, information flow, perception boundaries, physical/social laws of the simulated world
- Delivers only **rules and raw data** to agents (e.g., "occupancy: 0.83, distance to event: 4.2") — NOT behavioral directives (e.g., "you should leave", "warn others")
- Leaves agent **response strategy entirely up to the LLM**: what to communicate, whether to move, how to coordinate
- Creates a tension or pressure in the world that agents must navigate without being told how

**Two-axis scoring framework**:

| Axis | Low (1-3) | Mid (4-6) | High (7-10) |
|------|-----------|-----------|-------------|
| 世界ルールの設計精度 | Vague or missing rules; agents can't meaningfully differ | Some rules defined; partial constraints | Rules are precise, internally consistent, and create meaningful agent decisions |
| 行動の自由度 | Agents are told what to do (scripted behavior) | Some behavioral nudges; partial freedom | Agents receive only data/rules; full strategic freedom |

**Final score** = harmonic balance of the two axes. A system with perfect world rules but scripted agents caps at 5. A system with full agent freedom but no coherent world rules also caps at 5.

Scoring guide:
- **9-10**: Precise, rich world rules + agents receive only raw data → maximum emergence potential
- **7-8**: Good world rules + mostly free agents, with minor behavioral hints; strong emergence potential
- **5-6**: Either world rules are well-defined but agents are somewhat scripted, OR agents are free but world rules are underspecified
- **3-4**: World rules are thin and agents receive significant behavioral instructions; emergence is unlikely by design
- **1-2**: Agents are largely scripted; LLM acts as a text formatter rather than an autonomous reasoner
- **0**: No meaningful agent autonomy or no world rules

---

### B. 世界設定 (World Design) — /10

**What to evaluate**: The originality and depth of the simulated world scenario.

High scores require at least one of:
- **Originality**: A scenario not seen in standard demos; creative or surprising setting
- **Business relevance**: Models a real organizational, market, or strategic problem
- **Social science relevance**: Captures sociological, economic, or behavioral dynamics (e.g., information diffusion, resource allocation, social norms)

Scoring guide:
- **9-10**: Highly original AND/OR directly maps to a meaningful real-world problem with clear analytical value
- **7-8**: Interesting scenario with clear thematic focus; some real-world relevance
- **5-6**: Decent scenario but generic (e.g., basic crowd simulation, simple trading without insight)
- **3-4**: Minimal scenario design; world is a thin wrapper around the agent framework
- **1-2**: No meaningful scenario; agents move in empty or trivial space
- **0**: No discernible scenario

---

### C. 発展性 (Extensibility & Future Potential) — /10

**What to evaluate**: How well the system is designed to grow, and how clearly the authors articulate its potential.

Evaluate from two angles:

**Code extensibility** (5 points weight):
- Is the architecture modular? (agents, world, LLM client separated)
- Can new agent types, locations, or rules be added without rewriting core logic?
- Is configuration externalized (YAML/JSON config)?

**Future vision** (5 points weight):
- Does README describe concrete future directions?
- Are the proposed extensions technically credible and non-trivial?
- Do extensions deepen the research/business value of the scenario?

Scoring guide:
- **9-10**: Modular code + compelling, specific future directions that extend the core insight
- **7-8**: Good modularity or good future vision (not both)
- **5-6**: Some extensibility; future plans are vague or generic ("add more agents")
- **3-4**: Monolithic code; little future planning
- **1-2**: Hard to extend; no future directions
- **0**: Single-file script with no extensibility

---

### D. 技術実装 (Technical Implementation) — /10

**What to evaluate**: Overall technical quality of the LLM integration and agent infrastructure.

Sub-dimensions:
1. **LLM usage** (3 pts): Prompt engineering quality (structured output, context management, temperature/parameter choices), error handling for LLM failures, async/sync choices
2. **Memory design** (3 pts): How agent memory is stored, updated, and used in prompts; is memory meaningful (not just log dump)?
3. **Code quality** (2 pts): Readability, structure, naming, separation of concerns
4. **Simulation correctness** (2 pts): Synchronous step execution, no race conditions in agent updates, reproducibility (seeds, config)

Scoring guide:
- **9-10**: Sophisticated LLM integration + well-designed memory + clean code + correct simulation mechanics
- **7-8**: Strong in most areas with minor gaps
- **5-6**: Functional but rough edges (e.g., no error handling, flat memory, mixed concerns)
- **3-4**: Basic LLM calls without structure; minimal memory; messy code
- **1-2**: LLM barely integrated; code is difficult to follow
- **0**: LLM not meaningfully used

---

## Output Format

Write the following Markdown to `docs/evaluations/<YYYYMMDD>_<target_name>_eval.md`.

For the score table: if only 2 runs were conducted, show "-" in the Run3 column.
For final scores: round to 1 decimal place (e.g., 7.5).

```markdown
# 評価レポート: <target_name>

**評価日**: <today's date>
**実施回数**: 2回 [or 3回（3回目実施理由: <category>で差=<N>）]

---

## スコアサマリー

| カテゴリ      | Run1 | Run2 | Run3 | 最終(平均) |
|-------------|------|------|------|-----------|
| A. 創発設計  |  X   |  X   |  -   |    X.X    |
| B. 世界設定  |  X   |  X   |  -   |    X.X    |
| C. 発展性    |  X   |  X   |  -   |    X.X    |
| D. 技術実装  |  X   |  X   |  -   |    X.X    |
| **合計**    |  X   |  X   |  -   |  **X.X**  |

---

## 評価詳細

### A. 創発設計 — 最終: X.X/10

#### 評価
<2-4 sentences explaining the score based on the two-axis framework>

#### 根拠
- `<file>:<line>` — <what was found>
- `README.md` — "<quoted text>"

---

### B. 世界設定 — 最終: X.X/10

#### 評価
<2-4 sentences>

#### 根拠
- ...

---

### C. 発展性 — 最終: X.X/10

#### コード拡張性
<assessment>

#### 将来展望
<assessment>

#### 根拠
- ...

---

### D. 技術実装 — 最終: X.X/10

#### LLM利用
<assessment>

#### メモリ設計
<assessment>

#### コード品質・シミュレーション正確性
<assessment>

#### 根拠
- ...

---

## 総評

### 優れている点
- <bullet>
- <bullet>

### 改善点・提言
- <bullet>
- <bullet>

### 一言コメント
<1-2 sentences overall impression>
```

After writing the file, confirm to the user:
`評価完了: docs/evaluations/<YYYYMMDD>_<target_name>_eval.md に出力しました。総合スコア: X.X/40（X回実施）`
