# 队友安装与验收说明

本文用于在一台新的 Windows 10/11 开发机上运行与当前开发机相同的 ISACA
桌面开发版。当前版本是源码开发版，不是独立 EXE 安装包。

## 交付范围

- 绘图界面直接复用 SLiCAP 5.2.1 官方 Structured Electronic Design Environment。
- 数值分析包括 Laplace、PZ、Matrix、Noise 和 Bode。
- 符号分析由独立的 `sfg-prototype 0.2.3` 包提供。
- 已弃用的 React Web Schematic、视觉模型和大模型报告不属于本次交付。
- 正确入口是 `start-desktop.ps1`；不访问 `127.0.0.1:5173`，也不需要 Node.js。

## 前置条件

开发机需要安装 Git 和 Miniconda/Anaconda，并能访问以下两个仓库：

1. `Handkerchief-tj/Analog-Circuit-Analyzer`
2. `Handkerchief-tj/Intelligent-Symbolic-Analog-Circuit-Analyzer`

如果算法仓库保持 private，需要先把使用者加入该仓库，或另行提供版本固定的 wheel。

## 1. 克隆两个仓库

在准备保存源码的父目录运行：

```powershell
git clone https://github.com/Handkerchief-tj/Analog-Circuit-Analyzer.git
git clone https://github.com/Handkerchief-tj/Intelligent-Symbolic-Analog-Circuit-Analyzer.git

cd Analog-Circuit-Analyzer
git switch feature/desktop-slicap-shell
```

## 2. 创建固定环境

```powershell
conda create -n slicap5_env python=3.12 -y
conda activate slicap5_env
python -m pip install --upgrade pip
python -m pip install -e ".[test,ui]"
```

这里会安装固定的 `SLiCAP==5.2.1`、PySide6、FastAPI 和桌面运行依赖。
不要在旧的 `slicap_env` 中覆盖安装。

## 3. 安装 SFG 算法

假设两个仓库位于同一个父目录：

```powershell
cd ..\Intelligent-Symbolic-Analog-Circuit-Analyzer
git switch slicap-5.2-integration
python -m pip install -e .\sfg_prototype

cd ..\Analog-Circuit-Analyzer
```

开发阶段使用 editable install，更新算法仓库后无需复制源码。正式发行时将改用固定
版本 wheel。

## 4. 验证环境

```powershell
$python = (Get-Command python.exe).Source
.\scripts\check-environment.ps1 -Python $python
```

检查必须显示 Python 3.12、SLiCAP 5.2.1、PySide6 和已安装的
`sfg-prototype`，随后运行后端/桌面自动化测试。视觉验收测试按当前范围保持跳过。

## 5. 启动桌面程序

```powershell
$python = (Get-Command python.exe).Source
.\start-desktop.ps1 -Python $python
```

预期结果是直接打开 PySide6 桌面窗口。不会启动浏览器，不会显示 5173、8000 或
7860 端口。

也可以直接打开项目或文件：

```powershell
.\start-desktop.ps1 -Python $python -Project "C:\path\to\project"
.\start-desktop.ps1 -Python $python -File ".\examples\desktop\demo_2_numeric.cir"
```

## 6. 最小验收流程

1. 打开 `examples/desktop/rc_lowpass.cir`，执行 Laplace、PZ、Matrix 和 Bode。
2. 确认结果页先显示可读传递函数，极点同时显示 Hz 与 rad/s，MNA 显示为矩阵。
3. 打开 `examples/desktop/demo_2_numeric.cir`，频率范围填 `10` 到 `1e11` Hz。
4. 执行 SFG 分析，确认出现四个 root cluster、频率子区间和逐频段符号结果。
5. 新建官方 schematic，绘制 RC 低通，设置 source/detector，保存并导出分析。

## 常见问题

### `No module named sfg_prototype`

没有执行第 3 步，或者安装到了另一个 Conda 环境。重新激活 `slicap5_env` 后安装。

### `SLiCAP==5.2.1 required`

当前终端没有激活正确环境。执行 `conda activate slicap5_env`，再检查：

```powershell
python -c "import SLiCAP; print(SLiCAP.__version__)"
```

### Graphviz 警告

Graphviz 只用于把 DOT 渲染为 SVG。缺失时传递函数、极零点和符号结果仍应保留，
只是部分 SFG 图像无法生成。开发机可单独安装 Graphviz，正式安装包将携带私有副本。

### 为什么没有网页地址

本分支是桌面开发版。旧 React Web Schematic 已从交付中移除；未来网站版将通过
结构化后端 API 接入分析核心，而不是恢复该旧画布。

## 更新代码

```powershell
cd <Analog-Circuit-Analyzer 路径>
git pull origin feature/desktop-slicap-shell

cd <Intelligent-Symbolic-Analog-Circuit-Analyzer 路径>
git pull origin slicap-5.2-integration
```

更新依赖声明后重新执行两个仓库的 editable install 和环境检查。
