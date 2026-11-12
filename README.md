# 우아여행코스 (wooacourse)

한국관광공사 TourAPI 국문 관광정보 v2(`apis.data.go.kr/B551011/KorService2`, 콘텐츠 유형 25=여행코스, 약 1,070개)로 만든 여행 코스 사이트(Python 정적 생성기). https://wooacourse.wooahouse.com

- `scripts/fetch_data.py` — `areaBasedList2`로 목록, `detailCommon2`(개요)·`detailIntro2`(거리·소요시간·테마·일정)·`detailInfo2`(코스 지점)로 코스당 3호출 상세를 받아 `data/details/{id//2000}.json.gz`에 누적. 하루 예산 기본 800~1000호출(TourAPI 일일 한도는 약 3,300호출에서 걸림(2026-11-12 관측)).
- **지역**: TourAPI 여행코스는 `areaCode`가 거의 비어 있어(1,068개 중 49개) 대표 좌표를 카카오 `coord2regioncode`로 역지오코딩해 `data/geo.json`에 저장(시크릿 `KAKAO_REST_KEY`, 로컬은 `../hosppass/.env`). 좌표가 없는 코스는 빌드에서 제목·개요의 시군구 이름으로 추정, 그래도 없으면 지역 페이지 제외.
- `theme`은 대부분 '지자체'라 쓰지 않는다. 당일/1박2일/2박3일+는 `taketime` 문자열에서 '박' 유무로 판정.
- 코스·지점 설명은 일부만 발췌(저작권·중복콘텐츠), 이미지는 미사용.
- `scripts/build_site.py` — 코스 상세, 지역·시군구·소요시간 허브, 2개 이상 코스에 나오는 장소 페이지(`/place/{id}/`), 검색 인덱스.
- Actions: 매일 KST 05:00 fetch → 데이터 커밋 → 빌드 → 배포. 시크릿 `API_KEY`, `KAKAO_REST_KEY` 필요.
