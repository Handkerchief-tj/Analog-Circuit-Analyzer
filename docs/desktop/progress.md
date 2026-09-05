# 桌面第一阶段实施记录

日期：2026-09-05。最新范围调整：视觉模块暂缓测试，优先完成非视觉端到端链路。

## 冻结基线

- 集成仓库：`731729513ef7daa6eef795e974e9dd34fd38a270`，从 `feature/slicap-5-web-schematic` 建立 `feature/desktop-slicap-shell`。
- 独立算法：`0800212e91d80b319c8189cc0abf8fbed65db2e0`，分支 `slicap-5.2-integration`，使用 `sfg-prototype 0.2.0` wheel。
- 开发环境：Python 3.12、SLiCAP 5.2.1；旧 SLiCAP 4.0.8 环境保持不动。
- 算法回归：52 项通过，0 failure/0 error/0 skip，JUnit 记录在 `runs/desktop-sfg-regression.xml`。

## 已实现的里程碑

| 里程碑 | 状态与证据范围 |
|---|---|
| 官方桌面壳层 | 已实现；直接复用 MainWindow/CanvasPanel，RC 实际实例化、保存和导出测试通过 |
| 项目与输入 | 已实现项目目录、网表编辑器、参数表和输入模式切换；不是任意网表自动反向布局 |
| 官方导出 | 在隔离 worker 中调用官方 CLI 的 `_load_scene/_write_netlist`，避免冻结 EXE 后 `python -m` 无效 |
| 数值 worker | 已接入 Laplace/PZ/Matrix/Noise/Bode，结果直接来自对象，不解析 SLiCAP HTML |
| SFG worker | 调用独立 wheel，返回频段传函、目标根解释、参数、误差与报告路径 |
| 任务生命周期 | queued/running/completed/failed/cancelled；请求与结果持久化；取消后可再启动 |
| 离线结果 | KaTeX 0.16.22 与字体、许可证入库；大结果使用本地文件页避免 Qt setHtml 2 MB 上限 |
| 视觉 | 接口原型保留；用户要求暂停测试，不标记为可发布功能 |
| 安装发行版 | 尚未完成；standalone、Graphviz 分发与干净 Windows 安装/卸载测试仍待进行 |

已构建并检查开发 wheel `isaca_local-0.1.0-py3-none-any.whl`：包含桌面入口、离线 KaTeX 与字体和许可证，
不包含测试包；wheel 只是 Python 包，不是独立运行的 EXE。生成文件在 `runs/desktop-wheel/`，不提交到 Git。

## 本轮修复的可靠性问题

1. 官方 CanvasPanel 的 `_scene` 和 `_current_path` 是实例属性，不能在类上检查；修正版本适配检查。
2. 原理图修改后不能直接分析旧网表；现在原理图模式强制先保存并导出。
3. 参数表不能把每次展示都重新解释为“用户覆盖”；只记录实际变动，并重新求值依赖参数。
4. QProcess 取消定时器不能跨任务存活，否则可能误杀后续 worker；改成每任务拥有并及时停止。
5. 保持 QApplication 的强引用，避免官方网表导出测试中 Qt 对象提前释放造成进程崩溃。
6. NumPy 根数组不能用 `array or []` 判断；显式处理 None。
7. Graphviz 缺失/超时不应使已经成功的符号计算消失；保留结果并增加 warning。
8. 分频段误差与全局误差分开序列化；GUI 不在主线程重新解析大型 SymPy 表达式。

## 验证记录

核心回归与 demo 的最新数值以对应 JUnit/verification.json 为准，不以历史聊天中的计数替代。
当前后端/桌面回归为 **32 passed / 1 skipped**，跳过的是用户暂停的视觉校对测试。
RC 在 offscreen 与 Windows 原生 Qt 平台均完成保存、官方网表导出、取消后重启、数值及 Bode 分析；
原生窗口检查到 2 个实际 KaTeX 公式，极点为 -1000 rad/s。
最后一轮新增导出输入哈希检查、运行中输入锁定和持久化日志后，再次通过完整回归。
首次新增视觉校对测试使用了错误的 HSPICE 模型标记，出现一次夹具失败；已改为 netLens 格式，
但按用户最新要求保持显式跳过，不声称该视觉测试已经重新通过。

### demo_2 的当前结果，不等同于全面复现验收

桌面 worker 首次完整验证耗时约 217 秒（与后端回归同时运行，非独立性能基准），接受 21 个操作。
参考根为 3 个极点、2 个零点。频率边界来自本次配置的算法流程，不手工替换成论文图注边界。

| Cluster | 频段 / Hz | 最大幅值误差 / dB | 最大相位误差 / deg |
|---|---|---|---|
| 1 | 1.000000e1 – 3.399850e3 | 3.362558e-4 | 7.882563e-3 |
| 2 | 3.399850e3 – 4.685967e5 | 5.884220e-2 | 4.194397 |
| 3 | 4.685967e5 – 9.823256e7 | 8.942093e-2 | 4.266253 |
| 4 | 9.823256e7 – 1.000000e11 | 8.964611e-2 | 3.697497 |

四个子图在算法的频率采样检查中均处于 ±2 dB、±5° 范围内。恢复了 `gm/cmu`、
Eq.(24) `-cmu*gx/(cx*(cmu+cpi))` 和输入极点 `-(Gin+gx)/cx` 的符号形式。
但 **第二频段局部极点解释误差约 36.49%，状态为 outside_error_limit**；
第一频段的已解析根形式仍然很长。这说明“桌面集成可运行”和“所有根都达到论文可读性”是两项不同的验收。
本次不放宽根误差门限，不伪造论文形式，也不在集成仓库里修改算法源码来掩盖该问题。
该限制同时进入 GUI 警告和结构化 diagnostics，后续在独立算法仓库调查候选选择与表达式可读性。
最终 worker 复验用时约 194.7 秒，Eq.(24) 通过 SymPy 符号等价断言，warning 被保留。
结构化证据位于 `runs/desktop-demo2-20260905-final/verification.json`；精简、可入库的记录见
`verification-2026-09-05.json`。

## 下一阶段与验收边界

1. 扩大官方画布电路回归到 RLC、MOS/BJT、四种受控源、浮置源和子电路，并做实际 GUI 往返。
2. 检查多项目切换、任务异常退出后恢复、噪声显示和复杂表达式的大结果体验。
3. 构建独立 wheel，固定编译工具版本，准备 pyside6-deploy standalone；不能只写 spec 就称打包完成。
4. 审计 Qt/SLiCAP/SFG/KaTeX/Graphviz 的资源与许可证，确保未混入 Web、模型权重或开发缓存。
5. 私有 Graphviz 打包后，在无 Python/Conda/全局 Graphviz 的干净 Windows 上运行 RC、demo_2、取消恢复和卸载测试。
6. 视觉验收等用户恢复此范围后再单独推进。本轮不加载视觉模型。

官方接口参考：[SLiCAP GUI](https://www.slicap.org/GUI/)、
[Qt deployment](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)、
[KaTeX browser usage](https://katex.org/docs/browser.html)。实际适配以本机固定的 5.2.1 源码为准。
