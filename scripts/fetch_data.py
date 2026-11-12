# -*- coding: utf-8 -*-
"""
우아여행코스 수집기 — 한국관광공사 TourAPI 국문 관광정보 v2 (data.go.kr 15101578, apis.data.go.kr/B551011/KorService2)

1) areaBasedList2(contentTypeId=25, 여행코스)로 전체 코스 목록(약 1,070건)과 지역별(areaCode) 필터 목록으로 코스의 시도를 알아내 data/list.json.gz 에 저장.
2) 처음 보는 코스만 detailCommon2(개요)·detailIntro2(거리·소요시간·테마·일정)·detailInfo2(코스 지점 목록)로 상세를 받아
   data/details/{id//2000}.json.gz 에 누적(코스당 3호출). 하루 호출 예산(기본 800)만큼만 받고 멈춘다 — 내일 다시 돌리면 이어서 받는다.
3) 목록에서 사라진 코스는 캐시에서도 제거. 응답이 JSON이 아니면(일일 한도·초당 제한 XML 오류) 코드 22는 저장 후 종료, 23은 쉬고 재시도.
키: 환경변수 API_KEY → DATA_GO_KR_API_KEY → 로컬 ../hosppass/.env 의 API_KEY (코드에 넣지 않는다).
사용: python scripts/fetch_data.py [--budget N]
"""
import gzip, json, os, re, sys, time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DET = DATA / "details"
DET.mkdir(parents=True, exist_ok=True)
BASE = "https://apis.data.go.kr/B551011/KorService2/"
GAP = 0.3
BUCKET = 2000
CALLS = 0
AREAS = {"1": "서울", "2": "인천", "3": "대전", "4": "대구", "5": "광주", "6": "부산", "7": "울산", "8": "세종", "31": "경기", "32": "강원", "33": "충북", "34": "충남",
         "35": "경북", "36": "경남", "37": "전북", "38": "전남", "39": "제주"}


class DailyLimit(Exception):
    pass


def api_key():
    for name in ("API_KEY", "DATA_GO_KR_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    for p in (ROOT / ".env", ROOT.parent / "hosppass" / ".env"):
        if p.exists():
            m = re.search(r"^API_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip("\"'")
    sys.exit("환경변수 API_KEY 가 필요합니다.")


KEY = api_key()
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"


def call(op, **params):
    """JSON body 반환. 일일 한도(코드 22)면 DailyLimit, 초당 제한(23)이면 쉬고 재시도."""
    global CALLS
    last = ""
    for attempt in range(8):
        try:
            CALLS += 1
            r = S.get(BASE + op, params=dict(serviceKey=KEY, MobileOS="ETC", MobileApp="wooacourse", _type="json", **params), timeout=90)
            txt = r.content.decode("utf-8", "replace")
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND" in txt or "<returnReasonCode>23<" in txt:
                last = "rate"
                time.sleep(15 + 5 * attempt)
                continue
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS" in txt or "<returnReasonCode>22<" in txt:
                raise DailyLimit(txt[:200])
            j = json.loads(txt)
            h = j["response"]["header"]
            if h["resultCode"] != "0000":
                raise RuntimeError("%s %s" % (h["resultCode"], h["resultMsg"]))
            return j["response"]["body"]
        except (requests.RequestException, ValueError) as e:
            last = str(e)
            time.sleep(3 + 3 * attempt)
    raise RuntimeError("API 실패: %s %s" % (op, last))


def items(body):
    it = (body.get("items") or {})
    if not it:
        return []
    it = it.get("item") if isinstance(it, dict) else it
    return it if isinstance(it, list) else ([it] if it else [])


def pull(op, **params):
    out, page, n = [], 1, 1000
    while True:
        b = call(op, numOfRows=n, pageNo=page, **params)
        out += items(b)
        total = int(b.get("totalCount") or 0)
        if page * n >= total:
            return out
        page += 1
        time.sleep(GAP)


def kakao_key():
    for name in ("KAKAO_REST_KEY",):
        if os.environ.get(name):
            return os.environ[name].strip()
    for p in (ROOT / ".env", ROOT.parent / "hosppass" / ".env"):
        if p.exists():
            m = re.search(r"^KAKAO_REST_KEY\s*=\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip("\"'")
    return ""


def geocode(rows):
    """코스 대표 좌표 → 시도·시군구(카카오 coord2regioncode). 한 번 구한 값은 data/geo.json 에 저장해 재사용한다.
    TourAPI 여행코스는 areaCode 가 거의 비어 있어(1,068개 중 49개) 좌표로 지역을 정한다."""
    gp = DATA / "geo.json"
    geo = json.loads(gp.read_text(encoding="utf-8")) if gp.exists() else {}
    key = kakao_key()
    todo = [r for r in rows if r["id"] not in geo and r["x"] and r["y"]]
    if not key:
        print("KAKAO_REST_KEY 없음 — 지역 미확인 %d건" % len(todo))
        return geo
    n = 0
    for r in todo:
        try:
            j = S.get("https://dapi.kakao.com/v2/local/geo/coord2regioncode.json", params={"x": r["x"], "y": r["y"]}, headers={"Authorization": "KakaoAK " + key}, timeout=30).json()
            docs = [d for d in j.get("documents", []) if d.get("region_type") == "B"] or j.get("documents", [])
            if docs:
                geo[r["id"]] = [docs[0].get("region_1depth_name", ""), docs[0].get("region_2depth_name", "")]
                n += 1
        except Exception as e:
            print("  지오코딩 실패", r["id"], str(e)[:60])
        time.sleep(0.05)
    gp.write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("지오코딩 신규 %d건, 보유 %d건" % (n, len(geo)))
    return geo


def bucket_of(cid):
    return int(cid) // BUCKET


def load_details():
    det = {}
    for p in DET.glob("*.json.gz"):
        det.update(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
    return det


def save_details(det):
    byb = {}
    for k, d in det.items():
        byb.setdefault(bucket_of(k), {})[k] = d
    keep = set()
    for b, its in byb.items():
        p = DET / ("%d.json.gz" % b)
        keep.add(p.name)
        blob = json.dumps(its, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if p.exists() and gzip.decompress(p.read_bytes()) == blob:
            continue
        with gzip.GzipFile(p, "wb", compresslevel=9, mtime=0) as f:
            f.write(blob)
    for p in DET.glob("*.json.gz"):
        if p.name not in keep:
            p.unlink()


def fetch_one(cid):
    d = {}
    c = items(call("detailCommon2", contentId=cid))
    if not c:
        return None
    d["common"] = {k: c[0].get(k, "") for k in ("title", "overview", "homepage", "tel", "telname", "addr1", "zipcode")}
    time.sleep(GAP)
    i = items(call("detailIntro2", contentId=cid, contentTypeId=25))
    d["intro"] = {k: (i[0].get(k, "") if i else "") for k in ("distance", "schedule", "taketime", "theme")}
    time.sleep(GAP)
    st = items(call("detailInfo2", contentId=cid, contentTypeId=25, numOfRows=60, pageNo=1))
    d["stops"] = [{"n": x.get("subname", ""), "id": x.get("subcontentid", ""), "o": x.get("subdetailoverview", "")} for x in sorted(st, key=lambda x: int(x.get("subnum") or 0))]
    return d


def main():
    budget = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else int(os.environ.get("DAILY_BUDGET", "800"))
    lst = pull("areaBasedList2", contentTypeId=25, arrange="Q")
    print("코스 목록", len(lst))
    area_of = {}
    for code, name in AREAS.items():
        for x in pull("areaBasedList2", contentTypeId=25, areaCode=code):
            area_of[x["contentid"]] = name
        time.sleep(GAP)
    print("TourAPI 시도 확인", len(area_of), "/", len(lst))
    lp = DATA / "list.json.gz"
    if lp.exists():
        prev = len(json.loads(gzip.open(lp, "rt", encoding="utf-8").read()))
        if prev > 100 and len(lst) < prev * 0.6:
            sys.exit("목록이 직전(%d)보다 크게 줄어(%d) 중단" % (prev, len(lst)))
    rows = [{"id": x["contentid"], "title": x.get("title", ""), "mod": x.get("modifiedtime", ""), "x": x.get("mapx", ""), "y": x.get("mapy", ""), "area": area_of.get(x["contentid"], "")} for x in lst]
    geo = geocode(rows)
    for r in rows:
        g = geo.get(r["id"])
        if g:
            r["sido"], r["sgg"] = g
    with gzip.open(lp, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    ids = {x["id"]: x for x in rows}
    det = load_details()
    n0 = len(det)
    det = {k: v for k, v in det.items() if k in ids}
    todo = [i for i in ids if i not in det]
    todo.sort(key=lambda i: -int(ids[i]["mod"] or 0))  # 최근 수정된 코스부터
    todo = todo[:max(0, (budget - CALLS) // 3)]
    print("캐시 %d → 유지 %d, 이번에 받을 코스 %d개 (호출 약 %d, 예산 %d)" % (n0, len(det), len(todo), len(todo) * 3, budget), flush=True)
    done = fail = 0
    try:
        for n, cid in enumerate(todo, 1):
            try:
                d = fetch_one(cid)
                if d:
                    det[cid] = d
                    done += 1
            except DailyLimit:
                raise
            except Exception as e:
                fail += 1
                print("  실패", cid, str(e)[:80])
                if fail > 30:
                    print("실패 과다, 중단")
                    break
            if n % 100 == 0:
                save_details(det)
                print("  %d/%d 실패 %d" % (n, len(todo), fail), flush=True)
            time.sleep(GAP)
    except DailyLimit as e:
        print("일일 호출 한도 도달 — 저장하고 종료:", str(e)[:80].replace(chr(10), " "))
    save_details(det)
    print("완료: 목록 %d, 상세 보유 %d, 이번 신규 %d (실패 %d)" % (len(rows), len(det), done, fail))


if __name__ == "__main__":
    main()
