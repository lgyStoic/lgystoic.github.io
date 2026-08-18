"""聚合 deep/out/<id>.json 逐小区画像 -> profile.json / profile.csv，并统计字段覆盖率。"""
import json, os, glob, re, csv
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
cand = {r["id"]: r for r in json.load(open(os.path.join(BASE, "cand_l2.json")))}
screen = {r["id"]: r for r in json.load(open(os.path.join(BASE, "screen.json")))}

deep = {}
bad = []
for f in glob.glob(os.path.join(BASE, "deep", "out", "*.json")):
    try:
        d = json.load(open(f))
    except Exception as e:
        bad.append((os.path.basename(f), str(e)))
        continue
    fid = int(os.path.basename(f)[:-5])
    if d.get("id") != fid:
        bad.append((os.path.basename(f), f"id字段={d.get('id')} 与文件名不符"))
    deep[fid] = d

print(f"已落盘 {len(deep)}/{len(cand)}")
if bad:
    print("异常文件:", bad)
missing = sorted(set(cand) - set(deep))
if missing:
    print(f"未完成 {len(missing)}: {[cand[i]['name'] for i in missing][:20]}")

UNK = re.compile(r"^\s*(未知|未查实|未查|无法|不详|N/?A)\s*$|^未知")

def norm_verdict(v):
    """agent 常写成长句，取开头的类别词归一化为四选一。"""
    s = str(v or "").strip()
    if not s:
        return "未知"
    for key in ("大户型为主", "中大户型为主", "中小户型为主", "户型跨度大", "未知"):
        if s.startswith(key):
            return "中大户型为主" if key == "中大户型为主" else key
    if "大户型为主" in s:
        return "大户型为主"
    if "中小户型为主" in s:
        return "中小户型为主"
    if "跨度" in s:
        return "户型跨度大"
    return "未知"

# 深圳特色：「四房」与「≥120㎡」是两个不同的筛子（小面积多房很常见）
FOUR = re.compile(r"([四4五5六6七7八8])\s*房|([4-8])\s*室")
def big_by_rooms(layouts):
    """户型清单里是否存在四房及以上。"""
    return any(FOUR.search(str(x.get("rooms", ""))) for x in (layouts or []))

AREA = re.compile(r"(\d{2,4}(?:\.\d+)?)\s*㎡")
def max_area(layouts):
    """户型清单里出现过的最大建面。"""
    vals = []
    for x in (layouts or []):
        vals += [float(m) for m in AREA.findall(str(x.get("area", "")))]
    vals = [v for v in vals if 20 <= v <= 2000]
    return max(vals) if vals else None

def has(v):
    """字段是否算'查到了'——纯'未知'开头的算没查到。"""
    if not v or not str(v).strip():
        return False
    return not UNK.match(str(v).strip())

FIELDS = ["units_total", "residents_est", "parking", "parking_ratio",
          "large_share", "layout_verdict", "resettlement_detail",
          "school_primary", "school_middle"]

rows = []
for i in sorted(cand):
    c = cand[i]
    s = screen.get(i, {})
    d = deep.get(i, {})
    lay = d.get("layouts") or []
    rows.append({
        "id": i,
        "name": c["name"],
        "district": c["district"],
        "street": c["street"],
        "station": c["station"],
        "lines": c["lines"],
        "d_m": c["d_m"],
        "area_m2": c["area_m2"],
        "built_year": s.get("built_year", ""),
        "type": s.get("type", ""),
        "units_total": d.get("units_total", ""),
        "residents_est": d.get("residents_est", ""),
        "parking": d.get("parking", ""),
        "parking_ratio": d.get("parking_ratio", ""),
        "layouts": lay,
        "layouts_txt": " / ".join(
            f"{x.get('rooms','?')} {x.get('area','?')}" + (f" [{x['share']}]" if x.get("share") and not UNK.match(str(x['share'])) else "")
            for x in lay),
        "large_share": d.get("large_share", ""),
        "layout_verdict_raw": d.get("layout_verdict", ""),
        "layout_verdict": norm_verdict(d.get("layout_verdict", "")),
        "has_4room": "有" if big_by_rooms(lay) else ("未知" if not lay else "无"),
        "max_area": max_area(lay),
        "resettlement_detail": d.get("resettlement_detail", ""),
        "school_primary": d.get("school_primary", ""),
        "school_middle": d.get("school_middle", ""),
        "school_note": d.get("school_note", ""),
        "confidence": d.get("confidence", ""),
        "field_gaps": d.get("field_gaps", ""),
        "sources": d.get("sources", []),
        "done": i in deep,
    })

json.dump(rows, open(os.path.join(BASE, "profile.json"), "w"), ensure_ascii=False, indent=1)

done = [r for r in rows if r["done"]]
if done:
    print("\n=== 字段覆盖率（已完成的小区中，非'未知'的比例）===")
    for f in FIELDS:
        n = sum(1 for r in done if has(r[f]))
        print(f"  {f:20s} {n:3d}/{len(done)}  {n/len(done)*100:5.1f}%")
    n = sum(1 for r in done if r["layouts"])
    print(f"  {'layouts':20s} {n:3d}/{len(done)}  {n/len(done)*100:5.1f}%")

    print("\n=== 户型判定（归一化）===", dict(Counter(r["layout_verdict"] for r in done)))
    print("=== 有四房及以上户型 ===", dict(Counter(r["has_4room"] for r in done)))
    ma = [r for r in done if r["max_area"]]
    print(f"=== 最大建面 ≥120㎡ 的: {sum(1 for r in ma if r['max_area']>=120)}/{len(ma)}"
          f"  ≥140㎡: {sum(1 for r in ma if r['max_area']>=140)}")
    # 两个口径的交叉表：有四房 × 最大面积≥120
    cross = Counter((r["has_4room"], "≥120㎡" if (r["max_area"] or 0) >= 120 else "<120㎡") for r in done)
    print("=== 交叉（四房口径 × 面积口径）===", dict(cross))
    print("=== 置信度 ===", dict(Counter(str(r["confidence"])[:4] for r in done)))

    # 车位比数值化
    def pr(v):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:÷|/)\s*[\d,]+\s*户?\s*=\s*(\d+\.\d+)", str(v))
        if m:
            return float(m.group(2))
        m = re.match(r"\s*(\d+\.\d+)", str(v))
        return float(m.group(1)) if m else None
    vals = [(r["name"], pr(r["parking_ratio"])) for r in done]
    vals = [(n, v) for n, v in vals if v is not None and 0 < v < 5]
    if vals:
        vals.sort(key=lambda x: x[1])
        print(f"\n=== 车位比（{len(vals)} 个可数值化）===")
        print("  最低5:", ", ".join(f"{n} {v:.2f}" for n, v in vals[:5]))
        print("  最高5:", ", ".join(f"{n} {v:.2f}" for n, v in vals[-5:]))
        import statistics
        print(f"  中位数 {statistics.median(v for _, v in vals):.2f}")

cols = ["id", "name", "district", "street", "station", "lines", "d_m", "area_m2",
        "built_year", "units_total", "residents_est", "parking", "parking_ratio",
        "layouts_txt", "large_share", "layout_verdict", "resettlement_detail",
        "school_primary", "school_middle", "school_note", "confidence", "field_gaps"]
with open(os.path.join(BASE, "profile.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
print("\n写出 profile.json / profile.csv")
