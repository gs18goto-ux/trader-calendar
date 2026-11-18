# みんかぶFX「本日の予定／これからの予定【発言・イベント】」と「来週の主な予定」から
# 要人発言・イベントを取り込み、minkabu_auto.js を作る（自分用）。標準ライブラリのみ使用
import datetime as dt
import html
import json
import re
import sys
import urllib.request

BASE = "https://fx.minkabu.jp"
OUT = "minkabu_auto.js"
JST = dt.timezone(dt.timedelta(hours=9))
KEEP_DAYS = 14
# 来週の主な予定（時刻なし）からは、Forex Factory に載りにくい日本関連だけ拾う
JP_WORDS = r"日銀|植田|氷見野|内田|審議委員|国会|首相|財務相|財務大臣|片山|官房長官|経財相|衆院|参院"


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0 (trader-calendar personal)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def links(page_html):
    out = []
    for m in re.finditer(r'<a[^>]*title="([^"]+)"[^>]*href="(/news/\d+)"', page_html):
        out.append((html.unescape(m.group(1)), m.group(2)))
    return out


def article(path):
    h = get(path)
    t = re.search(r"<title>(.*?)</title>", h, re.S)
    title = html.unescape(t.group(1)) if t else ""
    d = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title)
    body = re.search(r'<p class="news__text[^"]*">(.*?)</p>', h, re.S)
    lines = []
    if body:
        for ln in re.split(r"<br\s*/?>", body.group(1)):
            lines.append(html.unescape(re.sub(r"<[^>]+>", "", ln)).replace("　", " ").rstrip())
    return (dt.date(int(d.group(1)), int(d.group(2)), int(d.group(3))) if d else None), lines


def day_of(base, day):
    """base（記事の日付）から見て day 日の日付（月またぎ対応）"""
    for k in range(0, 40):
        x = base + dt.timedelta(days=k)
        if x.day == day:
            return x
    return base


def parse_daily(base, lines):
    items, cur_date, cur_time = [], base, None
    for raw in lines:
        if raw.strip().startswith("※"):
            break
        s = raw.strip()
        if not s:
            cur_time = None  # 空行の後は時刻なしの項目
            continue
        m = re.match(r"^(\d{1,2})日$", s)
        if m:
            cur_date, cur_time = day_of(base, int(m.group(1))), None
            continue
        m = re.match(r"^(?:(\d{1,2})日)?(\d{1,2}):(\d{2})\s*(.+)$", s)
        if m:
            if m.group(1):
                cur_date = day_of(base, int(m.group(1)))
            cur_time = f"{int(m.group(2)):02d}:{m.group(3)}"
            text = m.group(4).strip()
        elif raw[:1] in (" ", "\t", "\u00a0"):
            text = s  # 字下げ行は直前と同じ時刻（空行の後なら時刻なし）
        else:
            cur_time, text = None, s
        d = cur_date if cur_time else base  # 時刻なしの項目は記事の日付に置く
        items.append({"d": d.isoformat(), "t": cur_time, "text": text, "src": "daily", "base": base.isoformat()})
    return items


def parse_weekly(base, lines):
    items, cur = [], None
    for raw in lines:
        s = raw.strip()
        if s.startswith("※"):
            break
        m = re.match(r"^(\d{1,2})日（.）$", s)
        if m:
            cur = day_of(base, int(m.group(1)))
            continue
        if cur and s and not s.startswith("・") and re.search(JP_WORDS, s):
            items.append({"d": cur.isoformat(), "t": None, "text": s, "src": "weekly"})
    return items


def load_old():
    try:
        s = open(OUT, encoding="utf-8").read()
        m = re.search(r"window\.TCAL_MK = (\[.*\]);", s, re.S)
        c = re.search(r"window\.TCAL_MK_COVER = (\[.*?\]);", s, re.S)
        return (json.loads(m.group(1)) if m else []), (json.loads(c.group(1)) if c else [])
    except FileNotFoundError:
        return [], []


def main():
    try:
        lst = links(get("/news?category=statement"))
    except Exception as ex:
        print("一覧を取得できませんでした:", ex)
        return 0
    daily_paths = [p for t, p in lst if re.match(r"^(本日|これから)の予定【発言・イベント】", t)][:2]
    fresh, cover = [], []
    for p in daily_paths:
        try:
            base, lines = article(p)
        except Exception as ex:
            print(p, "取得失敗:", ex)
            continue
        if not base:
            continue
        got = parse_daily(base, lines)
        print(p, base, len(got), "件")
        fresh += got
        cover.append(base.isoformat())
    # 来週の主な予定（毎週土曜朝に掲載）を一覧から探す
    for page in range(1, 26):
        try:
            hit = [(t, p) for t, p in links(get(f"/news?page={page}")) if t.startswith("来週の主な予定")]
        except Exception:
            break
        if hit:
            try:
                base, lines = article(hit[0][1])
                got = parse_weekly(base, lines) if base else []
                print(hit[0][1], "来週の主な予定", len(got), "件")
                fresh += got
            except Exception as ex:
                print("来週の主な予定 取得失敗:", ex)
            break
    if not fresh:
        print("予定が見つからなかったので更新しません")
        return 0
    old, old_cover = load_old()
    cutoff = (dt.datetime.now(JST) - dt.timedelta(days=KEEP_DAYS)).date().isoformat()
    cover_set = sorted({c for c in old_cover + cover if c >= cutoff})
    new_daily_dates = {c for c in cover}
    keep = []
    for e in old:
        if e["d"] < cutoff:
            continue
        # 新しく取れた日の「本日の予定」は入れ替える（変更・取り消しを反映）
        if e["src"] == "daily" and e.get("base") in new_daily_dates:
            continue
        if e["src"] == "weekly":
            continue  # 来週の予定は毎回取り直す
        keep.append(e)
    merged, seen = [], set()
    for e in keep + fresh:
        k = (e["d"], e["t"], e["text"])
        if k in seen:
            continue
        seen.add(k)
        merged.append(e)
    merged.sort(key=lambda e: (e["d"], e["t"] or "99"))
    stamp = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    body = "// 自動生成（update_minkabu.py）。出典: みんかぶFX。自分用。手で編集しないでください\n"
    body += f"window.TCAL_MK_UPDATED = {json.dumps(stamp)};\n"
    body += "window.TCAL_MK_COVER = " + json.dumps(cover_set) + ";\n"
    body += "window.TCAL_MK = " + json.dumps(merged, ensure_ascii=False, separators=(",", ":")) + ";\n"
    try:
        prev = open(OUT, encoding="utf-8").read()
    except FileNotFoundError:
        prev = ""
    strip = lambda s: re.sub(r"TCAL_MK_UPDATED = .*\n", "", s)
    if strip(prev) == strip(body):
        print("変更なし")
        return 0
    open(OUT, "w", encoding="utf-8").write(body)
    print(len(merged), "件を書き出しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
