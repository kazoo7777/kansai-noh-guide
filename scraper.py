#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
関西・全国の能楽（能・狂言）公演情報を公式サイト等から自動収集するスクリプト。
Python標準ライブラリのみで動作するため、追加インストールは不要です。

出力先:
  - data/performances.json (JSON形式のデータ)
  - data/performances.js   (HTMLを直接開いた場合でも読み込めるJS形式のデータ)
"""

import datetime
import hashlib
import html
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# 出力ディレクトリ設定
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# HTTPリクエスト用の共通設定
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KansaiNohGuideBot/1.0; +local-personal-use)",
    "Accept-Language": "ja,en;q=0.8",
}
SSL_CTX = ssl.create_default_context()

# 曜日表記
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

# 関西6府県
KANSAI_PREFS = {"大阪", "京都", "兵庫", "奈良", "滋賀", "和歌山"}

# 会場名・テキストから都道府県を推定するためのキーワード辞書
# ※「東京都」に「京都」が含まれる誤判定を防ぐため、東京を京都より先に判定する
PREF_KEYWORDS = [
    ("東京", ["東京都", "東京", "国立能楽堂", "観世能楽堂", "宝生能楽堂", "喜多能楽堂", "矢来能楽堂", "セルリアンタワー", "梅若能楽学院", "銕仙会", "渋谷", "新宿", "銀座", "千駄ヶ谷", "水道橋", "神楽坂", "目黒", "世田谷", "港区", "中央区", "千代田区", "小金井", "八王子"]),
    ("大阪", ["大阪府", "大阪市", "大阪", "大槻能楽堂", "山本能楽堂", "朝陽会館", "堺", "吹田", "豊中", "高槻", "枚方", "天王寺", "難波", "中之島", "住吉"]),
    ("京都", ["京都府", "京都市", "京都", "京都観世会館", "金剛能楽堂", "河村能舞台", "大江能楽堂", "嘉祥閣", "宇治", "平安神宮", "岡崎", "烏丸", "北野"]),
    ("兵庫", ["兵庫県", "兵庫", "神戸", "西宮", "西宮能楽堂", "湊川神社", "神能殿", "芦屋", "姫路", "宝塚", "明石", "尼崎", "伊丹", "淡路"]),
    ("奈良", ["奈良県", "奈良", "春日大社", "興福寺", "東大寺", "長谷寺", "薬師寺", "橿原", "法隆寺", "奈良公園"]),
    ("滋賀", ["滋賀県", "滋賀", "大津市伝統芸能会館", "大津", "彦根", "琵琶湖", "びわ湖", "長浜", "草津"]),
    ("和歌山", ["和歌山県", "和歌山", "高野山", "熊野", "那智", "紀三井寺", "白浜"]),
    ("神奈川", ["神奈川", "横浜", "横浜能楽堂", "鎌倉", "鎌倉能舞台", "川崎", "藤沢", "小田原"]),
    ("愛知", ["愛知", "名古屋", "名古屋能楽堂", "熱田", "豊田", "岡崎市"]),
    ("石川", ["石川", "金沢", "石川県立能楽堂"]),
    ("福岡", ["福岡", "大濠公園能楽堂", "博多", "北九州", "太宰府"]),
    ("広島", ["広島", "厳島", "宮島", "福山"]),
    ("宮城", ["宮城", "仙台"]),
    ("北海道", ["北海道", "札幌"]),
    ("静岡", ["静岡", "浜松", "伊豆"]),
    ("長野", ["長野", "松本", "軽井沢"]),
    ("新潟", ["新潟", "佐渡"]),
    ("岡山", ["岡山", "倉敷", "後楽園"]),
    ("三重", ["三重", "伊勢", "伊賀", "津市"]),
    ("高知", ["高知", "土佐"]),
    ("香川", ["香川", "高松", "金刀比羅"]),
    ("愛媛", ["愛媛", "松山"]),
    ("熊本", ["熊本"]),
    ("沖縄", ["沖縄", "那覇"]),
]


def fetch_text(url: str, timeout: int = 15) -> str:
    """指定URLからHTML/XMLテキストを取得します。"""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        raw = resp.read()
        # 文字コードを推定してデコード
        for enc in ("utf-8", "cp932", "euc-jp"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")


def clean_html(raw_html: str) -> str:
    """HTMLタグを除去し、見やすいプレーンテキストに整形します。"""
    if not raw_html:
        return ""
    text = re.sub(r"<!--.*?-->", "", raw_html, flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|li|tr|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("-->", "").replace("<!--", "")
    text = html.unescape(text)
    # 連続する空白・改行を整理
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def clean_inline(raw_html: str) -> str:
    """HTMLタグを除去して1行の文字列にします。"""
    return re.sub(r"\s+", " ", clean_html(raw_html)).strip()


def format_date_label(date_str: str) -> str:
    """YYYY-MM-DD を '2026年12月5日(土)' 形式に変換します。"""
    try:
        dt = datetime.date.fromisoformat(date_str)
        wd = WEEKDAYS_JA[dt.weekday()]
        return f"{dt.year}年{dt.month}月{dt.day}日({wd})"
    except ValueError:
        return date_str


def detect_prefecture(venue: str, extra_text: str = "", default_pref: str = "その他") -> str:
    """会場名や説明文から都道府県を判定します。"""
    combined = f"{venue} {extra_text}"
    # まず会場名だけでチェック（誤判定を防ぐため優先）
    for pref, keywords in PREF_KEYWORDS:
        for kw in keywords:
            if kw in venue:
                return pref
    # 次に全体テキストでチェック
    for pref, keywords in PREF_KEYWORDS:
        for kw in keywords:
            if kw in combined:
                return pref
    return default_pref


def make_item(
    title: str,
    date_str: str,
    venue: str,
    url: str,
    source: str,
    time_str: str = "",
    programs=None,
    price: str = "",
    tags=None,
    summary: str = "",
    image: str = "",
    default_pref: str = "その他",
) -> dict:
    """公演データ1件を統一フォーマットの辞書にまとめます。"""
    pref = detect_prefecture(venue, f"{title} {summary}", default_pref=default_pref)
    region = "関西" if pref in KANSAI_PREFS else "全国"
    uid = hashlib.md5(f"{source}|{date_str}|{venue}|{title}".encode("utf-8")).hexdigest()[:12]
    return {
        "id": uid,
        "title": title.strip(),
        "date": date_str,
        "dateLabel": format_date_label(date_str),
        "time": time_str.strip(),
        "venue": venue.strip(),
        "prefecture": pref,
        "region": region,
        "programs": [p.strip() for p in (programs or []) if p and p.strip()],
        "price": price.strip(),
        "tags": list(dict.fromkeys([t.strip() for t in (tags or []) if t and t.strip()])),
        "summary": summary.strip()[:300],
        "url": url.strip(),
        "source": source,
        "image": image.strip(),
    }


def iter_upcoming_months(count: int = 3):
    """今月から指定月数分の (年, 月) タプルを返します。"""
    today = datetime.date.today()
    y, m = today.year, today.month
    for _ in range(count):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


# ============================================================
# 各サイトの収集パーサー
# ============================================================

def scrape_otsuki() -> list:
    """大槻能楽堂（大阪）の公演スケジュールを取得します。"""
    items = []
    for y, m in iter_upcoming_months(3):
        url = f"https://noh-kyogen.com/schedule/?cal_year={y}&cal_month={m}"
        page = fetch_text(url)
        # id="event-xxxx" の詳細ブロックを抽出
        blocks = re.findall(
            r'<div class="details" id="(event-\d+)">(.*?)</div>\s*(?=<div class="details"|</div>\s*</div>)',
            page,
            flags=re.S,
        )
        # フォールバック分割
        if not blocks:
            parts = re.split(r'<div class="details" id="(event-\d+)">', page)
            for i in range(1, len(parts) - 1, 2):
                blocks.append((parts[i], parts[i + 1]))

        for ev_id, block in blocks:
            rows = re.findall(
                r'<div class="label">(.*?)</div>\s*<div class="content value">(.*?)</div>',
                block,
                flags=re.S,
            )
            info = {clean_inline(k): clean_html(v) for k, v in rows}
            title = info.get("イベントタイトル", "").replace("\n", " ")
            raw_date = info.get("月日", "")
            dm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw_date)
            if not dm or not title:
                continue
            date_str = f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
            time_str = info.get("時間", "").replace("\n", " ")
            content = info.get("内容", "")
            programs = [line for line in content.splitlines() if line][:8]
            price = info.get("料金", "").replace("\n", " / ")
            img_m = re.search(r'<img[^>]+src="([^"]+)"', block)
            img = img_m.group(1) if img_m else ""

            items.append(
                make_item(
                    title=title,
                    date_str=date_str,
                    venue="大槻能楽堂",
                    url=f"{url}#{ev_id}",
                    source="大槻能楽堂",
                    time_str=time_str,
                    programs=programs,
                    price=price[:160],
                    tags=["大槻能楽堂"],
                    summary=content.replace("\n", " "),
                    image=img,
                    default_pref="大阪",
                )
            )
        time.sleep(0.3)
    return items


def scrape_kongo() -> list:
    """金剛能楽堂（京都）の公演スケジュールを取得します。"""
    items = []
    for y, m in iter_upcoming_months(3):
        url = f"https://kongou-net.com/schedule/{y}{m:02d}.html"
        try:
            page = fetch_text(url)
        except Exception:
            continue
        blocks = re.split(r'<div class="details-box">', page)[1:]
        for block in blocks:
            day_m = re.search(r'<div class="day">\s*<p>(.*?)</p>', block, flags=re.S)
            if not day_m:
                continue
            dm = re.search(r"(\d{1,2})\s*日", clean_inline(day_m.group(1)))
            if not dm:
                continue
            date_str = f"{y:04d}-{m:02d}-{int(dm.group(1)):02d}"

            title_m = re.search(r"<h3>(.*?)</h3>", block, flags=re.S)
            title = clean_inline(title_m.group(1)) if title_m else ""
            if not title:
                continue

            venue_m = re.search(r'<span class="label">会場</span>(.*?)(?:<br|</p>)', block, flags=re.S)
            venue = clean_inline(venue_m.group(1)) if venue_m else "金剛能楽堂"

            time_m = re.search(r'<span class="label">時間</span>(.*?)(?:<br|</p>)', block, flags=re.S)
            time_str = clean_inline(time_m.group(1)) if time_m else ""

            # 演目リスト（最初の<ul>）
            uls = re.findall(r"<ul>(.*?)</ul>", block, flags=re.S)
            programs = []
            price_parts = []
            if uls:
                for li in re.findall(r"<li>(.*?)</li>", uls[0], flags=re.S):
                    t = clean_inline(li)
                    if t:
                        programs.append(t)
            if len(uls) > 1:
                for li in re.findall(r"<li>(.*?)</li>", uls[1], flags=re.S):
                    t = clean_inline(li)
                    if t and "お問い合わせ" not in t:
                        price_parts.append(t)

            items.append(
                make_item(
                    title=title,
                    date_str=date_str,
                    venue=venue or "金剛能楽堂",
                    url=url,
                    source="金剛能楽堂",
                    time_str=time_str,
                    programs=programs[:8],
                    price=" / ".join(price_parts)[:160],
                    tags=["金剛流", "金剛能楽堂"],
                    summary=" / ".join(programs),
                    default_pref="京都",
                )
            )
        time.sleep(0.3)
    return items


def scrape_kyoto_kanze() -> list:
    """京都観世会館（京都）のイベントカレンダーから公演を取得します。"""
    # 相対リンク（../xxxx/）を正しく解決するため末尾スラッシュを付ける
    url = "https://kyoto-kanze.jp/show_info/schedule/"
    page = fetch_text(url)
    items = []
    # 月ごとのブロック（<h1>YYYY年M月</h1>）で分割
    month_blocks = re.split(r"<h1>(\d{4})年(\d{1,2})月</h1>", page)
    for i in range(1, len(month_blocks) - 2, 3):
        y = int(month_blocks[i])
        m = int(month_blocks[i + 1])
        body = month_blocks[i + 2]

        # 各日のセル（cell-a）を分割して抽出
        cells = re.split(r'<div class="cell-a[^"]*">', body)[1:]
        for cell in cells:
            day_m = re.search(r'<span class="yohaku">\s*(\d{1,2})\s*</span>', cell)
            if not day_m:
                continue
            d = int(day_m.group(1))
            date_str = f"{y:04d}-{m:02d}-{d:02d}"

            # セル内の各公演
            ev_divs = re.findall(r'<div class="carender_detail_([RYG])[^"]*">(.*?)</div>', cell, flags=re.S)
            for kind, inner in ev_divs:
                title = clean_inline(inner)
                if not title or "休館" in title:
                    continue
                link_m = re.search(r'href="([^"]+)"', inner)
                ev_url = urllib.parse.urljoin(url, link_m.group(1).strip()) if link_m else url
                kind_tag = {
                    "R": "京都観世会自主公演",
                    "Y": "有料公演",
                    "G": "無料公演",
                }.get(kind, "")
                items.append(
                    make_item(
                        title=title,
                        date_str=date_str,
                        venue="京都観世会館",
                        url=ev_url,
                        source="京都観世会館",
                        tags=[t for t in ["観世流", kind_tag] if t],
                        summary=f"京都観世会館での{kind_tag or '公演'}です。",
                        default_pref="京都",
                    )
                )
    return items


def scrape_yamamoto() -> list:
    """山本能楽堂（大阪）の公演一覧を取得します。"""
    url = "https://www.noh-theater.com/schedule.php"
    page = fetch_text(url)
    items = []
    # scheduledetails.php?id=... のリンクブロックを抽出
    cards = re.findall(
        r'<a href="(scheduledetails\.php\?id=\d+)"[^>]*>(.*?)</a>',
        page,
        flags=re.S,
    )
    for rel_url, card in cards:
        full_url = urllib.parse.urljoin(url, rel_url)
        ps = [clean_inline(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", card, flags=re.S)]
        ps = [p for p in ps if p]
        if len(ps) < 2:
            continue

        # カテゴリ・タイトル・日時を抽出
        cats = []
        title = ""
        date_str = ""
        time_str = ""
        for p in ps:
            dm = re.search(r"日時[：:]\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(.*)", p)
            if dm:
                date_str = f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                time_str = dm.group(4).strip()
            elif not title and ("・" in p and len(p) < 45 and ("主催" in p or "能・狂言" in p or "古典芸能" in p or "体験" in p)):
                cats = [c.strip() for c in p.split("・") if c.strip()]
            elif not title and len(p) >= 4:
                title = p

        if not title or not date_str:
            continue

        img_m = re.search(r'<img[^>]+src="([^"]+)"', card)
        img = urllib.parse.urljoin(url, img_m.group(1)) if img_m else ""
        tags = cats[:3]
        if "初心者" in title:
            tags.append("初心者向け")

        items.append(
            make_item(
                title=title,
                date_str=date_str,
                venue="山本能楽堂",
                url=full_url,
                source="山本能楽堂",
                time_str=time_str,
                tags=tags,
                summary=" / ".join(ps[2:4]),
                image=img,
                default_pref="大阪",
            )
        )
    return items


def scrape_nishinomiya() -> list:
    """西宮能楽堂（兵庫）の公演案内を取得します。"""
    url = "https://nishinomiya-noh.jp/schedule/"
    page = fetch_text(url)
    items = []
    blocks = re.split(r'<div class="schedule-each">', page)[1:]
    for block in blocks:
        link_m = re.search(r'<a[^>]+href="([^"]+)"', block)
        ev_url = link_m.group(1) if link_m else url
        title_m = re.search(r'<h3 class="schedule-each-title">(.*?)</h3>', block, flags=re.S)
        text_m = re.search(r'<p class="schedule-text">(.*?)</p>', block, flags=re.S)
        if not title_m:
            continue
        title = clean_inline(title_m.group(1))
        desc = clean_inline(text_m.group(1)) if text_m else ""

        # 日付抽出（本文優先、なければタイトル）
        dm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", desc) or re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", title)
        if not dm:
            continue
        date_str = f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

        tm = re.search(r"(\d{1,2}時(?:\d{1,2}分)?開演(?:（[^）]+）)?)", desc)
        time_str = tm.group(1) if tm else ""

        img_m = re.search(r"background-image:\s*url\(([^)]+)\)", block)
        img = img_m.group(1).strip("'\"") if img_m else ""

        items.append(
            make_item(
                title=title,
                date_str=date_str,
                venue="西宮能楽堂",
                url=ev_url,
                source="西宮能楽堂",
                time_str=time_str,
                tags=["西宮能楽堂"],
                summary=desc,
                image=img,
                default_pref="兵庫",
            )
        )
    return items


def scrape_nohgaku_assoc() -> list:
    """公益社団法人 能楽協会の公式RSSから主催公演を取得します。"""
    url = "https://www.nohgaku.or.jp/performance/rss.xml"
    xml_text = fetch_text(url)
    root = ET.fromstring(xml_text)
    items = []
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc_html = item.findtext("content:encoded", default="", namespaces=ns) or item.findtext("description") or ""
        desc = clean_html(desc_html)
        if not title or not link:
            continue

        # 公演日を本文から探索（複数パターン対応）
        dm = (
            re.search(r"(?:202\d)年\s*(\d{1,2})月\s*(\d{1,2})日", desc)
            or re.search(r"(202\d)[./-](\d{1,2})[./-](\d{1,2})", desc)
        )
        if dm:
            if len(dm.groups()) == 2:
                ym = re.search(r"(202\d)年\s*\d{1,2}月\s*\d{1,2}日", desc)
                year = int(ym.group(1)) if ym else datetime.date.today().year
                date_str = f"{year:04d}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}"
            else:
                date_str = f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
        else:
            # URLから年月を推定（例: _202612）
            um = re.search(r"(202\d)(\d{2})", link)
            if not um:
                continue
            date_str = f"{um.group(1)}-{um.group(2)}-01"

        # 会場の簡易抽出
        vm = re.search(r"(?:会場|場所|於)[：:\s]*([^\n。、]+)", desc)
        venue = vm.group(1).strip() if vm else "公式サイト参照"
        img_m = re.search(r'<img[^>]+src="([^"]+)"', desc_html)
        img = img_m.group(1) if img_m else ""

        items.append(
            make_item(
                title=title,
                date_str=date_str,
                venue=venue,
                url=link,
                source="能楽協会",
                tags=["能楽協会主催"],
                summary=desc.replace("\n", " "),
                image=img,
                default_pref="その他",
            )
        )
    return items


def parse_jp_date(text: str) -> str:
    """西暦または和暦（令和）の日付文字列から YYYY-MM-DD を抽出します。"""
    if not text:
        return ""
    # 西暦 (2026年12月5日 / 2026/12/5 / 2026-12-5)
    m = re.search(r"(202\d)\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 令和 (令和8年11月29日 / 令和9年1月10日)
    m = re.search(r"令和\s*(\d{1,2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        year = 2018 + int(m.group(1))
        return f"{year:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def scrape_minatogawa() -> list:
    """湊川神社 神能殿（兵庫・神戸）の公演情報一覧を取得します。"""
    url = "https://www.minatogawajinja.or.jp/shinnouden/event/"
    page = fetch_text(url)
    items = []
    articles = re.findall(r'<article class="c-eventSummary[^"]*">(.*?)</article>', page, flags=re.S)
    for art in articles:
        link_m = re.search(r'href="([^"]+)"', art)
        title_m = re.search(r'<h3 class="c-eventSummary__ttl">(.*?)</h3>', art, flags=re.S)
        period_m = re.search(r'<span class="c-eventSummary__period">(.*?)</span>', art, flags=re.S)
        cat_m = re.search(r'<figcaption class="c-eventSummary__cat"[^>]*>(.*?)</figcaption>', art, flags=re.S)
        ex_m = re.search(r'<span class="c-eventSummary__excerpt">(.*?)</span>', art, flags=re.S)
        img_m = re.search(r'<img[^>]+src="([^"]+)"', art)

        if not title_m or not period_m:
            continue
        title = clean_inline(title_m.group(1))
        date_str = parse_jp_date(clean_inline(period_m.group(1)))
        if not title or not date_str:
            continue

        cat = clean_inline(cat_m.group(1)) if cat_m else ""
        excerpt = clean_inline(ex_m.group(1)) if ex_m else ""
        tags = ["湊川神社 神能殿"]
        if cat:
            tags.append(cat)

        items.append(
            make_item(
                title=title,
                date_str=date_str,
                venue="湊川神社 神能殿",
                url=link_m.group(1) if link_m else url,
                source="湊川神社 神能殿",
                tags=tags,
                summary=excerpt,
                image=img_m.group(1) if img_m else "",
                default_pref="兵庫",
            )
        )
    return items


def scrape_choyo() -> list:
    """朝陽会館（大阪・大阪天満宮前）の公演・イベント一覧を取得します。"""
    url = "https://choyokaikan.com/event-lists/"
    page = fetch_text(url)
    items = []
    cards = re.split(r'<div class="blog-card">', page)[1:]
    for card in cards:
        title_m = re.search(r'<span class="post-title">\s*<a href="([^"]+)">(.*?)</a>', card, flags=re.S)
        date_m = re.search(r"上演日[:：]\s*([^<]+)", card)
        if not title_m or not date_m:
            continue
        ev_url = title_m.group(1).strip()
        title = clean_inline(title_m.group(2))
        date_str = parse_jp_date(clean_inline(date_m.group(1)))
        if not title or not date_str:
            continue

        desc_m = re.search(r'<div style="line-height: 140%[^>]*>(.*?)</div>', card, flags=re.S)
        desc = clean_inline(desc_m.group(1)) if desc_m else ""

        # 会場が本文に明記されていればそちらを優先（朝陽会館主催で大槻能楽堂開催のケースなど）
        vm = re.search(r"会場[:：]\s*([^\s〒●◎※\(（]+)", desc)
        venue = vm.group(1).strip() if vm else "朝陽会館"

        tm = re.search(r"開演\s*([^会場]+?)(?:会場|$)", desc)
        time_str = tm.group(1).strip() if tm else ""

        img_m = re.search(r'<img[^>]+src="([^"]+)"', card)
        items.append(
            make_item(
                title=title,
                date_str=date_str,
                venue=venue,
                url=ev_url,
                source="朝陽会館",
                time_str=time_str[:50],
                tags=["朝陽会館", "観世流"],
                summary=desc,
                image=img_m.group(1) if img_m else "",
                default_pref="大阪",
            )
        )
    return items


def scrape_otsu_dengei() -> list:
    """大津市伝統芸能会館（滋賀・大津）の主催公演一覧を取得します。"""
    url = "https://www.otsu-dengei.jp/performance.php"
    page = fetch_text(url)
    items = []
    blocks = re.split(r'<div class="EachPerformance">', page)[1:]
    for block in blocks:
        head_m = re.search(r'<p class="EachPerformance__head[^"]*"[^>]*>(.*?)</p>', block, flags=re.S)
        if not head_m:
            continue
        # ルビ（<rt>...</rt>）を除去して見やすくする
        head_raw = re.sub(r"<rt>.*?</rt>|<rp>.*?</rp>", "", head_m.group(1), flags=re.S)
        head_lines = [line for line in clean_html(head_raw).splitlines() if line]
        if not head_lines:
            continue
        title = head_lines[0]

        # 日時抽出
        dt_m = re.search(r"日\s*(?:&nbsp;)?\s*時</span>\s*<div[^>]*>(.*?)</div>", block, flags=re.S)
        dt_text = clean_inline(dt_m.group(1)) if dt_m else clean_inline(block)
        date_str = parse_jp_date(dt_text)
        if not date_str:
            continue

        tm = re.search(r"((?:午前|午後)?\d{1,2}時(?:\d{1,2}分)?開演(?:[^<　]*)?|\d{1,2}:\d{2}[^<　]*)", dt_text)
        time_str = tm.group(1).strip() if tm else ""

        # 料金抽出
        price_m = re.search(r"前\s*売</li>\s*<li[^>]*>(.*?)</li>", block, flags=re.S)
        price = f"前売 {clean_inline(price_m.group(1))}" if price_m else ""

        # PDFチラシリンクがあれば優先
        pdf_m = re.search(r'href="(\./pdf/performance/[^"]+\.pdf)"', block)
        ev_url = urllib.parse.urljoin(url, pdf_m.group(1)) if pdf_m else url

        programs = [line for line in head_lines[1:5] if len(line) < 60]
        tags = ["大津市伝統芸能会館"]
        if any("お話" in line or "解説" in line for line in head_lines):
            tags.append("解説あり")

        items.append(
            make_item(
                title=title,
                date_str=date_str,
                venue="大津市伝統芸能会館",
                url=ev_url,
                source="大津市伝統芸能会館",
                time_str=time_str,
                programs=programs,
                price=price[:160],
                tags=tags,
                summary=" ".join(head_lines[1:])[:280],
                default_pref="滋賀",
            )
        )
    return items


def scrape_ooe() -> list:
    """大江能楽堂（京都）の公式サイトから定期能・別会公演を取得します。"""
    base_url = "https://www.asahi-net.or.jp/~tn4m-ooe/"
    top = fetch_text(base_url)
    # トップからリンクされている公演系HTMLページを収集
    rel_links = re.findall(r'href=["\']([a-zA-Z0-9_\-]+\.html)["\']', top)
    candidate_pages = []
    for lk in dict.fromkeys(rel_links):
        if any(k in lk.lower() for k in ("teiki", "bekkai", "yotei", "kouen", "schedule", "program")):
            candidate_pages.append(urllib.parse.urljoin(base_url, lk))

    items = []
    for page_url in candidate_pages[:6]:
        try:
            page = fetch_text(page_url)
        except Exception:
            continue
        text = clean_html(page)
        date_str = parse_jp_date(text)
        if not date_str:
            continue
        t_m = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.S | re.I)
        title = clean_inline(t_m.group(1)).replace("— 大江能楽堂", "").strip() if t_m else "大江能楽堂 公演"
        tm = re.search(r"((?:午前|午後)?\d{1,2}[:：時]\d{0,2}分?\s*開演|開演\s*(?:午前|午後)?\d{1,2}[:：時]\d{0,2}分?)", text)
        time_str = tm.group(1) if tm else ""
        tags = ["大江能楽堂", "観世流"]
        if "完売" in text:
            tags.append("完売・当日券確認")

        items.append(
            make_item(
                title=title,
                date_str=date_str,
                venue="大江能楽堂",
                url=page_url,
                source="大江能楽堂",
                time_str=time_str,
                tags=tags,
                summary=text.replace("\n", " ")[:240],
                default_pref="京都",
            )
        )
        time.sleep(0.25)
    return items


def scrape_nohgoyomi(max_pages: int = 5) -> list:
    """能暦（全国の能楽公演まとめ）から公演一覧を取得します。"""
    items = []
    for p in range(1, max_pages + 1):
        url = "https://nohgoyomi.com/performances/" if p == 1 else f"https://nohgoyomi.com/performances/page/{p}/"
        try:
            page = fetch_text(url)
        except Exception:
            break

        articles = re.findall(r'<article class="performance-card".*?</article>', page, flags=re.S)
        if not articles:
            break

        for art in articles:
            link_m = re.search(r'<a[^>]+href="([^"]+)"', art)
            title_m = re.search(r'<h2 class="performance-card__title">(.*?)</h2>', art, flags=re.S)
            date_m = re.search(r'<p class="performance-card__date">(.*?)</p>', art, flags=re.S)
            time_m = re.search(r'<p class="performance-card__time">(.*?)</p>', art, flags=re.S)
            venue_m = re.search(r'<p class="performance-card__venue">(.*?)</p>', art, flags=re.S)
            img_m = re.search(r'data-src="(https://nohgoyomi\.com/wp-content/uploads/[^"]+)"', art)

            if not title_m or not date_m:
                continue
            title = clean_inline(title_m.group(1))
            raw_date = clean_inline(date_m.group(1))
            dm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw_date)
            if not dm:
                continue
            date_str = f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

            # 演目リスト
            prog_block_m = re.search(r'<div class="performance-card__programs">(.*?)</div>', art, flags=re.S)
            programs = []
            if prog_block_m:
                for p_tag in re.findall(r"<p>(.*?)</p>", prog_block_m.group(1), flags=re.S):
                    pt = clean_inline(p_tag)
                    if pt:
                        programs.append(pt)

            # 特徴タグ（解説あり、字幕あり等）
            tags = [clean_inline(t) for t in re.findall(r'<span class="screen-reader-text">(.*?)</span>', art, flags=re.S)]

            items.append(
                make_item(
                    title=title,
                    date_str=date_str,
                    venue=clean_inline(venue_m.group(1)) if venue_m else "会場未定",
                    url=link_m.group(1) if link_m else url,
                    source="能暦",
                    time_str=clean_inline(time_m.group(1)) if time_m else "",
                    programs=programs[:8],
                    tags=tags,
                    summary=" / ".join(programs),
                    image=img_m.group(1) if img_m else "",
                    default_pref="その他",
                )
            )
        time.sleep(0.3)
    return items


def make_dedup_key(item: dict) -> tuple:
    """重複整理および既存公演の照合に使う正規化キーを生成します。"""
    def normalize_key(text: str) -> str:
        t = re.sub(r"[\s　・\-－―「」『』（）()【】\[\]第\d回]", "", text or "")
        return t[:14].lower()

    return (
        item.get("date", ""),
        normalize_key(item.get("venue", "")),
        normalize_key(item.get("title", "")),
    )


def deduplicate(items: list) -> list:
    """同じ日付・会場・類似タイトルの公演重複を整理し、情報が充実している方を残します。"""
    best_by_key = {}
    for item in items:
        key = make_dedup_key(item)
        # 情報量スコア（演目数＋料金＋時間＋画像＋公式優先）
        score = (
            len(item["programs"]) * 3
            + (2 if item["price"] else 0)
            + (2 if item["time"] else 0)
            + (1 if item["image"] else 0)
            + (3 if item["source"] != "能暦" else 0)
        )
        prev = best_by_key.get(key)
        if not prev or score > prev[0]:
            best_by_key[key] = (score, item)
    return [v[1] for v in best_by_key.values()]


def apply_first_seen(items: list, json_path: Path, today_str: str) -> int:
    """
    前回のperformances.jsonから初回掲載日(firstSeen)を引き継ぎ、
    今回新しく出現した公演だけに今日の日付を記録します。
    ※既存ファイルが無い初回実行時、およびfirstSeen未記録の既存公演は空文字（NEWなし）として扱い、
      導入初日に全件がNEWにならないようにします。
    """
    if not json_path.exists():
        for item in items:
            item["firstSeen"] = ""
        return 0

    try:
        prev_data = json.loads(json_path.read_text(encoding="utf-8"))
        prev_items = prev_data.get("performances", [])
    except Exception:
        for item in items:
            item["firstSeen"] = ""
        return 0

    seen_by_id = {}
    seen_by_key = {}
    for prev in prev_items:
        # すでに掲載済みの公演で firstSeen が未設定なら空文字（NEWなし）として記憶
        fs = prev.get("firstSeen", "")
        if prev.get("id"):
            seen_by_id[prev["id"]] = fs
        seen_by_key[make_dedup_key(prev)] = fs

    new_count = 0
    for item in items:
        uid = item.get("id", "")
        key = make_dedup_key(item)
        if uid in seen_by_id:
            item["firstSeen"] = seen_by_id[uid]
        elif key in seen_by_key:
            item["firstSeen"] = seen_by_key[key]
        else:
            item["firstSeen"] = today_str
            new_count += 1
    return new_count


def main():
    print("能楽の公演情報をWebから収集しています...")
    today_str = datetime.date.today().isoformat()

    scrapers = [
        ("大槻能楽堂", scrape_otsuki),
        ("山本能楽堂", scrape_yamamoto),
        ("朝陽会館", scrape_choyo),
        ("京都観世会館", scrape_kyoto_kanze),
        ("金剛能楽堂", scrape_kongo),
        ("大江能楽堂", scrape_ooe),
        ("西宮能楽堂", scrape_nishinomiya),
        ("湊川神社 神能殿", scrape_minatogawa),
        ("大津市伝統芸能会館", scrape_otsu_dengei),
        ("能楽協会", scrape_nohgaku_assoc),
        ("能暦", scrape_nohgoyomi),
    ]

    all_items = []
    source_stats = []

    for name, fn in scrapers:
        try:
            fetched = fn()
            # 今日以降の公演のみ残す
            upcoming = [it for it in fetched if it["date"] >= today_str]
            all_items.extend(upcoming)
            source_stats.append({"name": name, "count": len(upcoming), "status": "ok"})
            print(f"  [OK] {name}: {len(upcoming)}件（取得全体: {len(fetched)}件）")
        except Exception as exc:
            source_stats.append({"name": name, "count": 0, "status": f"error: {exc}"})
            print(f"  [警告] {name}: 取得に失敗しました ({exc})")

    merged = deduplicate(all_items)
    merged.sort(key=lambda x: (x["date"], x["time"], x["venue"]))

    json_path = DATA_DIR / "performances.json"
    new_count = apply_first_seen(merged, json_path, today_str)

    kansai_count = sum(1 for x in merged if x["region"] == "関西")
    now_label = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")

    payload = {
        "updatedAt": now_label,
        "totalCount": len(merged),
        "kansaiCount": kansai_count,
        "newCount": new_count,
        "sources": source_stats,
        "performances": merged,
    }

    # JSONファイル保存
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 直接ブラウザで開く場合用のJSファイルも保存
    js_path = DATA_DIR / "performances.js"
    js_path.write_text(
        "// 自動生成された能公演データ（scraper.py により更新）\nwindow.NOH_DATA = "
        + json.dumps(payload, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )

    print(f"\n完了しました！ 合計 {len(merged)}件（うち関西 {kansai_count}件 / 本日の新着 {new_count}件）")
    print(f"保存先: {json_path}")


if __name__ == "__main__":
    main()
