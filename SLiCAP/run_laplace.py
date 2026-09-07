import SLiCAP as sl
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
import os
os.chdir(BASE_DIR)

#创建slicap项目
sl.initProject("nmos common source")

cirName = "circuit"
fileName = cirName + ".cir"

dst = "cir"

#创建电路对象
cir = sl.makeCircuit(fileName)

#拉普拉斯变换
result = sl.doLaplace(cir)
gain = result.laplace
sl.htmlPage("Laplace Transfer")
sl.eqn2html("gain", gain)




