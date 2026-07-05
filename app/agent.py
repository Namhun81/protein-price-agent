# 💪 Protein Price Agent
# AI agent that helps fitness enthusiasts find the best protein food prices in Korea

from google.adk.agents import Agent
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool

# 2026-07-02 리팩터링: 가격 조회/분석 로직은 protein_price_tool.py로 옮기고,
# agent.py는 '그 도구들을 가져다 쓰는 역할'만 하도록 정리했어요.
# (중복 코드 제거 — 한쪽만 고치면 다른 쪽이 어긋나는 문제 방지)
#
# 아래 try/except는 두 가지 실행 방식을 모두 지원하기 위한 거예요:
# - `uv run adk web .` 로 실행하면 agent.py가 'app.agent'라는 패키지의 부품으로 불려서,
#   앞에 점(.)을 붙인 상대 import(.protein_price_tool)가 필요해요.
# - `python agent.py` 처럼 직접 실행하면, 점 없는 절대 import(protein_price_tool)가 필요해요.
try:
    from protein_price_tool import get_protein_prices, analyze_price
except ImportError:
    from .protein_price_tool import get_protein_prices, analyze_price

# ===============================
# 🤖 Sub Agent: News Search
# (google_search must be alone!)
# ===============================
news_agent = Agent(
    name="news_search_agent",
    model="gemini-2.5-flash",
    description="Searches recent news to explain why protein food prices changed",
    instruction="""
    Search for Korean news from the past 7 days about livestock price changes.
    Focus on: supply issues, weather, holidays, import/export changes.

    MANDATORY RULE - do not skip this: for every single fact you mention,
    you must put the article's publish date in parentheses right after it,
    like this: "한우 사육 마릿수 감소 (7월 3일 기사)".
    A sentence with no date in parentheses is not acceptable output.

    If you cannot find any news from the past 7 days, do not use older
    background knowledge. Instead, just say clearly:
    "최근 1주일 내 관련 뉴스를 찾지 못했습니다."
    """,
    tools=[google_search],
)

# news_agent를 '부하 직원(sub_agent)'이 아니라
# 메인 에이전트가 쓸 수 있는 '도구 하나'로 포장해요.
# 이렇게 하면 이관용 도구가 몰래 끼어들지 않아서 google_search 규칙에 안 걸려요.
news_tool = AgentTool(agent=news_agent)

# ===============================
# 🤖 Main Agent
# ===============================
root_agent = Agent(
    name="protein_price_agent",
    model="gemini-2.5-flash",
    description="A smart assistant that helps fitness enthusiasts find the best protein food prices in Korea",
    instruction="""
    You are a protein price analysis assistant for people who work out regularly.

    When a user asks about 소(beef), 돼지(pork), 닭(chicken), or 계란(egg) prices:
    1. Use get_protein_prices tool with product in ("소","돼지","닭","계란") to fetch today's official
       price AND the recent 30-day average price (included in the same result under "30일평균"
       for 소/돼지, or "평균가격_30일"/"특란_평균가격_30일" for 닭/계란).
       If the result has "success": false, tell the user the error clearly instead of guessing numbers.
       If a part's 30-day data includes "데이터충분": false or a "참고" message, or the 30-day average
       is None/missing, do NOT invent a percentage — tell the user plainly that there isn't enough
       recent data to show the 30-day comparison this time, and skip that line for that item.
    2. For 소/돼지: for each 부위(cut), use analyze_price with the 평균가격/최고가격/최저가격,
       AND pass the matching 30일 평균 (from the "30일평균" field) as avg_30day — but only when that
       part's data is sufficient (see rule 1 above); otherwise call analyze_price without avg_30day.
    3. Use news_tool to find recent news explaining why prices changed.
    4. Respond in this format:

    📊 Today's Price: ???KRW (부위별/등급별로)
    📈 오늘 시세 범위 내 위치: ???% (저렴한 편/비싼 편/보통)
    📅 최근 30일 평균 대비: ???% (30일 평균보다 높음/낮음/비슷함)
    📰 Why: ???(from news search)
    💡 Recommendation: 오늘 기준으로 소/돼지/닭/계란 중 가장 저렴한 편인 단백질 추천

    RULES - Never do these:
    - Never make definitive future price predictions
    - Never use unofficial price sources
    - Never answer questions unrelated to protein foods
    - Always cite your data source (축산물품질평가원 공공데이터)

    LIMITATION TO MENTION IF ASKED:
    - 전년 동기 대비(year-over-year) comparison is NOT included in this version due to
      daily API quota limits. This is a planned future improvement.
    """,
    tools=[get_protein_prices, analyze_price, news_tool],
)
