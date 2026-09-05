# ISACA 桌面开发版使用说明

## 环境与入口

固定 Python 3.12、SLiCAP 5.2.1，算法来自独立 `sfg-prototype==0.2.0` wheel。
不修改旧 `slicap_env`，不修改任何 Conda 环境中的 SLiCAP 源码。

在 `Analog-Circuit-Analyzer-next` 仓库根目录：

```powershell
conda activate slicap5_env
.\start-desktop.ps1
```

可选参数 `-Project <项目目录>` 和 `-File <.cir 或 .slicap_sch 文件>`。
启动器检查 Python、SLiCAP、QtWebEngine 和 SFG 包，不会启动网络服务。
本地公式资源已经随源码保存，无需访问 CDN。

## 官方原理图

1. 左侧创建/打开一个项目文件夹。建议使用独立用户项目，不把安装目录作为项目。
2. 点击“新建原理图”，或打开已有 `.slicap_sch`。
3. 在官方画布绘制、连线、设置元件参数、`.param`、source 和 detector。绘图菜单仍是官方英文菜单。
4. 保存原理图；右侧选择输入为原理图，再运行分析，或使用菜单“导出当前原理图并分析”。
5. 程序保存当前图后，在独立 worker 中调用 SLiCAP 官方 CLI 使用的加载器和导出函数。
6. 生成的 `.cir` 进入严格参数检查，数值完整后执行分析。

原理图是绘图权威文件，导出的 `.cir` 是分析输入。选择原理图分析时总是重新导出，
不会误用上一次留在网表编辑器里的旧网表。取消保存时不启动导出。

## 手写网表

左侧“打开网表”可载入 `examples/desktop/rc_lowpass.cir` 或 `demo_2_numeric.cir`。
网表编辑器支持行号、基础语法高亮、保存和未保存修改提示。
右侧输入模式选择网表，点“验证”查看参数来源与缺失项。

参数表中的数值可以覆盖，但只把真正修改过的单元格作为用户覆盖；
未修改项保持原有 `.param` 或 inline 来源。覆盖参数后会重新解析依赖表达式。
缺失参数不自动设为 1。“使用 SLiCAP 默认值”是显式选项，不代表实际工艺参数。

## 分析设置与结果

可选择 Laplace、PZ、Matrix、Noise、Bode 和 SFG 符号化简。
默认幅值误差 2 dB、相位误差 5°，每个频段最多接受 10 个操作。
两个频率输入框同时留空时由分析流程决定范围；填写时单位为 Hz，要求有限、正值、递增。
SFG 根聚类和误差受控化简必须提供完整数值，即使其输出是符号表达式。

结果标签展示分析摘要、展平元件、数值传函及极零点、MNA、噪声、SFG 分频段结果和文件列表。
根表达式使用 s 平面约定，根的频率另以 Hz 显示。零点的左右半平面符号不得丢失。
子图传函的频响误差和局部根解释的根误差分别展示；局部根解释不等于全图精确求根。
完整 ranking、root localization 和 error trace 报告可在“生成文件”中打开。

计算通过 QProcess 运行。点取消会写取消请求，超时后仅结束当前 worker；不会删除项目。
每个任务的 request.json、worker-result.json、日志和 desktop-state.json 保存在项目 runs 子目录。
计算途中关闭窗口会询问是否取消任务，未保存的图和网表会单独询问。

## Graphviz

开发版暂时可以使用当前环境的 dot，或仅给本次进程设置：

```powershell
$env:ISACA_GRAPHVIZ_DOT = '你的 Graphviz 路径\dot.exe'
.\start-desktop.ps1
```

这不修改系统 PATH。dot 缺失或超时只会影响 SFG SVG，不会丢弃 DOT、表达式和数值结果。
发布版的私有 Graphviz 尚待构建及验收，不要把开发机可运行当成安装包已完成。

## 暂缓的功能

视觉入口目前仅为实验性接口，按用户决定暂停视觉测试和性能验证，不纳入本阶段验收。
不要依赖其识别结果直接分析陌生电路。CPU/GPU 包、模型分发、故障回退仍需独立测试。
本版没有大模型辅助报告，没有云端部署，也没有已验收的 EXE 安装器。

## 可重复验证

```powershell
python -m pytest backend/tests -q
python scripts/verify-desktop-analysis.py --case rc_lowpass --output runs/verify-rc-01
python scripts/verify-desktop-analysis.py --case demo_2_numeric --symbolic --output runs/verify-demo2-01
```

输出目录必须是新的目录，以免覆盖前次证据。脚本复用桌面 worker，不另写数值/化简算法。
算法源码自己的 52 项测试仍在独立算法仓库运行。
