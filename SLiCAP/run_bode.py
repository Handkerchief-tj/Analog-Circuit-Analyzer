import sys
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import SLiCAP as sl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# 强制创建必要目录
os.makedirs("./cir", exist_ok=True)
os.makedirs("./html/css", exist_ok=True)
os.makedirs("./img", exist_ok=True)

# 接收命令行传来的扫频参数
start_f = float(sys.argv[1]) if len(sys.argv) > 1 else 0.001
stop_f = float(sys.argv[2]) if len(sys.argv) > 2 else 1000000
points = int(sys.argv[3]) if len(sys.argv) > 3 else 200

sl.initProject("Bode_Analysis")
sl.ini.disp = 0  # 关闭显示

cir = sl.makeCircuit("circuit.cir")
LaplaceResult = sl.doLaplace(cir, pardefs="circuit", numeric=True)

# ================= 核心修复：直接调用底层的 plt 去保存当前画面 =================

# 1. 绘制并保存幅度图
f_dBm = sl.plotSweep("f_dBm", "dB Magnitude plot", LaplaceResult, start_f, stop_f, points,
                     sweepScale="", yUnits="V", funcType="dBmag")
# 使用 plt.savefig 代替 f_dBm.savefig
plt.savefig("./img/f_dBm.png", dpi=300, bbox_inches="tight")
plt.close('all')  # 【极其重要】画完马上关掉当前画板，防止后面的相位图跟幅度图重叠！

# 2. 绘制并保存相位图
f_phs = sl.plotSweep("f_phs", "Phase plot", LaplaceResult, start_f, stop_f, points,
                     sweepScale="", yUnits="V", funcType="phase")
plt.savefig("./img/f_phs.png", dpi=300, bbox_inches="tight")
plt.close('all')  # 同样关闭画板

# =================================================================================

print("波特图 PNG 高清图片绘制完毕！")
