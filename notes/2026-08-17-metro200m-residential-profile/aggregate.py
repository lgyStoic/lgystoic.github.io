"""聚合 14 批粗筛结果 -> screen.json + screen.csv，并做完整性/一致性检查。"""
import json, os, glob, re
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
allrows = {r["id"]: r for r in json.load(open(os.path.join(BASE, "all461.json")))}

merged = {}
dupes = []
for f in sorted(glob.glob(os.path.join(BASE, "batches", "out_b*.json"))):
    d = json.load(open(f))
    items = d.get("items", d) if isinstance(d, dict) else d
    for it in items:
        i = it.get("id")
        if i in merged:
            dupes.append(i)
        merged[i] = it

missing = sorted(set(allrows) - set(merged))
print(f"批次文件: {len(glob.glob(os.path.join(BASE,'batches','out_b*.json')))}")
print(f"已覆盖: {len(merged)}/461  缺失 {len(missing)}: {missing}")
if dupes:
    print("重复 id:", dupes)

# 名称一致性核查（防止 agent 张冠李戴到别的 id）
mismatch = [i for i in merged if merged[i].get("name") != allrows.get(i, {}).get("name")]
if mismatch:
    print(f"名称与原表不符 {len(mismatch)} 条:")
    for i in mismatch[:20]:
        print(f"  id={i} agent={merged[i].get('name')!r} orig={allrows.get(i,{}).get('name')!r}")

out = []
for i in sorted(allrows):
    base = allrows[i]
    s = merged.get(i, {})
    out.append({
        **base,
        "type": s.get("type", "未查"),
        "built_year": s.get("built_year", "未查"),
        "units_total": s.get("units_total", "未查"),
        "buildings": s.get("buildings", "未查"),
        "layout_main": s.get("layout_main", "未查"),
        "large_unit": s.get("large_unit", "未查"),
        "resettlement": s.get("resettlement", "未查"),
        "confidence": s.get("confidence", "未查"),
        "note": s.get("note", ""),
        "sources": s.get("sources", []),
    })
json.dump(out, open(os.path.join(BASE, "screen.json"), "w"), ensure_ascii=False, indent=1)

print("\n=== 性质分布 ===")
for k, v in Counter(r["type"] for r in out).most_common():
    print(f"  {k}: {v}")
print("=== 置信度 ===", dict(Counter(r["confidence"] for r in out)))
print("=== 大户型为主 ===", dict(Counter(r["large_unit"] for r in out)))
print("=== 回迁房 ===", dict(Counter(r["resettlement"] for r in out)))

def year_of(s):
    m = re.findall(r"(19|20)\d{2}", str(s))
    return int(str(s)[str(s).find(m[0]):][:4]) if m else None

for r in out:
    r["_year"] = year_of(r["built_year"])
have = [r for r in out if r["_year"]]
print(f"\n有年份: {len(have)}  2002年后: {sum(1 for r in have if r['_year']>=2002)}")

# CSV
import csv
cols = ["id", "name", "district", "street", "station", "lines", "d_m", "area_m2",
        "type", "built_year", "units_total", "buildings", "layout_main",
        "large_unit", "resettlement", "confidence", "note"]
with open(os.path.join(BASE, "screen.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in out:
        w.writerow(r)
print("\n写出 screen.json / screen.csv")

# ---- 第二层候选筛选 ----
RES_OK = {"住宅小区", "混合", "安居房人才房"}
cand = []
for r in out:
    if r["type"] not in RES_OK:
        continue
    y = r["_year"]
    if y and y < 2002:
        continue
    big = r["large_unit"] in ("是", "部分", "未知")
    if not big:
        continue
    cand.append(r)
cand.sort(key=lambda r: (r["district"], -r["area_m2"]))
print(f"\n=== 第二层候选（住宅性质 + 2002后/年份未知 + 大户型是/部分/未知）: {len(cand)} ===")
print(dict(Counter(r["district"] for r in cand)))
json.dump(cand, open(os.path.join(BASE, "cand_l2.json"), "w"), ensure_ascii=False, indent=1)
