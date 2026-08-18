# 药剂学科研组图 Skill 使用说明

本项目提供 `assemble-pharmaceutics-figures` Codex Skill，用于药剂学、生物医学及微生物研究中的多面板 Figure 规划、有效内容边界确认、Adobe Illustrator 拼版、双语图注和投稿前 QA。

## 能做什么

- 只读扫描 PNG、JPEG、TIFF、PDF、SVG 和 EPS 素材；
- 根据文件名、尺寸和有限本地特征提出面板顺序建议；
- 要求用户确认 Figure 核心结论及 A/B/C/D 面板映射；
- 按图片有效科研内容而非整张画布尺寸排版；
- 使用 Illustrator 生成可编辑 AI、PDF 和 JSX；
- 输出中英文图注、原图溯源表和 QA 报告。

## 科研完整性规则

- 原图只读，不覆盖、不重命名、不修改源像素；
- 自动判断只是候选，不推断处理组、样本量、统计方法、比例尺或机制；
- 缺失信息保持 `[待确认]` / `[TO CONFIRM]`；
- 不自动裁剪 Western blot，不选择性删除结果；
- 默认完全本地处理，云端视觉识别必须逐张授权；
- `runs/` 中的科研素材和产物不进入 Git。

## 强制确认门

标准流程分为两类批准，不能合并或跳过：

1. 面板科学逻辑确认：确认 Figure 结论及 A/B/C/D 顺序；
2. 有效内容边界确认：逐张检查红框是否保留坐标轴、图例、误差线、显著性标记、比例尺、文字和复合面板内部间距。

只有依次输入 `APPROVE_BOUNDS` 和 `APPROVE` 后，才能调用 Illustrator。

## 命令流程

```powershell
pharmfig scan <图片目录> --run-id Figure1
pharmfig propose .\runs\Figure1\manifest.yaml
pharmfig bounds .\runs\Figure1\manifest.yaml
# 查看 content_bounds_review.png，必要时调整 manifest 中的 normalized 坐标。
pharmfig bounds-approve .\runs\Figure1\manifest.yaml
pharmfig approve .\runs\Figure1\manifest.yaml
pharmfig assemble .\runs\Figure1\manifest.yaml --run-illustrator
pharmfig caption .\runs\Figure1\manifest.yaml --bilingual
pharmfig qa .\runs\Figure1\manifest.yaml
```

## 有效内容边界

每个面板在 manifest 中记录：

```yaml
content_bounds:
  mode: manual
  normalized: [0.1, 0.08, 0.92, 0.95]
  padding_percent: 2
  status: draft
  detection_basis: border_color
  unresolved_risks: []
```

- 坐标顺序为 `[left, top, right, bottom]`，取值范围为 0–1；
- 默认保留 2% 安全边距；
- 自动检测仅去除外围白边或透明边，保留复合图内部结构；
- Illustrator 放置完整原图，再使用可编辑剪切蒙版隐藏外围空白；
- 修改边界、源文件、面板顺序或图注事实会自动撤销批准。

## Skill 文件位置

- 主说明：`skills/assemble-pharmaceutics-figures/SKILL.md`
- 期刊布局：`skills/assemble-pharmaceutics-figures/references/journal-layout.md`
- 图注约束：`skills/assemble-pharmaceutics-figures/references/caption-contract.md`
- 隐私与科研完整性：`skills/assemble-pharmaceutics-figures/references/privacy-and-integrity.md`

## 安装

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Illustrator 2023 自动调用需要：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[windows]"
```
