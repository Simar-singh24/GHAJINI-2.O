import re

with open(r'd:\Ghajini-2.O\loading_animation_prompt.txt', 'r', encoding='utf-8') as f:
    text = f.read()

start = text.find('"use client";')
if start == -1:
    start = text.find('LoadingAnimation')
end = text.rfind('];') + 2

ts_code = text[start:end]
ts_code += "\n\n// Expose globally for browser usage\nif (typeof window !== 'undefined') {\n    (window as any).mountLoadingAnimation = mountLoadingAnimation;\n}\n"

with open(r'd:\Ghajini-2.O\backend\app\static\loading-animation.ts', 'w', encoding='utf-8') as out:
    out.write(ts_code)

print("Saved loading-animation.ts successfully, length:", len(ts_code))
