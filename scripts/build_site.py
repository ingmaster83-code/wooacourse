# -*- coding: utf-8 -*-
"""우아여행코스 정적 사이트 생성기.
입력: data/list.json.gz(코스 목록+지오코딩 시도·시군구) · data/details/*.json.gz(개요·거리·소요시간·코스 지점)
출력: _site/  (코스 상세, 지역·소요시간 허브, 코스에 자주 나오는 장소, 안내, 검색 인덱스, sitemap)
상세가 아직 없는 코스는 만들지 않는다(상세는 매일 예산만큼 쌓임). 이미지는 저작권·혼합콘텐츠 때문에 쓰지 않고 본문은 일부만 발췌한다.
"""
import collections, gzip, html as ihtml, json, re, shutil, sys
from datetime import datetime, timedelta, timezone

from common import *  # noqa

sys.stdout.reconfigure(encoding="utf-8")
DATA = ROOT / "data"
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).date()

SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
         "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
         "경상남도": "경남", "제주특별자치도": "제주", "전남광주통합특별시": "전남광주"}
BUCKETS = [("day", "당일치기", "하루 안에 다녀오는 코스"), ("night1", "1박2일", "하루 묵고 다녀오는 코스"), ("night2", "2박3일 이상", "이틀 이상 묵는 코스")]
BNAME = {k: n for k, n, _ in BUCKETS}
BDESC = {k: d for k, _, d in BUCKETS}


def un(s):
    return ihtml.unescape(ihtml.unescape(s or ""))


def plain(s):
    s = un(s)
    s = re.sub(r"<br\s*/?>|</p>|\\n", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t ]+", " ", s.replace("\r", ""))
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def excerpt(s, n):
    s = re.sub(r"\s+", " ", plain(s))
    if len(s) <= n:
        return s
    cut = s[:n]
    k = max(cut.rfind(". "), cut.rfind("다. "), cut.rfind(" "))
    return (cut[:k] if k > n * 0.6 else cut).rstrip(" ,.·") + " …"


def sho(s):
    return SHORT.get(s, s)


def km(s):
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", (s or "").replace(",", ""))
    return float(m.group(1)) if m and "km" in (s or "").lower() else None


def bucket(tk, title=""):
    t = (tk or "").replace(" ", "")
    m = re.search(r"(\d+)박", t)
    if m:
        return "night1" if int(m.group(1)) == 1 else "night2"
    if t:
        return "day"
    if "1박2일" in title.replace(" ", ""):
        return "night1"
    return ""


def load():
    rows = json.loads(gzip.open(DATA / "list.json.gz", "rt", encoding="utf-8").read())
    det = {}
    for p in (DATA / "details").glob("*.json.gz"):
        det.update(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
    cs = []
    for r in rows:
        d = det.get(r["id"])
        if not d:
            continue
        c = d["common"]
        title = un(c.get("title") or r["title"]).strip()
        stops = [{"n": un(s["n"]).strip(), "id": s["id"], "o": s["o"]} for s in d["stops"] if un(s["n"]).strip()]
        if not stops:
            continue
        intro = d["intro"]
        cs.append(dict(id=r["id"], title=title, sido=r.get("sido", ""), sgg=r.get("sgg", ""), x=r.get("x", ""), y=r.get("y", ""), mod=r.get("mod", ""), overview=plain(c.get("overview")),
                       dist=km(intro.get("distance")), distraw=(intro.get("distance") or "").strip(), take=(intro.get("taketime") or "").strip(), bucket=bucket(intro.get("taketime"), title), stops=stops))
    return cs, len(rows)


def clink(c):
    return '<a href="/course/%s/">%s</a>' % (c["id"], esc(c["title"]))


def ctable(L, cap=200, region=True):
    L = L[:cap]
    head = "<tr><th>여행 코스</th>%s<th>소요시간</th><th>거리</th><th>들르는 곳</th></tr>" % ("<th>지역</th>" if region else "")
    rows = []
    for c in L:
        names = " → ".join(s["n"] for s in c["stops"][:4]) + (" …" if len(c["stops"]) > 4 else "")
        rows.append("<tr><td>%s</td>%s<td>%s</td><td>%s</td><td>%s</td></tr>" % (
            clink(c), ("<td>%s</td>" % esc((sho(c["sido"]) + " " + c["sgg"]).strip() or "-")) if region else "", esc(c["take"] or "-"), ("%.1fkm" % c["dist"]) if c["dist"] else "-", esc(names)))
    return '<div class="tbl-wrap"><table class="tbl">%s%s</table></div>' % (head, "".join(rows))


def stat(L):
    n = len(L)
    ds = [c["dist"] for c in L if c["dist"]]
    b = collections.Counter(BNAME.get(c["bucket"], "") for c in L if c["bucket"])
    s = "여행 코스 <b>%d개</b>입니다." % n
    if b:
        s += " " + ", ".join("%s %d개" % (k, v) for k, v in b.most_common()) + "로 나뉩니다."
    if ds:
        s += " 코스 평균 이동 거리는 약 %.0fkm입니다." % (sum(ds) / len(ds))
    return '<p class="lead">%s</p>' % s


def hub(path, h1, sub, L, extra="", cap=200, title=None, desc=None, crumbs=None, prio="0.7", region=True, faq=None):
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(h1), esc(sub)), stat(L), ad(), extra, '<h2 class="group-title">코스 목록</h2>', ctable(L, cap, region)]
    if len(L) > cap:
        body.append('<p class="note">코스가 많아 %d개만 표시했습니다. 지역·소요시간별 페이지에서 좁혀 보세요.</p>' % cap)
    write(path, layout(path, title or h1, desc or sub, "\n".join(b for b in body if b), faq, crumbs or [("홈", "/")], coupang=True), prio)


def page_course(c, by_sido, place_ok, hubs_ok):
    region = (sho(c["sido"]) + " " + c["sgg"]).strip()
    names = [s["n"] for s in c["stops"]]
    lead = ["<b>%s</b>은(는) %s여행 코스로, 총 <b>%d곳</b>(%s)을 돕니다." % (esc(c["title"]), (esc(region) + "의 ") if region else "", len(names), esc(" → ".join(names[:5]) + (" …" if len(names) > 5 else "")))]
    if c["take"]:
        lead.append("소요 시간은 %s%s입니다." % (esc(c["take"]), "(%s)" % BNAME[c["bucket"]] if c["bucket"] else ""))
    if c["dist"]:
        lead.append("코스 이동 거리는 약 %skm로 안내돼 있습니다." % ("%g" % c["dist"]))
    rows = [("지역", region), ("소요 시간", c["take"]), ("이동 거리", c["distraw"]), ("코스 지점", "%d곳" % len(names))]
    tbl = '<div class="tbl-wrap"><table class="tbl">%s</table></div>' % "".join("<tr><th>%s</th><td>%s</td></tr>" % (a, esc(b)) for a, b in rows if b)
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(c["title"]), esc(" · ".join(x for x in (region, BNAME.get(c["bucket"], "")) if x) or "여행 코스")), '<p class="lead">%s</p>' % " ".join(lead), ad(), '<h2 class="group-title">코스 정보</h2>', tbl]
    if c["overview"]:
        body.append('<h2 class="group-title">코스 소개</h2><div class="lead">%s</div>' % "<br>".join(esc(l) for l in excerpt(c["overview"], 520).split("\n") if l.strip()))
    body.append('<h2 class="group-title">코스 순서</h2><ol class="lead">')
    for s in c["stops"]:
        nm = ('<a href="/place/%s/">%s</a>' % (s["id"], esc(s["n"]))) if s["id"] in place_ok else esc(s["n"])
        ex = excerpt(s["o"], 110)
        body.append("<li><b>%s</b>%s</li>" % (nm, (" — " + esc(ex)) if ex else ""))
    body.append("</ol>")
    if c["x"] and c["y"]:
        body.append('<p><a class="btn" href="https://map.kakao.com/link/map/%s,%s,%s">🗺️ 코스 시작 지점 지도에서 보기</a></p>' % (urllib.parse.quote(c["title"][:40]), c["y"], c["x"]))
    body.append('<div class="note-box">코스 정보는 한국관광공사 TourAPI(공공데이터포털) 기준이며 일부만 발췌했습니다. 각 장소의 운영 여부·휴무·요금은 방문 전에 확인하세요.</div>')
    sib = [o for o in by_sido.get(c["sido"], []) if o is not c][:8] if c["sido"] else []
    if sib:
        body.append('<h2 class="group-title">같은 지역 다른 여행 코스 <small>%s</small></h2>' % esc(sho(c["sido"])))
        body.append(ctable(sib))
    chips = []
    if c["sido"] and ("region", c["sido"]) in hubs_ok:
        chips.append('<a class="chip" href="/region/%s/">%s 여행 코스</a>' % (q(c["sido"]), esc(sho(c["sido"]))))
    if c["sido"] and c["sgg"] and ("sgg", c["sido"], c["sgg"]) in hubs_ok:
        chips.append('<a class="chip" href="/region/%s/%s/">%s %s</a>' % (q(c["sido"]), q(c["sgg"]), esc(sho(c["sido"])), esc(c["sgg"])))
    if c["bucket"]:
        chips.append('<a class="chip" href="/time/%s/">%s 코스</a>' % (c["bucket"], BNAME[c["bucket"]]))
    body.append('<div class="chips">%s</div>' % "".join(chips))
    faq = [("%s 코스는 얼마나 걸리나요?" % c["title"], ("공공데이터에는 소요 시간이 %s로 등록돼 있습니다. 이동 수단·체류 시간에 따라 달라질 수 있습니다." % c["take"]) if c["take"] else "공공데이터에 소요 시간 정보가 없습니다. 코스 지점 수(%d곳)를 참고해 일정을 잡으세요." % len(names)),
           ("%s 코스에서는 어디를 들르나요?" % c["title"], "%s 순서로 %d곳을 돕니다." % (", ".join(names[:8]), len(names))),
           ("코스 정보는 어디서 가져왔나요?", "한국관광공사가 공공데이터포털에 공개한 TourAPI 여행코스 정보입니다. 운영·휴무는 바뀔 수 있어 방문 전에 확인하세요.")]
    crumbs = [("홈", "/")] + ([(sho(c["sido"]), "/region/%s/" % c["sido"])] if c["sido"] and ("region", c["sido"]) in hubs_ok else []) + [((c["title"][:28] + "…") if len(c["title"]) > 28 else c["title"], "/course/%s/" % c["id"])]
    ld = [{"@context": "https://schema.org", "@type": "TouristTrip", "name": c["title"], "description": excerpt(c["overview"], 160) or c["title"],
           "itinerary": {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": s["n"]} for i, s in enumerate(c["stops"])]}}]
    title = "%s - %s여행 코스%s" % (c["title"], (region + " ") if region else "", (" (%s)" % BNAME[c["bucket"]]) if c["bucket"] else "")
    desc = "%s여행 코스 %s: %s 등 %d곳%s." % ((region + " ") if region else "", c["title"], ", ".join(names[:3]), len(names), (", 소요 " + c["take"]) if c["take"] else "")
    write("/course/%s/" % c["id"], layout("/course/%s/" % c["id"], title, desc, "\n".join(body), faq, crumbs, "article", ld, coupang=True), "0.6")


def build():
    cs, total_rows = load()
    print("코스", len(cs), "/ 목록", total_rows)
    # 좌표가 없어 지역을 못 구한 코스는 제목·개요에 나온 시군구 이름(지오코딩된 코스에서 알아낸 이름만)으로 추정한다.
    stems = collections.defaultdict(collections.Counter)
    for c in cs:
        if c["sido"] and c["sgg"]:
            stems[re.sub(r"(특별자치시|시|군|구)$", "", c["sgg"].split()[0])][(c["sido"], c["sgg"].split()[0])] += 1
    uniq = {k: v.most_common(1)[0][0] for k, v in stems.items() if len(k) >= 2 and len(v) == 1}
    n_inf = 0
    for c in cs:
        if not c["sido"]:
            text = c["title"] + " " + c["overview"][:160]
            hit = [k for k in uniq if k in text]
            if hit:
                k = max(hit, key=lambda x: (c["title"].find(x) >= 0, len(x)))
                c["sido"], c["sgg"] = uniq[k]
                n_inf += 1
    print("지역 추정", n_inf, "건, 지역 없음", sum(1 for c in cs if not c["sido"]))
    cs.sort(key=lambda c: (-int(c["mod"] or 0), c["id"]))
    by_sido, by_sgg, by_b, by_sb = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    stops = collections.defaultdict(list)
    for c in cs:
        if c["sido"]:
            by_sido[c["sido"]].append(c)
            if c["sgg"]:
                by_sgg[(c["sido"], c["sgg"])].append(c)
        if c["bucket"]:
            by_b[c["bucket"]].append(c)
            if c["sido"]:
                by_sb[(c["bucket"], c["sido"])].append(c)
        for s in c["stops"]:
            if s["id"]:
                stops[s["id"]].append((c, s))
    place_ok = {k for k, v in stops.items() if len({c["id"] for c, _ in v}) >= 2}
    hubs_ok = {("region", s) for s in by_sido} | {("sgg", s, g) for (s, g), L in by_sgg.items() if len(L) >= 3}
    OUT.mkdir(parents=True, exist_ok=True)
    for ch in OUT.iterdir():
        shutil.rmtree(ch) if ch.is_dir() else ch.unlink()
    for c in cs:
        page_course(c, by_sido, place_ok, hubs_ok)
    # 지역
    for s, L in by_sido.items():
        gc = collections.Counter(c["sgg"] for c in L if c["sgg"])
        bc = collections.Counter(c["bucket"] for c in L if c["bucket"])
        extra = '<h2 class="group-title">소요시간별</h2><div class="chips">%s</div>' % "".join(
            ('<a class="chip" href="/time/%s/%s/">%s <small>%d</small></a>' % (b, q(s), BNAME[b], n)) if len(by_sb[(b, s)]) >= 3 else '<span class="chip">%s <small>%d</small></span>' % (BNAME[b], n) for b, n in bc.most_common())
        if gc:
            extra += '<h2 class="group-title">시군구별</h2><div class="chips">%s</div>' % "".join(
                ('<a class="chip" href="/region/%s/%s/">%s <small>%d</small></a>' % (q(s), q(g), esc(g), n)) if n >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(g), n) for g, n in gc.most_common(60))
        hub("/region/%s/" % s, "%s 여행 코스 %d개" % (s, len(L)), "당일치기·1박2일 추천 코스", L, extra, 150, "%s 여행 코스 %d개 - 당일치기·1박2일 코스" % (sho(s), len(L)),
            "%s의 여행 코스 %d개를 소요시간·거리·들르는 곳과 함께 정리했습니다." % (s, len(L)), [("홈", "/"), ("지역별", "/region/"), (s, "/region/%s/" % s)], "0.8",
            faq=[("%s 여행 코스는 몇 개인가요?" % sho(s), "한국관광공사 공공데이터 기준 %d개입니다." % len(L))])
    for (s, g), L in by_sgg.items():
        if len(L) >= 3:
            hub("/region/%s/%s/" % (s, g), "%s %s 여행 코스 %d개" % (sho(s), g, len(L)), "들르는 곳과 소요시간", L, "", 150, "%s %s 여행 코스 %d개" % (sho(s), g, len(L)), "%s %s의 여행 코스 %d개를 정리했습니다." % (s, g, len(L)),
                [("홈", "/"), (s, "/region/%s/" % s), (g, "/region/%s/%s/" % (s, g))], "0.6", region=False)
    cards = "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d개</span></a>' % (q(s), esc(sho(s)), len(L)) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1])))
    write("/region/", layout("/region/", "지역별 여행 코스", "시도별 여행 코스 개수를 확인하고 당일치기·1박2일 코스를 고르세요.", '<div class="page-head"><h1>지역별 여행 코스</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("지역별", "/region/")]), "0.8")
    # 소요시간
    for k, name, desc in BUCKETS:
        L = by_b.get(k, [])
        if not L:
            continue
        sc = collections.Counter(c["sido"] for c in L if c["sido"])
        extra = '<h2 class="group-title">지역별</h2><div class="chips">%s</div>' % "".join(('<a class="chip" href="/time/%s/%s/">%s <small>%d</small></a>' % (k, q(s), esc(sho(s)), n)) if n >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(sho(s)), n) for s, n in sc.most_common())
        hub("/time/%s/" % k, "%s 여행 코스 %d개" % (name, len(L)), desc, L, extra, 200, "%s 여행 코스 %d개 - 지역별 추천" % (name, len(L)), "%s 여행 코스 %d개를 지역·거리·들르는 곳과 함께 정리했습니다." % (name, len(L)),
            [("홈", "/"), ("소요시간별", "/time/"), (name, "/time/%s/" % k)], "0.8", faq=[("%s 코스는 어떻게 고르나요?" % name, "지역을 고른 뒤 들르는 곳과 이동 거리를 비교해 일정에 맞는 코스를 고르세요.")])
        for s, n in sc.items():
            if n >= 3:
                L2 = by_sb[(k, s)]
                hub("/time/%s/%s/" % (k, s), "%s %s 여행 코스 %d개" % (sho(s), name, len(L2)), desc, L2, "", 150, "%s %s 코스 %d개" % (sho(s), name, len(L2)), "%s의 %s 여행 코스 %d개를 정리했습니다." % (s, name, len(L2)),
                    [("홈", "/"), (name, "/time/%s/" % k), (s, "/time/%s/%s/" % (k, s))], "0.6", region=False)
    cards = "".join('<a class="card" href="/time/%s/"><b>%s</b><span>%d개 · %s</span></a>' % (k, name, len(by_b.get(k, [])), esc(d)) for k, name, d in BUCKETS if by_b.get(k))
    write("/time/", layout("/time/", "소요시간별 여행 코스", "당일치기, 1박2일, 2박3일 이상으로 여행 코스를 찾으세요.", '<div class="page-head"><h1>소요시간별 여행 코스</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("소요시간별", "/time/")]), "0.8")
    # 장소(2개 이상 코스에 등장)
    npl = 0
    for pid in place_ok:
        occ = stops[pid]
        name = occ[0][1]["n"]
        L = []
        seen = set()
        for c, _ in occ:
            if c["id"] not in seen:
                seen.add(c["id"]); L.append(c)
        ex = max((excerpt(s["o"], 200) for _, s in occ), key=len)
        sc = collections.Counter(sho(c["sido"]) for c in L if c["sido"]).most_common(1)
        where = sc[0][0] if sc else ""
        body = ['<div class="page-head"><h1>%s이(가) 포함된 여행 코스 %d개</h1><p>%s</p></div>' % (esc(name), len(L), esc(where)),
                '<p class="lead"><b>%s</b>은(는) %d개의 여행 코스에 들르는 곳으로 등록돼 있습니다.%s</p>' % (esc(name), len(L), (" " + esc(ex)) if ex else ""), ad(), '<h2 class="group-title">이곳을 지나는 코스</h2>', ctable(L, 50)]
        write("/place/%s/" % pid, layout("/place/%s/" % pid, "%s 여행 코스 - %s이(가) 포함된 코스 %d개" % (name, name, len(L)), "%s을(를) 들르는 여행 코스 %d개와 함께 가기 좋은 장소를 정리했습니다." % (name, len(L)), "\n".join(body), None,
                                          [("홈", "/"), (name, "/place/%s/" % pid)], coupang=True), "0.5")
        npl += 1
    # 홈
    top = sorted(place_ok, key=lambda p: -len({c["id"] for c, _ in stops[p]}))[:12]
    body = ['<div class="hero"><h1>여행 코스 찾기</h1><p>한국관광공사 여행 코스 %s개를 지역·소요시간·들르는 곳으로 찾으세요</p>'
            '<div class="today-box"><div><small>여행 코스</small><b>%s개</b></div><div><small>당일치기</small><b>%d개</b></div><div><small>1박2일</small><b>%d개</b></div><div><small>코스 지점</small><b>%s곳</b></div></div></div>' % (
                "{:,}".format(len(cs)), "{:,}".format(len(cs)), len(by_b.get("day", [])), len(by_b.get("night1", [])), "{:,}".format(len({s["id"] for c in cs for s in c["stops"] if s["id"]}))),
            '<div class="search-box"><input id="q" type="search" placeholder="코스 검색 (예: 속초, 1박2일, 한옥마을)" autocomplete="off"><div id="sr" class="sr-list"></div></div>', ad(),
            '<h2 class="group-title">소요시간별</h2><div class="card-grid">%s</div>' % cards, '<h2 class="group-title">지역별</h2><div class="card-grid">%s</div>' % "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d개</span></a>' % (q(s), esc(sho(s)), len(L)) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1]))),
            '<h2 class="group-title">여러 코스에 나오는 인기 장소</h2><div class="chips">%s</div>' % "".join('<a class="chip" href="/place/%s/">%s <small>%d</small></a>' % (p, esc(stops[p][0][1]["n"]), len({c["id"] for c, _ in stops[p]})) for p in top),
            '<h2 class="group-title">최근 갱신된 코스</h2>', ctable(cs[:10], 10), '<script src="/assets/js/search.js"></script>']
    faq = [("여행 코스 정보는 어디서 가져왔나요?", "한국관광공사가 공공데이터포털에 공개한 TourAPI 여행 코스 정보를 정리했습니다. 코스 소개와 지점 설명은 일부만 발췌했습니다."),
           ("당일치기와 1박2일 코스는 어떻게 나눴나요?", "공공데이터에 등록된 소요 시간 정보를 기준으로 '박'이 들어가면 1박2일·2박3일 이상, 시간 단위나 '1일'이면 당일치기로 나눴습니다."),
           ("코스에 나온 장소는 지금도 운영하나요?", "휴무·운영 변경이 있을 수 있어 방문 전에 각 장소의 안내를 확인하세요.")]
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "우아여행코스", "url": BASE + "/", "potentialAction": {"@type": "SearchAction", "target": BASE + "/?q={q}", "query-input": "required name=q"}}]
    write("/", layout("/", "여행 코스 찾기 - 지역별 당일치기·1박2일 코스 %s개 | 우아여행코스" % "{:,}".format(len(cs)), "한국관광공사 여행 코스 %s개를 지역·소요시간·들르는 곳으로 찾고 코스 순서를 확인하세요." % "{:,}".format(len(cs)), "\n".join(body), faq, None, "website", ld, coupang=True), "1.0")
    idx = [[c["title"], "/course/%s/" % c["id"], " · ".join(s["n"] for s in c["stops"][:3]), (sho(c["sido"]) + " " + c["sgg"]).strip(), c["take"]] for c in cs]
    (OUT / "search_index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pages_static(len(cs), total_rows)
    finish()
    print("장소 허브", npl)


def pages_static(n, total):
    body = ['<div class="page-head"><h1>여행 코스 고르는 방법과 이용 안내</h1></div>', ad(),
            '<h2 class="group-title">1. 코스 고르기</h2><ol class="lead"><li><a href="/region/">지역별</a>이나 <a href="/time/">소요시간별</a>로 후보를 좁힙니다.</li><li>코스 상세에서 들르는 곳 순서와 이동 거리를 확인합니다.</li><li>각 장소의 운영 시간·휴무일을 방문 전에 확인합니다.</li></ol>',
            '<h2 class="group-title">2. 코스 정보 읽는 법</h2><ul class="lead"><li><b>소요 시간</b>은 공공데이터에 등록된 값이며 이동 수단·체류 시간에 따라 달라집니다.</li><li><b>이동 거리</b>는 코스 지점을 이은 대략의 거리입니다.</li><li>지점 설명은 일부만 발췌했으니 자세한 내용은 한국관광공사 안내를 참고하세요.</li></ul>',
            '<div class="note-box">이 사이트는 한국관광공사 공개 데이터를 정리한 참고용이며 장소의 현재 운영 상태를 보장하지 않습니다.</div>']
    write("/guide/", layout("/guide/", "여행 코스 고르는 방법과 이용 안내", "지역·소요시간별로 여행 코스를 고르고 코스 정보를 읽는 방법을 정리했습니다.", "\n".join(body), None, [("홈", "/"), ("이용 안내", "/guide/")]), "0.6")
    body = ['<div class="page-head"><h1>데이터 설명</h1></div>', '<p class="lead">우아여행코스는 한국관광공사 <b>TourAPI 국문 관광정보</b>(공공데이터포털)의 여행코스(콘텐츠 유형 25)를 정리합니다. 전체 %d개 중 상세를 받은 %d개를 게시하며, 상세는 호출 한도 때문에 매일 일부씩 쌓입니다. 코스 지역은 대표 좌표를 역지오코딩해 정했고 좌표가 없는 코스는 지역 페이지에 없습니다. 이미지는 사용하지 않습니다.</p>' % (total, n)]
    write("/about/", layout("/about/", "데이터 설명", "우아여행코스가 사용하는 한국관광공사 TourAPI 데이터와 정리 방법을 설명합니다.", "\n".join(body), None, [("홈", "/"), ("데이터 설명", "/about/")]), "0.3")
    body = ['<div class="page-head"><h1>개인정보처리방침</h1></div>', '<p class="lead">우아여행코스는 회원가입·로그인 없이 이용하며 개인정보를 수집하지 않습니다. 사이트 개선을 위해 Google Analytics가 익명 방문 통계를 수집하고, Google AdSense와 쿠팡 파트너스가 광고를 표시하면서 쿠키를 사용할 수 있습니다. 게시된 코스 정보는 공공데이터포털에 공개된 자료입니다.</p>']
    write("/privacy/", layout("/privacy/", "개인정보처리방침", "우아여행코스 개인정보처리방침", "\n".join(body), None, [("홈", "/"), ("개인정보처리방침", "/privacy/")]), sitemap=False)


def finish():
    shutil.copytree(ROOT / "assets", OUT / "assets")
    for nf in ROOT.glob("naver*.html"):
        shutil.copy(nf, OUT / nf.name)
    today = TODAY.isoformat()
    urls = "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (BASE, q(p), today, pr) for p, pr in WRITTEN)
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE, encoding="utf-8")
    (OUT / "CNAME").write_text("wooacourse.wooahouse.com\n", encoding="utf-8")
    nf = layout("/404.html", "페이지를 찾을 수 없습니다", "요청한 페이지를 찾을 수 없습니다.", '<div class="page-head"><h1>페이지를 찾을 수 없습니다</h1></div><div class="chips"><a class="chip" href="/">홈</a><a class="chip" href="/region/">지역별 코스</a></div>', None, None, noindex=True)
    (OUT / "404.html").write_text(nf, encoding="utf-8")
    print("페이지", len(WRITTEN), "(sitemap)")


if __name__ == "__main__":
    build()
