# 智能符号化模拟电路分析系统

当前分支 `feature/desktop-slicap-shell` 实现 **PySide6 桌面开发版**，直接复用
SLiCAP 5.2.1 官方原理图画布。已弃用的 React Web Schematic 不属于本次交付。
系统把输入统一为规范化 `.cir`，分别执行 SLiCAP 数值分析和独立 SFG 算法的分频段符号化简。

**当前是可从源码运行的桌面开发版，还不是无需 Python 的 EXE 安装发行版。**
视觉模块按用户要求暂停测试，不属于当前验收范围；不加载视觉模型或大模型。

## 桌面版快速开始

在现有 `slicap5_env` 环境、此仓库根目录中运行：

```powershell
conda activate slicap5_env
.\start-desktop.ps1
```

桌面入口不启动本地 Web 服务，也不占用 5173、8000、7860 端口。
新机器需先安装本仓库依赖与固定的 `sfg-prototype` wheel，参见后文环境安装。
队友首次安装请直接阅读 [队友安装与验收说明](docs/desktop/teammate-setup.md)；
日常操作和验收边界见 [桌面使用说明](docs/desktop/usage.md) 与
[桌面阶段进度](docs/desktop/progress.md)。

```text
图片识别 IR（接口预留） ─┐
手写/上传 .cir ──────────┼─> CircuitDocument -> SLiCAP 5.2.1 数值分析
官方 .slicap_sch ────────┘                    -> SFG 分频段符号化简
```

## 当前能力

| 模块 | 当前状态 |
|---|---|
| 官方桌面画布 | 直接继承 SLiCAP 5.2.1 MainWindow，不重画器件或引脚 |
| 桌面后台任务 | QProcess 隔离，NDJSON 日志，取消和失败结果持久化 |
| 桌面结果 | 本地 KaTeX、数值/噪声/MNA、小信号元件、分频段符号表达式与误差 |
| EXE 安装发行版 | 未完成；standalone 构建与干净 Windows 验收仍待实施 |
| `.cir` 规范化与严格参数解析 | 已实现；支持 `k/m/u/n/p` 和科学计数法 |
| SLiCAP 5.2.1 数值分析 | 已实现；使用 `makeCircuit/doLaplace/doPZ/doMatrix/doNoise` |
| SFG 算法接入 | 已实现；安装独立 `sfg-prototype` wheel 后可调用 |
| 官方 `.slicap_sch` | 由 SLiCAP 5.2.1 官方画布创建、打开和保存 |
| `.cir` 生成 | 在隔离 worker 中调用 SLiCAP 官方导出逻辑，不由 ISACA 拼接 |
| 图片识别 | 本阶段只保留 `netLens IR -> CircuitDocument` 边界，不加载视觉权重 |

## 设计原则

- 旧 `slicap_env` 与 SLiCAP 4.0.8 不原地升级，新系统使用隔离的
  `slicap5_env`。
- SLiCAP 调用集中在 `backend/isaca_api/slicap_adapter.py`，界面代码不直接依赖
  SLiCAP 私有全局状态。
- SFG 算法保留在独立仓库，通过版本化 wheel 安装；本仓库不复制算法源码。
- 数值参数默认采用严格模式，未赋值参数不会被静默替换为 `1`。
- 每个分析任务有独立目录，保存输入、版本、诊断和结果制品。

## 目录结构

```text
backend/isaca_api/                 FastAPI、统一数据模型、SLiCAP 适配层
backend/isaca_desktop/             官方绘图壳层、输入面板、QProcess worker、结果界面
start-desktop.ps1                  桌面开发版入口，不启动 Web 服务
examples/desktop/                  RC 与 demo_2_numeric 网表
docs/desktop/                      安装、使用与里程碑记录
backend/tests/                     后端、参数、schematic 与官方 CLI 测试
scripts/check-environment.ps1      桌面环境和后端测试检查
scripts/run-circuit-regression.py  60 个测试网表的迁移回归
docs/migration/                    升级记录与架构决策
```

## 环境安装

推荐在 PowerShell 中执行：

```powershell
conda create -n slicap5_env python=3.12 -y
conda activate slicap5_env
pip install "SLiCAP==5.2.1"
pip install -e ".[test,ui]"
```

SFG 算法 wheel 由独立仓库构建：

```powershell
git clone https://github.com/Handkerchief-tj/Intelligent-Symbolic-Analog-Circuit-Analyzer.git
cd Intelligent-Symbolic-Analog-Circuit-Analyzer
git switch slicap-5.2-integration
pip install -e .\sfg_prototype
```

## 本地运行

```powershell
conda activate slicap5_env
cd <Analog-Circuit-Analyzer 仓库目录>
.\start-desktop.ps1 -Python (Get-Command python.exe).Source
```

程序将直接打开 PySide6 桌面窗口，不会给出浏览器地址。首次安装、项目操作和故障排查见
[队友安装与验收说明](docs/desktop/teammate-setup.md)。

## 参数策略

参数优先级为：

```text
本次用户覆盖 > 网表 .param > 元件行直接数值 > 用户显式启用的 SLiCAP 默认值
```

符号分析允许保留未赋值符号；数值分析、根聚类和误差评估要求相关参数具有数值。
“使用 SLiCAP 默认值”必须显式开启，结果中会记录来源和版本。SLiCAP 5.2.1
的若干基础器件默认值为 0，它们是软件缺省值，不等同于合理的物理设计值。

## API

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/api/v1/catalog/devices` | 5.2.1 器件、引脚和默认参数目录 |
| `GET` | `/api/v1/catalog/symbols/{name}.svg` | 单个官方 SLiCAP SVG 符号 |
| `GET` | `/api/v1/catalog/symbols/core` | 官方核心 SVG symbol bundle |
| `POST` | `/api/v1/circuits/normalize` | 规范化文本或 `.cir` 网表 |
| `POST` | `/api/v1/schematics/convert` | 内部 JSON、`.slicap_sch`、`.cir` 转换 |
| `POST` | `/api/v1/analyses` | 提交数值或 SFG 分析任务 |
| `GET` | `/api/v1/analyses/{job_id}` | 查询任务状态和结构化结果 |
| `GET` | `/api/v1/analyses/{job_id}/artifacts/{name}` | 获取网表和报告制品 |

API 默认不开放跨域访问。未来接入网站时，由服务器通过逗号分隔的
`ISACA_CORS_ORIGINS` 环境变量显式配置允许的正式前端域名。

## 验证

```powershell
.\scripts\check-environment.ps1
```

当前已验证：

- 当前 `slicap-5.2-integration` 算法分支为 `60 passed`；既有 SLiCAP 4.0.8/5.2.1
  双版本核心回归保持通过。
- 本仓库后端包含官方目录、CLI、junction、参数和分析链路回归测试。
- 20 个显式数值测试在 SLiCAP 4.0.8 与 5.2.1 间全部通过：传递函数均符号
  等价，采样最大相对误差约 `5.39e-16`，极点和零点最大相对差为 0。
- `demo_2_numeric` 可从 API 完成 SLiCAP 数值分析与 4 个 SFG 子频段化简，
  自动生成 `simplification.md`、`subrange_simplification.md`、
  `operation_ranking.md`、`error_trace.md` 和 `root_localization.md`。

运行 60 个测试网表的结构回归：

```powershell
python .\scripts\run-circuit-regression.py `
  --library-root "C:\pr\learning\college\else\sitp_2\测试样例\测试样例合集" `
  --output .\runs\regression\slicap521-structure.json
```

加上 `--numeric` 时，只对数值参数完整的网表执行 `doLaplace/doPZ`；其余案例仍会
记录结构解析结果和缺失参数，不会自动填 `1`。

首次完整回归中，20 个参数完整案例通过 `doLaplace/doPZ`，24 个符号案例通过结构
展平，另有 16 个失败。16 个失败文件均为多管目录中的旧草稿，
使用了未定义 PMOS 模型 `P`；case2 草稿还使用了非法电流源格式 `DC`。其对应的
“审查修正版”均通过，详情见迁移回归报告。该结果用于区分数据版本，不能简化成
“44/60 电路受支持”。

## 已知边界

- SLiCAP 5.2.1 GUI 仍在发展，本分支固定版本，不跟随 `latest`。
- SFG 算法对 `demo_2_numeric` 已能生成分频段解释；部分高阶局部闭环根仍可能
  返回较长表达式或 `unresolved`，不能描述为已达到任意复杂电路的论文级最简形式。
  默认按论文 Eq. (6)-(7) 验收整个频段的传递性能，逐根位置偏差仅作为诊断显示。
- 视觉模型和多用户服务器部署不在本阶段验收范围内。

迁移细节见 [docs/migration/README.md](docs/migration/README.md)。
