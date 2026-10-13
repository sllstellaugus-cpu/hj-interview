from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
OUT = Path(__file__).resolve().parent / "news.json"

QUERIES = [
    ("HJ중공업", 8),
    ('"HJ중공업" 조선', 8),
    ('"HJ중공업" MRO', 8),
    ("조선업 수주 원가 공정", 5),
    ("미 해군 MRO 조선", 6),
    ("친환경 선박 조선 AI 스마트야드", 4),
]

POSITIVE = {
    "HJ중공업": 10,
    "수주": 5,
    "영업이익": 5,
    "매출": 4,
    "MRO": 6,
    "MSRA": 6,
    "미 해군": 5,
    "컨테이너선": 5,
    "친환경": 3,
    "특수선": 4,
    "방산": 4,
    "원가": 4,
    "공정": 4,
    "수익성": 5,
    "영도조선소": 5,
    "AI": 2,
    "스마트": 2,
}
NEGATIVE = {
    "주가": -8,
    "특징주": -10,
    "급등": -8,
    "급락": -8,
    "목표주가": -6,
    "증권": -5,
    "공시": -6,
}

# 면접과 직접 관련 없는 HJ 건설/홍보/주가성 뉴스는 제외
EXCLUDE_WORDS = {
    "건설", "고속도로", "아파트", "재개발", "재건축", "부동산",
    "챔피언십", "기부", "기부금", "골프", "사회공헌",
    "개장 전", "주가", "특징주", "급등", "급락", "목표주가", "공시",
}

# 조선경영기획 면접에 직접 연결되는 키워드
RELEVANT_WORDS = {
    "HJ중공업", "조선", "영도조선소", "선박", "컨테이너선", "상선",
    "특수선", "함정", "방산", "MRO", "MSRA", "미 해군",
    "수주", "수주잔고", "매출", "영업이익", "실적", "수익성",
    "원가", "공정", "후판", "친환경", "자율운항", "스마트", "AI",
}

def is_relevant(title: str) -> bool:
    lower = title.lower()
    if any(word.lower() in lower for word in EXCLUDE_WORDS):
        return False

    # HJ 기사도 조선/실적/방산 등 면접 관련 주제가 함께 있어야 함
    if "hj중공업" in lower:
        hj_topics = RELEVANT_WORDS - {"HJ중공업"}
        return any(word.lower() in lower for word in hj_topics)

    # 일반 업계 기사는 조선 관련성이 명확해야 함
    ship_core = {
        "조선", "선박", "컨테이너선", "특수선", "함정", "방산",
        "MRO", "MSRA", "미 해군", "영도조선소", "후판", "자율운항",
    }
    return any(word.lower() in lower for word in ship_core)



def fetch_rss(query: str):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read()

    root = ET.fromstring(data)
    items = []
    for item in root.findall("./channel/item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(KST)
        except Exception:
            dt = datetime.now(KST)
        items.append({"title": title, "link": link, "source": source, "dt": dt})
    return items


def score(title: str, query_weight: int) -> int:
    total = query_weight
    lower = title.lower()
    for key, value in POSITIVE.items():
        if key.lower() in lower:
            total += value
    for key, value in NEGATIVE.items():
        if key.lower() in lower:
            total += value
    return total


def category(title: str) -> str:
    t = title.lower()
    if "mro" in t or "msra" in t or "미 해군" in t or "함정" in t:
        return "MRO·방산"
    if "컨테이너선" in t or "선박" in t or "조선" in t or "영도조선소" in t:
        return "수주·선박"
    if "영업이익" in t or "매출" in t or "실적" in t or "수익성" in t:
        return "실적·수익성"
    if "원가" in t or "공정" in t or "후판" in t:
        return "원가·공정"
    if "ai" in t or "스마트" in t or "친환경" in t or "자율운항" in t:
        return "기술·친환경"
    return "기타"


def explain(cat: str):
    if cat == "MRO·방산":
        return (
            "HJ의 신성장 사업과 방산·정비 역량 확장을 이해하는 데 직접 연결돼.",
            "최근 MRO 관련 흐름을 보면서, 신규 매출원뿐 아니라 실제 수주 이후의 원가·공정·수익성 관리가 전략기획에서 중요하다고 생각했습니다.",
        )
    if cat == "수주·선박":
        return (
            "수주잔고, 향후 매출 가시성, 공정·납기·수익성으로 이어지는 핵심 뉴스야.",
            "최근 수주 흐름을 관심 있게 보고 있습니다. 수주 규모 자체보다 향후 공정·원가·납기 관리로 계획한 수익성을 실제 이익으로 연결하는 것이 중요하다고 생각합니다.",
        )
    if cat == "실적·수익성":
        return (
            "영업이익률 개선 원인과 회사의 현재 경영상태를 설명할 때 바로 쓸 수 있어.",
            "최근 실적을 보면서 단순 매출 증가보다 사업별 원가와 수익성 개선이 중요하다고 봤습니다. 전략기획에서는 계획 대비 실적 차이와 원인을 빠르게 파악하는 것이 필요하다고 생각합니다.",
        )
    if cat == "원가·공정":
        return (
            "조선 경영기획의 핵심인 프로젝트 손익·공정·납기 리스크와 연결돼.",
            "조선업은 공정과 원가가 프로젝트 수익성에 직접 연결되기 때문에, 원가 변동과 공정 지연을 계획 대비 차이로 조기에 관리하는 것이 중요하다고 생각합니다.",
        )
    if cat == "기술·친환경":
        return (
            "기술 변화가 생산성·원가·선종 경쟁력·중장기 사업계획에 미치는 영향을 볼 수 있어.",
            "최근 친환경·스마트조선 흐름을 관심 있게 보고 있습니다. 기술 변화가 생산성·원가·사업계획에 어떻게 반영되는지가 중요하다고 생각합니다.",
        )
    return (
        "HJ와 조선산업의 최근 흐름을 이해하는 데 참고할 뉴스야.",
        "최근 조선산업 변화를 꾸준히 보고 있으며, 회사의 실적과 실행과제에 어떤 영향을 주는지 연결해서 보려고 하고 있습니다.",
    )


def clean_title(title: str) -> str:
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def main():
    now = datetime.now(KST)
    cutoff = now - timedelta(days=7)
    pool = {}

    for query, query_weight in QUERIES:
        try:
            for item in fetch_rss(query):
                if item["dt"] < cutoff:
                    continue
                title = clean_title(item["title"])
                if not title or not item["link"]:
                    continue
                if not is_relevant(title):
                    continue
                key = re.sub(r"\W+", "", title.lower())
                candidate = {
                    "title": title,
                    "link": item["link"],
                    "source": item["source"],
                    "dt": item["dt"],
                    "score": score(title, query_weight),
                    "cat": category(title),
                }
                if key not in pool or candidate["score"] > pool[key]["score"]:
                    pool[key] = candidate
        except Exception as exc:
            print("RSS error:", query, exc)

    ranked = sorted(pool.values(), key=lambda x: (x["score"], x["dt"]), reverse=True)
    chosen = []
    category_count = {}

    for item in ranked:
        cat = item["cat"]
        if category_count.get(cat, 0) >= 2:
            continue
        why, interview_line = explain(cat)
        chosen.append(
            {
                "title": item["title"],
                "link": item["link"],
                "source": item["source"] or "Google News",
                "published": item["dt"].strftime("%Y.%m.%d"),
                "category": cat,
                "why": why,
                "interview_line": interview_line,
            }
        )
        category_count[cat] = category_count.get(cat, 0) + 1
        if len(chosen) >= 5:
            break

    data = {
        "last_updated": now.strftime("%Y.%m.%d %H:%M KST"),
        "items": chosen,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", len(chosen), "items")


if __name__ == "__main__":
    main()
