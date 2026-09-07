import gradio as gr
from netlist_parser import sync_text_to_df, sync_df_to_text, update_param_df, MOS_PARAMS
from analysis import run_my_analysis

DEFAULT_NETLIST = """Vdd Vdd 0 V dc={Vdd} value=0
Vin in 0 V value={Vin} 

Rd Vdd out R value={Rd} noisetemp={T}
Rs net1 0 R value={Rs} noisetemp={T}

M1 out in net1 0 M gm={gm1} cgs={cgs1} cdg={cdg1}

.source Vin
.detector V_out
.end"""

HELP_TEXT = """# 📖 使用说明与网表语法指南

---

## 一、平台使用流程

### 第一步：输入电路图与网表
- **方式 A**：拍摄或上传电路图片，点击"识别图片提取网表"（功能预留中，暂不可用）
- **方式 B**：在下方文本框中直接输入或粘贴 SPICE 网表（推荐）

### 第二步：配置元件参数
- **A 区**：勾选 MOS 管小信号参数（gm、cgs、cdg 等），系统会自动将对应参数插入网表
- **B 区**：为网表中的 `{变量名}` 赋予具体数值，后台自动注入 `.param` 语句

### 第三步：选择分析类型并执行
勾选需要分析的模块（可多选）：

| 分析模块 | 功能说明 |
|---------|---------|
| 拉普拉斯分析 | 推导传递函数 H(s)，计算零极点 |
| 矩阵方程分析 | 列写节点电压矩阵方程（MNA） |
| 噪声分析 | 计算各器件噪声贡献及总输出噪声谱 |
| 波特图绘制 | 绘制幅频 / 相频响应曲线 |

点击 **开始综合分析** 执行。

### 第四步：查看结果
- LaTeX 渲染的传递函数、矩阵方程、噪声数据
- 高清波特图（幅频 + 相频）
- 大模型深度分析报告

---

## 二、SPICE 网表语法指南

### 2.1 基本结构

```
[标题行（可选）]
<元件名> <节点+> <节点-> [<节点+> <节点->] <元件类型> <参数>=<值> ...

.source <信号源名>          （必填：定义输入激励）
.detector <检测节点>        （必填：定义输出观测点，格式 V_<节点名>）
.param <变量名>=<数值> ...  （可选：参数赋值）
.model <模型名> <类型>       （可选：模型定义）
.end                         （必填：网表结束）
```

### 2.2 元件类型速查

| 元件 | 关键字 | 示例 |
|------|--------|------|
| 电压源 | V | `Vdd Vdd 0 V dc={Vdd} value=0` |
| 电阻 | R | `Rd Vdd out R value={Rd} noisetemp={T}` |
| 电容 | C | `C1 n1 n2 C value={C1}` |
| MOS 管 | M | `M1 out in net1 0 M gm={gm1} cgs={cgs1} cdg={cdg1}` |
| BJT | Q | `Q1 out in 0 Q gm={gm} gpi={gpi}` |
| VCCS | G | `G1 3 5 2 5 G value={g_m}` |
| CCCS | H | `H1 4 0 Vsense H value={A_r}` |
| 二端口 | O | `O1 2 4 3 0 MyModel` |

### 2.3 MOS 管小信号参数列表

在第二步 A 区勾选后自动插入网表：

`gm` `cgs` `cgb` `cdg` `cdb` `csb` `gb` `go`

使用格式：`M<name> <D> <G> <S> <B> M <参数>=<值> ...`

### 2.4 参数系统
- 使用花括号 `{变量名}` 表示符号参数，系统会在符号推导中保留变量名
- 在第二步 B 区为所有 `{变量}` 赋予具体数值（用于数值计算和波特图绘制）
- `s` 为保留字，表示拉普拉斯算子，可在参数表达式中使用，如 `zt={R_t/(1+s*tau)}`

---

## 三、不同分析功能的网表语法说明

### 🔵 拉普拉斯分析与波特图绘制
这两者要求网表包含完整的 .source 和 .detector 定义，且 MOS 管必须提供小信号参数。

```
* 共源极放大器示例
Vdd Vdd 0 V dc={Vdd} value=0
Vin in 0 V value={Vin}
Rd Vdd out R value={Rd}
M1 out in 0 0 M gm={gm} cgs={cgs} cdg={cdg}
.source Vin
.detector V_out
.end
```

### 🟢 矩阵方程分析
不需要 .source / .detector，系统自动列写所有节点的 KCL 方程，但也可保留以便与其他分析共用网表。

```
Vdd Vdd 0 V dc={Vdd} value=0
Vin in 0 V value={Vin}
Rd Vdd out R value={Rd}
M1 out in 0 0 M gm={gm} cgs={cgs} cdg={cdg}
.end
```

### 🟠 噪声分析
- 电阻需标注 `noisetemp={T}` 以启用车热噪声建模
- 需定义 .source 和 .detector

```
Vcc vcc 0 V dc={Vcc} value=0
Vs in 0 V value={Vs}
Rs vcc in R value={Rs} noisetemp={T}     （带噪声温度）
Re vcc out R value={Re} noisetemp={T}
Rl out 0 R value={Rl} noisetemp={T}
Q out vcc 0 0 QV gm={gm} gpi={gpi}
.source Vs
.detector V_out
.end
```

### 使用 .model 定义复杂元件

```
O1 2 4 3 0 MyModel
.model MyModel OC
+ cp={C_i}
+ gp={1/R_i}
+ gm={g_m}
+ zt={R_t/(1+s*tau)}
```

---

## 四、完整实战示例

### 共源极放大器（拉普拉斯 + 波特图 + 噪声）

```
Vdd Vdd 0 V dc={Vdd} value=0
Vin in 0 V value={Vin}
Rd Vdd out R value={Rd} noisetemp={T}
Rs net1 0 R value={Rs} noisetemp={T}
M1 out in net1 0 M gm={gm1} cgs={cgs1} cdg={cdg1}
.source Vin
.detector V_out
.end
```

第二步 B 区填入：`Vdd=5  Vin=1  Rd=1k  Rs=100  T=300  gm1=10m  cgs1=1p  cdg1=0.5p`

### 电流反馈放大器（含二端口模型）

```
V1 1 0 V value={V_s}
R1 1 2 R value={R_s}
O1 2 4 3 0 Mycfb
R2 3 0 R value={R_ell}
R3 3 4 R value={R_a}
R4 4 0 R value={R_b}
.model Mycfb OC
+ cp={C_i} gp={1/R_i} gm={g_m} zt={R_t/(1+s*tau)}
.source V1
.detector V_3
.end
```

---

## 五、注意事项

1. 网表必须以 `.end` 结尾，否则无法解析
2. `.detector` 的格式为 `V_<节点名>`（如 `V_out`、`V_3`），表示检测该节点的电压
3. `.source` 的值必须与网表中某个独立电压源的名称一致
4. 注释行以 `*` 开头
5. 波特图扫频参数为选填，默认 0.001Hz ~ 1MHz、200 个点
6. 图片识别（第一步）为功能预留状态，当前建议直接输入网表
7. 大模型深度分析需要配置 API Key（环境变量 `DASHSCOPE_API_KEY`）
8. 使用 `.model` 时，续行以 `+` 开头

---

## 六、常见问题

**Q: 分析结果为什么是空的？**
A: 检查网表是否包含 `.end`，.source 和 .detector 是否正确定义。

**Q: MOS 参数如何填写？**
A: 在第二步 A 区勾选需要的参数（如 gm、cgs、cdg），系统自动插入网表。

**Q: 如何做参数扫描？**
A: 目前暂未开放参数扫描功能，可通过修改 B 区数值后重新分析实现。

**Q: 为什么波特图没有曲线？**
A: 检查是否勾选了"波特图绘制"，以及网表是否包含完整的 .source 和 .detector。"""

with gr.Blocks(theme=gr.themes.Soft(), title="智能电路分析系统") as demo:
    with gr.Row():
        with gr.Column(scale=4):
            gr.Markdown("## 📝 智能电路图识别与一键分析工具")
        with gr.Column(scale=1, min_width=80):
            help_btn = gr.Button("📖 帮助", size="sm", variant="secondary")

    help_md = gr.Markdown(value=HELP_TEXT, visible=False, label="帮助文档")

    gr.Markdown("### 📸 第一步：输入电路图与网表生成")
    with gr.Row():
        with gr.Column(scale=1):
            img_input = gr.Image(sources=["upload", "webcam"], type="filepath", label="1. 拍摄或上传")
            btn_img_to_netlist = gr.Button("⚡ 识别图片提取网表 (功能预留)")
        with gr.Column(scale=1):
            circuit_text = gr.Textbox(lines=12, label="2. 可编辑电路网表", value=DEFAULT_NETLIST, interactive=True)

    gr.Markdown("---")

    gr.Markdown("### ⚙️ 第二步：元件参数提取与赋值配置")
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("#### A. MOS管小信号参数 (打钩自动插入网表)")
            mos_df = gr.Dataframe(
                value=sync_text_to_df(DEFAULT_NETLIST, []),
                headers=["MOS元件"] + MOS_PARAMS, datatype=["str"] + ["bool"] * len(MOS_PARAMS),
                type="array", interactive=True, row_count=(1, "dynamic"), col_count=(len(MOS_PARAMS) + 1, "fixed")
            )

        with gr.Column(scale=1):
            gr.Markdown("#### B. 核心变量具体赋值 (后台自动注入 .param)")
            param_df = gr.Dataframe(
                value=update_param_df(DEFAULT_NETLIST, []),
                headers=["参数名 (变量)", "具体数值"], datatype=["str", "str"],
                type="array", interactive=True, row_count=(1, "dynamic"), col_count=(2, "fixed")
            )

    gr.Markdown("---")

    gr.Markdown("### 🚀 第三步：选择分析类型并执行")
    with gr.Row():
        analysis_selector = gr.CheckboxGroup(
            choices=["拉普拉斯分析", "矩阵方程分析", "噪声分析", "波特图绘制"],
            value=["拉普拉斯分析", "波特图绘制"],
            label="请勾选需要运行的独立模块", interactive=True
        )

        with gr.Accordion("📶 波特图扫频参数设置 (选填)", open=False):
            with gr.Row():
                sweep_start = gr.Number(value=0.001, label="起始频率 (Hz)")
                sweep_stop = gr.Number(value=1e6, label="终止频率 (Hz)")
                sweep_points = gr.Number(value=200, label="扫描点数", precision=0)

    btn_analyze = gr.Button("开始综合分析", variant="primary", size="lg")

    gr.Markdown("---")

    # ... 前半部分代码不变 ...

    gr.Markdown("### 📊 第四步：分析结果")
    out_laplace = gr.Markdown(visible=False, label="拉普拉斯传递函数", latex_delimiters=[
        {"left": "$$", "right": "$$", "display": True},
        {"left": "$", "right": "$", "display": False},
        {"left": r"\(", "right": r"\)", "display": False},
        {"left": "\\[", "right": "\\]", "display": False}
    ])
    out_matrix = gr.Markdown(visible=False, label="矩阵方程", latex_delimiters=[
        {"left": "$$", "right": "$$", "display": True},
        {"left": "$", "right": "$", "display": False},
        {"left": r"\(", "right": r"\)", "display": False},
        {"left": "\\[", "right": "\\]", "display": False}
    ])
    out_noise = gr.Markdown(visible=False, label="噪声分析", latex_delimiters=[
        {"left": "$$", "right": "$$", "display": True},
        {"left": "$", "right": "$", "display": False},
        {"left": r"\(", "right": r"\)", "display": False},
        {"left": "\\[", "right": "\\]", "display": False}
    ])

    # 采用原生的 gr.Image 接收 PNG，既不会卡死浏览器，右上角又自带全屏放大与下载按钮
    with gr.Row():
        out_bode_mag = gr.Image(type="filepath", visible=False, label="波特幅度图 (高清PNG)", interactive=False)
        out_bode_phs = gr.Image(type="filepath", visible=False, label="波特相位图 (高清PNG)", interactive=False)

    gr.Markdown("#### 🤖 大模型深度分析结果")
    res_markdown = gr.Markdown(
        value="大模型根据公式推导的分析结果会显示在这里~",
        latex_delimiters=[
            {"left": "$$", "right": "$$", "display": True},
            {"left": r"\(", "right": r"\)", "display": False},
            {"left": "$", "right": "$", "display": False},
            {"left": "\\[", "right": "\\]", "display": False}
        ]
    )
    res_fig = gr.Plot(visible=False)

    # ---------------- 事件绑定 ----------------
    btn_img_to_netlist.click(fn=lambda x: DEFAULT_NETLIST, inputs=[img_input], outputs=[circuit_text])
    circuit_text.change(fn=sync_text_to_df, inputs=[circuit_text, mos_df], outputs=[mos_df])
    circuit_text.change(fn=update_param_df, inputs=[circuit_text, param_df], outputs=[param_df])
    mos_df.change(fn=sync_df_to_text, inputs=[mos_df, circuit_text], outputs=[circuit_text])

    btn_analyze.click(
        fn=run_my_analysis,
        inputs=[circuit_text, param_df, analysis_selector, sweep_start, sweep_stop, sweep_points],
        outputs=[out_laplace, out_matrix, out_noise, out_bode_mag, out_bode_phs, res_markdown, res_fig]
    )

    # ---------------- 帮助文档展开/收起 ----------------
    help_visible = gr.State(value=False)

    def toggle_help(visible):
        return not visible, gr.update(visible=not visible)

    help_btn.click(
        fn=toggle_help,
        inputs=[help_visible],
        outputs=[help_visible, help_md]
    )

    # ---------------- 页脚：开源致谢 ----------------
    gr.HTML("""
    <div style="margin-top: 48px; padding: 16px 0; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; text-align: center; line-height: 1.8;">
        本平台基于以下开源项目构建：
        <br>
        <a href="https://slicap.github.io/SLiCAP_python/" target="_blank" style="color: #6b7280; text-decoration: none;">SLiCAP</a>
        (MIT License, Copyright © 2024–2025 Anton Montagne) ·
        <br>
        <a href="https://github.com/NYCU-AI-EDA/Netlistify" target="_blank" style="color: #6b7280; text-decoration: none;">Netlistify</a>
        (Apache License 2.0, © 2025 Chun-Yen Huang et al.) ·
        <br>
        <a href="https://github.com/facebookresearch/detr" target="_blank" style="color: #6b7280; text-decoration: none;">Facebook DETR</a>
        (Apache License 2.0, © Facebook, Inc.)
        <br>
        本系统为上述项目的集成与改进，仅为教学与工程研究目的使用。
    </div>
    """)

if __name__ == "__main__":
    # 【核心修改】：去掉了 max_threads=1，防止阻塞浏览器的网络心跳检测！
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False)