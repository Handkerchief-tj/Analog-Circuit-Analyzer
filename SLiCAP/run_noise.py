import SLiCAP as sl
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
import os
os.chdir(BASE_DIR)

sl.initProject("Noise Analysis")
sl.ini.disp = 0

cir = sl.makeCircuit("circuit.cir")
result = sl.doNoise(cir, source="circuit", detector="circuit", pardefs="circuit", numeric=True)
sl.htmlPage("Noise Analysis")
sl.noise2html(result)
sl.eqn2html("S_out", result.onoise)
if result.inoise != None:
    sl.eqn2html("S_in", result.inoise)
