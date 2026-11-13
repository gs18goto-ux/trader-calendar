# 日銀HP「公表予定」から講演・挨拶・記者会見を読み取り、boj_auto.js を作る
# GitHub Actions から毎日実行される（標準ライブラリのみ使用）
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser

URL = "https://www.boj.or.jp/about/calendar/index.htm"
OUT = "boj_auto.js"
KINDS = ("講演", "挨拶", "記者会見", "談話")


class Rows(HTMLParser):
    """table の行ごとにセルの文字列を集める"""

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.in_cell, self.cell = True, []
        elif tag == "br" and self.in_cell:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.in_cell:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.in_cell = False
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (trader-calendar updater)"})
    raw = urllib.request.urlopen(req, timeout=30).read()
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def z2h(s):
    return s.translate(str.maketrans("０１２３４５６７８９：（）", "0123456789:()"))


def main():
    today = (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()
    p = Rows()
    p.feed(fetch())
    events, cur_m, cur_d = [], None, None
    for cells in p.rows:
        cells = [z2h(html.unescape(c)) for c in cells]
        joined = " ".join(cells)
        # 日付（「11月16日(月)」または同じ月の続きで「16日(月)」）
        for c in cells[:2]:
            m = re.search(r"(?:(\d{1,2})\s*月)?\s*(\d{1,2})\s*日\s*\(", c)
            if m:
                if m.group(1):
                    cur_m = int(m.group(1))
                cur_d = int(m.group(2))
                break
        k = re.search(r"【(" + "|".join(KINDS) + r")】\s*(.+)", joined)
        if not k or cur_m is None or cur_d is None:
            continue
        kind, rest = k.group(1), k.group(2).strip()
        t = re.search(r"\b(\d{1,2}):(\d{2})\b", " ".join(cells[:3]))
        time = f"{int(t.group(1)):02d}:{t.group(2)}" if t else None
        # 年の推定（今日より半年以上前の月なら翌年）
        year = today.year
        if cur_m < today.month - 6:
            year += 1
        elif cur_m > today.month + 6:
            year -= 1
        date = f"{year}-{cur_m:02d}-{cur_d:02d}"
        pm = re.match(r"([^(]+?)\s*\((.*)\)\s*$", rest)
        who, place = (pm.group(1).strip(), pm.group(2).strip()) if pm else (rest, "")
        top = ("総裁" in who) and ("審議委員" not in who)
        events.append([date, time, "JST", "boj", "JP", f"{who} {kind}", place, 3 if top else 2, "gov" if top else "member"])

    if not events:
        print("講演・挨拶が見つかりませんでした（ページ構成が変わった可能性）。ファイルは更新しません。")
        return 0
    stamp = (dt.datetime.utcnow() + dt.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
    body = "// 自動生成（update_boj.py）。手で編集しないでください\n"
    body += f"window.TCAL_BOJ_AUTO_UPDATED = {json.dumps(stamp)};\n"
    body += "window.TCAL_BOJ_AUTO = " + json.dumps(events, ensure_ascii=False, indent=1) + ";\n"
    try:
        old = open(OUT, encoding="utf-8").read()
    except FileNotFoundError:
        old = ""
    strip = lambda s: re.sub(r"TCAL_BOJ_AUTO_UPDATED = .*\n", "", s)
    if strip(old) == strip(body):
        print("変更なし")
        return 0
    open(OUT, "w", encoding="utf-8").write(body)
    print(f"{len(events)} 件を書き出しました")
    for e in events:
        print(" ", e[0], e[1] or "未定", e[5], e[6])
    return 0


if __name__ == "__main__":
    sys.exit(main())
