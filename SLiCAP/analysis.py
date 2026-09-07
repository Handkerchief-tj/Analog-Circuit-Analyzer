import os
import sys
import subprocess
import matplotlib.pyplot as plt
import gradio as gr
import datetime
from dashscope import Generation
from utils import read_file_content, get_latest_html, parse_slicap_to_markdown, clean_old_html, convert_pdf_to_png
import matplotlib
matplotlib.use('Agg')

def save_backend_log(netlist, laplace_md, matrix_md, noise_md, bode_mag_path, bode_phs_path, llm_result, analysis_types):
    """恢复后台静默日志留存功能"""
    log_dir = "./backend_logs"
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"log_{timestamp}.md")

    content = f"# 自动化分析日志 - {timestamp}\n"
    content += f"**勾选的分析类型**: {', '.join(analysis_types)}\n\n"
    content += f"## 1. 运行时的网表 (包含参数注入)\n```text\n{netlist}\n```\n\n"
    content += f"## 2. 提取的拉普拉斯公式\n{laplace_md if laplace_md else '*未执行或提取失败*'}\n\n"
    content += f"## 3. 提取的矩阵方程\n{matrix_md if matrix_md else '*未执行或提取失败*'}\n\n"
    content += f"## 4. 提取的噪声分析\n{noise_md if noise_md else '*未执行或提取失败*'}\n\n"
    content += f"## 5. 波特图状态\n"
    content += f"- 幅度图: {'✅ 成功生成' if bode_mag_path else '❌ 未生成'}\n"
    content += f"- 相位图: {'✅ 成功生成' if bode_phs_path else '❌ 未生成'}\n\n"
    content += f"## 6. 大模型深度分析报告\n{llm_result}\n"

    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[后台日志] 本次分析已保存至: {log_file}")
    except Exception as e:
        print(f"[后台日志] 保存出错: {e}")


def find_pdf_path(filename):
    """寻找 SLiCAP 生成的 PDF 文件"""
    if os.path.exists(f"./img/{filename}"): return f"./img/{filename}"
    if os.path.exists(f"./html/img/{filename}"): return f"./html/img/{filename}"
    return None


def run_my_analysis(ui_netlist_text, param_df_data, analysis_types, start_f, stop_f, points):
    if not ui_netlist_text or not analysis_types:
        return (gr.update(visible=False), gr.update(visible=False),
                gr.update(visible=False), gr.update(visible=False),
                gr.update(visible=False),
                "⚠️ 分析失败：未提供网表或未勾选分析项！", None)

    # 1. 组装最终仿真网表
    final_netlist_lines = ui_netlist_text.strip().split('\n')
    if param_df_data:
        param_str = ".param " + " ".join([f"{row[0]}={row[1]}" for row in param_df_data if row[0]])
        if final_netlist_lines[-1].strip().lower() == '.end':
            final_netlist_lines.insert(-1, param_str)
        else:
            final_netlist_lines.append(param_str)
            final_netlist_lines.append('.end')

    final_netlist = "\n".join(final_netlist_lines)

    os.makedirs("./cir", exist_ok=True)
    with open("./cir/circuit.cir", "w", encoding="utf-8") as f:
        f.write(final_netlist)

    md_laplace, md_matrix, md_noise, llm_context = "", "", "", ""
    svg_mag, svg_phs = None, None
    path_mag, path_phs = None, None
    os.makedirs("./html", exist_ok=True)
    os.makedirs("./img", exist_ok=True)

    is_laplace = "拉普拉斯分析" in analysis_types
    is_matrix = "矩阵方程分析" in analysis_types
    is_noise = "噪声分析" in analysis_types
    is_bode = "波特图绘制" in analysis_types

    # --- 执行拉普拉斯 ---
    if is_laplace:
        clean_old_html("./html", "Laplace-Transfer.html")
        res = subprocess.run([sys.executable, "run_laplace.py"], capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0: print(f"❌ [拉普拉斯报错]: {res.stderr}")

        latest_lap = get_latest_html("./html", "Laplace-Transfer.html")
        if latest_lap:
            md_laplace = parse_slicap_to_markdown(read_file_content(latest_lap))
            llm_context += f"--- 传递函数 ---\n{md_laplace}\n\n"

    # --- 执行矩阵 ---
    if is_matrix:
        clean_old_html("./html", "Matrix-Equations.html")
        res = subprocess.run([sys.executable, "run_matrix.py"], capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0: print(f"❌ [矩阵报错]: {res.stderr}")

        latest_mat = get_latest_html("./html", "Matrix-Equations.html")
        if latest_mat:
            md_matrix = parse_slicap_to_markdown(read_file_content(latest_mat))
            llm_context += f"--- 矩阵方程 ---\n{md_matrix}\n\n"

    # --- 执行噪声分析 ---
    if is_noise:
        clean_old_html("./html", "Noise-Analysis.html")
        res = subprocess.run([sys.executable, "run_noise.py"], capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            print(f"❌ [噪声报错]: {res.stderr}")

        latest_noise = get_latest_html("./html", "Noise-Analysis.html")
        if latest_noise:
            md_noise = parse_slicap_to_markdown(read_file_content(latest_noise))
            llm_context += f"--- 噪声分析 ---\n{md_noise}\n\n"

    # --- 执行波特图 ---
    if is_bode:
        # 清除旧文件（防干扰）
        for p in ["./img/f_dBm.pdf", "./img/f_dBm.png", "./img/f_phs.pdf", "./img/f_phs.png"]:
            if os.path.exists(p): os.remove(p)

        res = subprocess.run([sys.executable, "run_bode.py", str(start_f), str(stop_f), str(points)],
                             capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if res.returncode != 0:
            print(f"❌ [波特图报错]: {res.stderr}")
            png_mag, png_phs = None, None
        else:
            # 1. 寻找生成的 PDF
            pdf_mag = find_pdf_path("f_dBm.pdf")
            pdf_phs = find_pdf_path("f_phs.pdf")
            # 2. 转换为 PNG
            png_mag = convert_pdf_to_png(pdf_mag)
            png_phs = convert_pdf_to_png(pdf_phs)
    else:
        png_mag, png_phs = None, None

    # --- 调用大模型 ---
    llm_analysis_result = ""
    if llm_context.strip():
        expected_sections = ["### 一、 电路拓扑与基础分析\n（必须使用 Markdown 表格归纳）"]
        section_index = 2
        if is_laplace:
            expected_sections.append(f"### {['一', '二', '三', '四', '五'][section_index - 1]}、 拉普拉斯传递函数")
            section_index += 1
        if is_matrix:
            expected_sections.append(f"### {['一', '二', '三', '四', '五'][section_index - 1]}、 节点电压矩阵方程")
            section_index += 1
        if is_noise:
            expected_sections.append(f"### {['一', '二', '三', '四', '五'][section_index - 1]}、 噪声分析")
            section_index += 1
        expected_sections.append(f"### {['一', '二', '三', '四', '五'][section_index - 1]}、 综合性能评估")

        messages = [
            {'role': 'system',
             'content': f"你是一位电路分析专家。请严格按顺序输出：\n\n{chr(10).join(expected_sections)}\n\n⚠️ 所有行内变量必须用 \\( ... \\) 包裹！"},
            {'role': 'user', 'content': f"公式：\n{llm_context}\n最终网表：\n{final_netlist}"}
        ]
        try:
            response = Generation.call(api_key=os.environ.get("DASHSCOPE_API_KEY"), model="glm-5.1",
                                       messages=messages, result_format="message")
            if response.status_code == 200: llm_analysis_result = response.output.choices[0].message.content

            else:
                print(f"请求失败，状态码: {response.status_code}")
                print(f"错误码: {response.code}")
                print(f"错误信息: {response.message}")
                print("详细错误说明请参考：https://help.aliyun.com/zh/model-studio/developer-reference/error-code")



        except Exception as e:
            llm_analysis_result = f"异常：{str(e)}"
    else:
        llm_analysis_result = "未勾选公式类分析或提取失败，跳过大模型文字分析。"

    # --- 核心：保存后台日志 ---
    save_backend_log(final_netlist, md_laplace, md_matrix, md_noise, png_mag, png_phs, llm_analysis_result, analysis_types)

    fig = plt.figure(figsize=(1, 1));
    plt.axis("off");
    plt.close(fig)

    # 将生成的 PNG 路径返回给前端的 gr.Image
    return (
        gr.update(value=md_laplace, visible=is_laplace),
        gr.update(value=md_matrix, visible=is_matrix),
        gr.update(value=md_noise, visible=is_noise),
        gr.update(value=png_mag, visible=bool(png_mag)),
        gr.update(value=png_phs, visible=bool(png_phs)),
        llm_analysis_result, fig
    )