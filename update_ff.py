# Forex Factory の週間カレンダー（公式配布データ）を取り込み、ff_auto.js を作る
# 自分用。配布版では正式なAPIに差し替えること。標準ライブラリのみ使用
import datetime as dt
import json
import re
import sys
import urllib.request

FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",  # 無ければ無視
]
OUT = "ff_auto.js"
KEEP_DAYS = 14  # 過去何日分を残すか
JST = dt.timezone(dt.timedelta(hours=9))
STAR = {"High": 3, "Medium": 2, "Low": 1, "Non-Economic": 1}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (trader-calendar personal)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_old():
    try:
        s = open(OUT, encoding="utf-8").read()
        m = re.search(r"window\.TCAL_FF = (\[.*\]);", s, re.S)
        return json.loads(m.group(1)) if m else []
    except FileNotFoundError:
        return []


def convert(item):
    raw = item.get("date") or ""
    try:
        t = dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(JST)
    except ValueError:
        return None
    impact = item.get("impact") or ""
    title = (item.get("title") or "").strip()
    return {
        # 休日は元の日付のまま（日本時間に直すと日付がずれるため）
        "d": raw[:10] if impact == "Holiday" else t.strftime("%Y-%m-%d"),
        "t": None if impact == "Holiday" else t.strftime("%H:%M"),
        "cc": (item.get("country") or "").upper(),
        "title": title,
        "imp": impact,
        "star": STAR.get(impact, 1),
        "fc": (item.get("forecast") or "").strip(),
        "pv": (item.get("previous") or "").strip(),
        "hol": impact == "Holiday",
    }


def main():
    fresh, ok = [], False
    for url in FEEDS:
        try:
            data = get(url)
            ok = True
            fresh += [e for e in (convert(x) for x in data) if e]
            print(url, len(data), "件")
        except Exception as ex:  # 来週分などは無いことがある
            print(url, "取得できませんでした:", ex)
    if not ok or not fresh:
        print("データが取れなかったので更新しません")
        return 0
    key = lambda e: f'{e["d"]}|{e["t"]}|{e["cc"]}|{e["title"]}'
    cutoff = (dt.datetime.now(JST) - dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    fresh_days = {e["d"] for e in fresh}
    merged = {}
    # 古いデータは、今回取れた日付に含まれない日のものだけ残す（予定の変更・削除を反映するため）
    for e in load_old():
        if e["d"] >= cutoff and e["d"] not in fresh_days:
            merged[key(e)] = e
    for e in fresh:
        merged[key(e)] = e
    events = sorted(merged.values(), key=lambda e: (e["d"], e["t"] or ""))
    body = "// 自動生成（update_ff.py）。出典: Forex Factory 週間カレンダー。手で編集しないでください\n"
    stamp = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    body += f"window.TCAL_FF_UPDATED = {json.dumps(stamp)};\n"
    body += "window.TCAL_FF = " + json.dumps(events, ensure_ascii=False, separators=(",", ":")) + ";\n"
    try:
        old = open(OUT, encoding="utf-8").read()
    except FileNotFoundError:
        old = ""
    strip = lambda s: re.sub(r"TCAL_FF_UPDATED = .*\n", "", s)
    if strip(old) == strip(body):
        print("変更なし")
        return 0
    open(OUT, "w", encoding="utf-8").write(body)
    print(len(events), "件を書き出しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
