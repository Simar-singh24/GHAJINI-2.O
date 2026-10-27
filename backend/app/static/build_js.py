import os

ts_path = r"d:\Ghajini-2.O\backend\app\static\loading-animation.ts"
clean_ts_path = r"d:\Ghajini-2.O\backend\app\static\loading-animation-clean.ts"

with open(ts_path, "r", encoding="utf-8") as f:
    code = f.read()

# Replace React import
code = code.replace('import * as React from "react";', "// vanilla JS engine")

# Remove React component wrapper
p_start = code.find("export interface LoadingAnimationProps")
p_end = code.find("// <data>")
if p_start != -1 and p_end != -1:
    code = code[:p_start] + "\n" + code[p_end:]

with open(clean_ts_path, "w", encoding="utf-8") as f:
    f.write(code)

print("Saved clean TS, size:", len(code))
