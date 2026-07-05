"""
protein_price_tool.py

소/돼지/닭/계란 가격 조회 + 가격 분석 도구 모음.
agent.py는 이 파일에서 함수를 가져다 씁니다 (중복 코드 제거).

    from protein_price_tool import get_protein_prices, analyze_price

2026-07-02 업데이트:
- "최근 30일 평균 대비 몇 % 높은지/낮은지" 기능 추가
- (전년 동기 대비는 일일 API 할당량 제약으로 이번 버전에는 포함하지 않음.
   향후 CSV 데이터를 별도로 확보하면 추가 예정)
"""

import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("LIVESTOCK_API_KEY")

CATTLE_PORK_URL = "http://data.ekape.or.kr/openapi-data/service/user/grade/consumerPriceDaily"
CHICKEN_URL = "http://data.ekape.or.kr/openapi-data/service/user/grade/poultry/chickenDomae"
EGG_URL = "http://data.ekape.or.kr/openapi-data/service/user/grade/poultry/egg"

# 최근 며칠 평균을 계산할지 (기본 30일)
RECENT_AVG_DAYS = 30

CATTLE_PORK_CODES = {
    "소": {
        "judgeKind": "4301",
        "items": {"안심": "21", "등심": "22", "설도": "36", "양지": "40"},
    },
    "돼지": {
        "judgeKind": "4304",
        "items": {"앞다리": "25", "삼겹살": "27", "갈비": "28"},
    },
}


# ── 작은 도우미 함수들 ──────────────────────────────────────────

def _to_float(value) -> float:
    """'8,500' 같은 문자열도 숫자로 바꿔줘요. (콤마/공백 제거)"""
    if value is None:
        raise ValueError("가격 값이 비어 있어요(None).")
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").strip()
    return float(cleaned)


def _recent_date_range(days_back: int = 14):
    today = datetime.now()
    start = today - timedelta(days=days_back)
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


def _check_result_code(root: ET.Element):
    """API가 '00'(정상) 말고 다른 코드를 주면 에러 메시지를 돌려줘요."""
    result_code = root.findtext(".//resultCode")
    result_msg = root.findtext(".//resultMsg")
    if result_code is not None and result_code != "00":
        return f"API 오류(resultCode={result_code}): {result_msg}"
    return None


def _safe_request(url: str, params: dict):
    """
    요청을 보내고, 문제가 있으면 (None, '에러 설명') 을,
    성공하면 (XML root, None) 을 돌려줘요.
    """
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()  # 500, 404 같은 HTTP 에러면 여기서 예외 발생
    except requests.exceptions.RequestException as e:
        return None, f"네트워크/서버 오류: {e}"

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return None, f"응답을 이해할 수 없는 형식이에요: {response.text[:200]}"

    error_msg = _check_result_code(root)
    if error_msg:
        return None, error_msg

    return root, None


def _average(numbers: list):
    """숫자 리스트의 평균을 계산해요. 리스트가 비어있으면 None을 돌려줘요."""
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 1)


# ── 소/돼지 ──────────────────────────────────────────────────

def _get_cattle_or_pork_prices(product: str) -> dict:
    config = CATTLE_PORK_CODES[product]
    judge_kind = config["judgeKind"]

    for days_ago in range(0, 10):
        check_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y%m%d")
        results = {}
        for part_name, item_cd in config["items"].items():
            params = {
                "serviceKey": API_KEY,
                "standYmd": check_date,
                "judgeKind": judge_kind,
                "itemCd": item_cd,
            }
            root, error = _safe_request(CATTLE_PORK_URL, params)
            if error:
                return {"success": False, "error": error}
            item = root.find(".//item")
            if item is not None:
                results[part_name] = {
                    "평균가격": item.findtext("ntslPrc"),
                    "최고가격": item.findtext("maxPrc"),
                    "최저가격": item.findtext("minPrc"),
                }
        if results:
            return {"success": True, "기준일자": check_date, "가격정보": results}

    return {"success": False, "error": f"{product} 가격 데이터를 최근 10일 안에서 찾지 못했어요."}


def _get_recent_average_cattle_pork(product: str, days: int = RECENT_AVG_DAYS) -> dict:
    """
    최근 N일치 평균가격(ntslPrc)을 부위별로 모아서, 그 평균을 계산해요.
    (재료 창고 문을 하루마다 두드려서, 부위마다 최근 N개 가격을 모으는 거예요)

    할당량 참고: 소(4부위)+돼지(3부위) 30일치 = 약 210번 호출.
    """
    config = CATTLE_PORK_CODES[product]
    judge_kind = config["judgeKind"]

    # 부위별로 최근 가격들을 담을 빈 바구니 준비
    part_price_lists = {part_name: [] for part_name in config["items"]}

    for days_ago in range(days):
        check_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y%m%d")
        for part_name, item_cd in config["items"].items():
            params = {
                "serviceKey": API_KEY,
                "standYmd": check_date,
                "judgeKind": judge_kind,
                "itemCd": item_cd,
            }
            root, error = _safe_request(CATTLE_PORK_URL, params)
            if error:
                # 하루 정도 데이터가 없어도 (주말/공휴일 등) 전체를 실패시키지 않고 그냥 건너뛰어요
                continue
            item = root.find(".//item")
            if item is not None:
                price_text = item.findtext("ntslPrc")
                if price_text:
                    try:
                        part_price_lists[part_name].append(_to_float(price_text))
                    except ValueError:
                        pass

    # 최소 이 정도 날짜는 모여야 "믿을만한 평균"으로 봐요. 너무 적으면 조용히 넘어가지 않고 표시해줘요.
    MIN_DAYS_FOR_RELIABLE_AVG = 5

    averages = {}
    for part_name, prices in part_price_lists.items():
        collected_days = len(prices)
        averages[part_name] = {
            "평균가격_30일": _average(prices),
            "수집된_일수": collected_days,
            "데이터충분": collected_days >= MIN_DAYS_FOR_RELIABLE_AVG,
        }
        if collected_days == 0:
            averages[part_name]["참고"] = "최근 30일 데이터를 하나도 모으지 못했어요. 30일 평균 비교는 이번엔 생략해주세요."
        elif collected_days < MIN_DAYS_FOR_RELIABLE_AVG:
            averages[part_name]["참고"] = f"최근 {collected_days}일치만 모여서 평균이 정확하지 않을 수 있어요."

    return {"success": True, "기간": f"최근{days}일", "부위별_30일평균": averages}


# ── 닭/계란 (기간 단위 조회 + 여러 날짜 모아서 평균까지) ──────────────

def _latest_item_by_date(items):
    """modYmd(발표일) 기준으로 진짜 가장 최근 item을 찾아줘요.
    (API가 항상 최신순으로 주는 게 아닐 수도 있어서, 직접 정렬해요!)"""
    return sorted(items, key=lambda i: i.findtext("modYmd") or "", reverse=True)[0]


def _get_chicken_prices() -> dict:
    # 30일 평균까지 같이 계산할 수 있도록, 조회 기간을 넉넉하게 잡아요
    start_ymd, end_ymd = _recent_date_range(RECENT_AVG_DAYS)
    params = {
        "serviceKey": API_KEY,
        "startYmd": start_ymd,
        "endYmd": end_ymd,
        "numOfRows": "100",
        "pageNo": "1",
    }
    root, error = _safe_request(CHICKEN_URL, params)
    if error:
        return {"success": False, "error": error}

    items = root.findall(".//item")
    if not items:
        return {"success": False, "error": "닭고기 가격 데이터를 찾지 못했어요."}

    latest = _latest_item_by_date(items)

    # 최근 30일치 평균가격(avg) 계산
    avg_prices = []
    for item in items:
        price_text = item.findtext("avg")
        if price_text:
            try:
                avg_prices.append(_to_float(price_text))
            except ValueError:
                pass

    result = {
        "success": True,
        "발표일": latest.findtext("modYmd"),
        "거래종류": latest.findtext("typeName"),
        "평균가격": latest.findtext("avg"),
        "대리점가격": latest.findtext("agency"),
        "마트가격": latest.findtext("mart"),
        "프랜차이즈가격": latest.findtext("franchise"),
        "평균가격_30일": _average(avg_prices),
        "수집된_일수": len(avg_prices),
    }
    if not avg_prices:
        result["참고"] = "최근 30일 데이터를 하나도 모으지 못했어요. 30일 평균 비교는 이번엔 생략해주세요."
    return result


def _get_egg_prices() -> dict:
    start_ymd, end_ymd = _recent_date_range(RECENT_AVG_DAYS)
    params = {
        "serviceKey": API_KEY,
        "startYmd": start_ymd,
        "endYmd": end_ymd,
        "type": "2",  # 1: 산지, 2: 도매
        "numOfRows": "100",
        "pageNo": "1",
    }
    root, error = _safe_request(EGG_URL, params)
    if error:
        return {"success": False, "error": error}

    items = root.findall(".//item")
    if not items:
        return {"success": False, "error": "계란 가격 데이터를 찾지 못했어요."}

    latest = _latest_item_by_date(items)

    # 최근 30일치 특란(special) 기준 평균가격 계산
    avg_prices = []
    for item in items:
        price_text = item.findtext("special")
        if price_text:
            try:
                avg_prices.append(_to_float(price_text))
            except ValueError:
                pass

    result = {
        "success": True,
        "발표일": latest.findtext("modYmd"),
        "거래종류": latest.findtext("typeName"),
        "왕란가격": latest.findtext("verybig"),
        "특란가격": latest.findtext("special"),
        "대란가격": latest.findtext("big"),
        "중란가격": latest.findtext("medium"),
        "소란가격": latest.findtext("small"),
        "특란_평균가격_30일": _average(avg_prices),
        "수집된_일수": len(avg_prices),
    }
    if not avg_prices:
        result["참고"] = "최근 30일 데이터를 하나도 모으지 못했어요. 30일 평균 비교는 이번엔 생략해주세요."
    return result


# ── 에이전트가 실제로 부르는 두 개의 도구 ──────────────────────────

def get_protein_prices(product: str) -> dict:
    """
    한국 축산물품질평가원의 공식 API에서 소/돼지/닭/계란의
    최신 가격 정보 + 최근 30일 평균가격을 가져옵니다.

    Args:
        product (str): 가격을 조회할 축산물 종류. "소", "돼지", "닭", "계란" 중 하나.

    Returns:
        dict: 성공 시 {"success": True, ...가격정보..., "30일평균": {...}}
              실패 시 {"success": False, "error": "에러 설명"}
    """
    if not API_KEY:
        return {"success": False, "error": "LIVESTOCK_API_KEY가 .env 파일에 설정되어 있지 않아요."}

    if product in ("소", "돼지"):
        today_result = _get_cattle_or_pork_prices(product)
        if not today_result.get("success"):
            return today_result
        avg_result = _get_recent_average_cattle_pork(product)
        today_result["30일평균"] = avg_result.get("부위별_30일평균")
        return today_result

    elif product == "닭":
        return _get_chicken_prices()
    elif product == "계란":
        return _get_egg_prices()
    else:
        return {"success": False, "error": f"'{product}'는 지원하지 않아요. 소/돼지/닭/계란 중에서 골라주세요."}


def analyze_price(current_price, max_price, min_price, avg_30day=None) -> dict:
    """
    오늘의 최고가/최저가 범위 안에서 평균가격이 저렴한 편인지 비싼 편인지,
    그리고 (있으면) 최근 30일 평균과 비교해서 몇 % 높은지/낮은지 분석합니다.
    문자열("8,500" 같은 콤마 포함 값)도 안전하게 처리합니다.

    Args:
        current_price: 오늘의 평균 가격 (숫자 또는 문자열).
        max_price: 오늘의 최고 가격.
        min_price: 오늘의 최저 가격.
        avg_30day: 최근 30일 평균 가격 (없으면 None, 이 경우 30일 비교는 생략).

    Returns:
        dict: 성공 시 위치(%), 저렴/비쌈 판정, 30일 대비 결과 포함.
              실패 시 {"success": False, "error": ...}
    """
    try:
        current_price = _to_float(current_price)
        max_price = _to_float(max_price)
        min_price = _to_float(min_price)
    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"가격 값을 숫자로 바꿀 수 없어요: {e}"}

    if max_price == min_price:
        position_percent = 50.0
    else:
        position_percent = ((current_price - min_price) / (max_price - min_price)) * 100

    if position_percent < 35:
        status, emoji = "저렴한 편", "🟢"
    elif position_percent > 65:
        status, emoji = "비싼 편", "🔴"
    else:
        status, emoji = "보통", "🟡"

    result = {
        "success": True,
        "current_price": current_price,
        "position_percent": round(position_percent, 1),
        "status": status,
        "emoji": emoji,
    }

    # 30일 평균이 있으면, 그것과도 비교해요
    if avg_30day is not None:
        try:
            avg_30day = _to_float(avg_30day)
            if avg_30day > 0:
                diff_percent = ((current_price - avg_30day) / avg_30day) * 100
                result["avg_30day"] = avg_30day
                result["diff_from_30day_percent"] = round(diff_percent, 1)
                if diff_percent > 5:
                    result["diff_from_30day_status"] = "📈 최근 30일 평균보다 높아요"
                elif diff_percent < -5:
                    result["diff_from_30day_status"] = "📉 최근 30일 평균보다 낮아요"
                else:
                    result["diff_from_30day_status"] = "➡️ 최근 30일 평균과 비슷해요"
        except (ValueError, TypeError):
            pass  # 30일 평균값이 이상하면 그냥 생략하고 넘어가요

    return result


if __name__ == "__main__":
    for product in ["소", "돼지", "닭", "계란"]:
        print(f"\n===== {product} 가격 =====")
        print(get_protein_prices(product))
