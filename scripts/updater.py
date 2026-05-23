import os
import sys
import time
import subprocess

"""
Uso:
updater.exe <ruta_exe_actual> <ruta_exe_nuevo>
"""

exe_actual = sys.argv[1]
exe_nuevo = sys.argv[2]

time.sleep(2)  # aseguramos que el main ya cerró

os.replace(exe_nuevo, exe_actual)

subprocess.Popen([exe_actual])