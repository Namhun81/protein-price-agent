# 🥩 Protein Price Agent

> A concierge AI agent that tells fitness-focused Koreans which protein food (beef, pork, chicken, or egg) is the smartest, cheapest choice **today** — backed by official government price data, recent price trends, and real-time news context.

**Kaggle x Google 5-Day AI Agents Intensive — Capstone Project**
**Track:** Concierge Agents

---

## 🎯 The Problem

> *"I need protein for my workouts, but I'm tired of chicken every day. I want beef, but it's expensive. Which of beef, pork, chicken, or egg is actually the smart choice to eat today?"*

Fitness enthusiasts in Korea constantly face this decision, but answering it well requires combining three separate things a person can't easily do in real time:
1. **Official, up-to-date market prices** across four different food categories (each published through a different government API with a different data shape)
2. **Context on *why* prices moved** (supply shocks, avian flu, holidays, feed cost changes)
3. **A clear, actionable recommendation** — not just raw numbers

Doing this manually means checking multiple government portals, reading news separately, and doing the comparison math yourself — every single day.

## 🤖 Why an AI Agent (not just a script)?

A simple script could fetch prices and print them. But this task needs **judgment and orchestration**, not just data-fetching:
- The agent must **decide which tool to call** (price lookup vs. price-position analysis vs. news search) and **in what order**, based on what the user actually asked.
- It must **combine structured data** (today's price range, recent trend) **with unstructured reasoning** (why did this happen? is chicken worth recommending given the news?).
- It must **know its own limits** — e.g., refusing to predict future prices, and staying on-topic (protein food only) even when asked something unrelated.

This is exactly the kind of multi-step, tool-using, judgment-requiring task that an LLM agent — not a fixed script — is suited for.

## 🏗️ Architecture

```
                    ┌─────────────────────────┐
                    │   User (chat / voice)   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   protein_price_agent    │  (gemini-2.5-flash)
                    │   — the "concierge"      │
                    └──┬──────────┬─────────┬──┘
                       │          │         │
         ┌─────────────▼──┐  ┌────▼─────┐  ┌▼──────────────────┐
         │ get_protein_    │  │ analyze_  │  │ news_tool          │
         │ prices          │  │ price     │  │ (AgentTool wrapping │
         │ (function tool) │  │ (function │  │  news_search_agent, │
         │                 │  │  tool)    │  │  which uses          │
         │ Calls KAPE      │  │           │  │  google_search)      │
         │ open APIs       │  │ Position- │  │                      │
         │ (beef/pork/     │  │ in-range  │  │ Explains WHY prices  │
         │  chicken/egg)   │  │ + 30-day  │  │ moved (news context) │
         │ + 30-day avg    │  │ trend     │  │                      │
         └─────────────────┘  └───────────┘  └────────────────────┘
```

**Why `news_search_agent` is wrapped in an `AgentTool` instead of used as a `sub_agent`:** ADK's built-in `google_search` tool cannot be combined with other tools in the same model request. Using `sub_agents=[...]` causes ADK to automatically inject a hidden `transfer_to_agent` tool, which triggers this restriction. Wrapping the sub-agent in `AgentTool` and exposing it as a normal tool on the root agent avoids the conflict while still letting the root agent delegate the news-search task.

**Why not MCP?** I initially considered MCP — the standard way agents connect to external tools — for the news search. In the end, ADK's built-in `google_search` tool already handled this reliably, so I wrapped the news agent as an `AgentTool` instead, avoiding the extra time needed to find and vet a separate MCP server. The capstone's 3-of-6 technology requirement was already met by Agent/ADK, Security, and Skills, so this was a deliberate choice, not a gap.

## ✨ Features

- **4-category price lookup** (beef, pork, chicken, egg) from Korea's official livestock data authority (KAPE — Korea Institute for Animal Products Quality Evaluation)
- **Today's price-range analysis**: for beef/pork, each cut is scored as *cheap / average / expensive* based on where today's average price sits between today's high and low
- **Recent 30-day trend comparison**: today's price is also compared against the average of the last 30 days, so the agent can say whether today is higher, lower, or about the same as the recent trend (not just today's snapshot)
- **News-grounded explanations**: a dedicated sub-agent searches recent Korean news to explain *why* a price moved (supply issues, avian flu, holidays, feed costs, etc.)
- **Cross-category recommendation**: the agent compares all four proteins and recommends the smartest one to buy today
- **Safety rails**: the agent will not make future price predictions, will not use unofficial data sources, and will not answer questions unrelated to protein food prices

## 🧩 Capstone Technologies Demonstrated

| # | Technology | How it's demonstrated |
|---|---|---|
| 1 | **Agent (ADK)** | `root_agent` built with `google.adk.agents.Agent`, orchestrating multiple tools based on natural-language instructions (see `app/agent.py`) |
| 2 | **Multi-agent tool use** | `news_search_agent` is a separate agent, exposed to the root agent via `AgentTool` — a working example of agent-as-tool composition |
| 3 | **Security** | The API key is loaded from a local `.env` file via `python-dotenv` and is never hardcoded or logged; `.env` is excluded from version control via `.gitignore` |
| 4 | **Antigravity** | Used throughout development for vibe-coding, debugging, and iterating on the agent (shown in demo video) |
| 5 | **Deployability** | Designed to run locally via `adk web` and is deployable to Vertex AI Agent Engine / Cloud Run (shown in demo video) |
| 6 | **Skills** | A companion `SKILL.md` documents the agent's conventions and constraints for future development |

## 📊 Data Sources

All price data comes from **KAPE (축산물품질평가원 / Korea Institute for Animal Products Quality Evaluation)** open APIs, published via Korea's public data portal ([data.go.kr](https://www.data.go.kr)):

| Product | Endpoint | Update cycle |
|---|---|---|
| Beef / Pork | `data.ekape.or.kr/openapi-data/service/user/grade/consumerPriceDaily` | Daily |
| Chicken (wholesale) | `data.ekape.or.kr/openapi-data/service/user/grade/poultry/chickenDomae` | Periodic (date-range query) |
| Egg | `data.ekape.or.kr/openapi-data/service/user/grade/poultry/egg` | Periodic (date-range query) |

News context is retrieved live via Gemini's built-in `google_search` tool at query time.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A Gemini API key ([Google AI Studio](https://aistudio.google.com))
- A KAPE (축산물품질평가원) OpenAPI service key, free at [data.go.kr](https://www.data.go.kr)

### Setup

```bash
git clone https://github.com/Namhun81/protein-price-agent.git
cd protein-price-agent

# Create and activate a virtual environment first
uv venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

cd app
# Create your .env file
echo "LIVESTOCK_API_KEY=your_kape_key_here" >> .env
echo "GOOGLE_API_KEY=your_gemini_key_here" >> .env

# Run the agent
uv run adk web . --host 127.0.0.1 --port 8080
```

Then open `http://127.0.0.1:8080` in your browser and try:

```
오늘 소고기 가격이 왜 이런지 최근 뉴스도 같이 찾아서 알려줘
지금 소, 돼지, 닭, 계란 중에 가장 저렴한 게 뭐야?
```

## ⚠️ Limitations & Disclaimers

- This agent **never predicts future prices** — it only analyzes today's official data against today's own price range, the recent 30-day trend, and recent news, by design.
- **Year-over-year comparison is not included** in this version. KAPE's daily price API only returns one date per call, so computing a full prior-year comparison would require far more API calls than the free-tier daily quota allows. This is left as a planned future improvement (e.g., by pre-collecting a historical CSV instead of calling the live API).
- **API quota note**: the 30-day trend feature calls the beef/pork price API once per cut per day to compute the recent average — about 120 calls if you ask about beef only (4 cuts × 30 days), about 90 calls for pork only (3 cuts × 30 days), and about 210 calls if you compare both beef and pork in the same conversation. This is well within a free-tier developer account's daily call limit for normal demo use, but is worth knowing if you plan to call the agent very frequently in a short period.
- Chicken and egg prices may lag by a few days depending on when KAPE last published data; the agent automatically falls back to the most recent available date.
- Free-tier Gemini API quotas may limit heavy interactive use; production deployment would use a billed tier.
- Beef and pork prices are based on official **consumer-price** survey data (a national average, so actual prices may vary by store/region), while chicken and egg prices are based on **wholesale** data, which may run slightly lower than what you'd pay at a supermarket.
- News search results are generated by an LLM-based sub-agent and, due to the probabilistic nature of AI responses, publish dates for cited news are not always guaranteed to appear in every answer, even when explicitly instructed.

## 🛠️ Built With

- [Google Agent Development Kit (ADK) 2.0](https://google.github.io/adk-docs/)
- Gemini 2.5 Flash
- Python, `requests`, `python-dotenv`
- KAPE Open API (Korea Institute for Animal Products Quality Evaluation)
- Antigravity (development environment)

## 👤 Author

Namhun ([@Namhun81](https://github.com/Namhun81)) — built as part of the Kaggle x Google 5-Day AI Agents Intensive, July 2026.
