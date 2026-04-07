from openai import OpenAI
from dotenv import load_dotenv
import os 
import json

# load env file
load_dotenv()
api_key = os.environ.get("OPENAI_API_KEY")
# connect to api
client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"    
)


# system prompt
FINANCIAL_ANALYST_PROMPT = """
You are a senior financial analyst with expertise in reading SEC filings, 
earnings reports, and financial statements.

When answering questions:
- Always cite the specific document, section, or page you are drawing from
- Quote exact numbers rather than approximating
- Flag any data that seems inconsistent or unusual
- If a question cannot be answered from the provided documents, say so clearly
  rather than guessing
- Structure answers with a direct answer first, then supporting evidence

When analyzing financial metrics:
- Calculate year-over-year changes when relevant
- Put numbers in context (e.g. is a 5% margin high or low for this industry?)
- Distinguish between GAAP and non-GAAP figures when both appear

Format your responses as:
ANSWER: [direct answer in 1-2 sentences]
EVIDENCE: [specific data points and where they come from]
CONTEXT: [any important caveats or additional context]
"""

# API call
response = client.chat.completions.create(
    model = "openai/gpt-4o-mini",
    messages = [
        {
            "role": "system",
            "content": FINANCIAL_ANALYST_PROMPT
        },
        {
            "role": "user",
            "content": "What was Lam Research's total revenue in fiscal year 2024?"
        }
    ]
)

print(response.choices[0].message.content)


# Test different prompts
prompts = {
    "no system prompt": "",
    "generic assistant": "You are a helpful assistant",
    "financial analyst": FINANCIAL_ANALYST_PROMPT
}

question = "What was Lam Research's revenue growth last year and what drove it?"

for name, prompt in prompts.items():
    messages = []
    if prompt:
        messages.append({"role": "system", "content":prompt})
    messages.append({"role":"user", "content":question})

    response = client.chat.completions.create(
        model = "openai/gpt-4o-mini",
        messages = messages
    )

    print(f"\n --- {name} ---")
    print(response.choices[0].message.content)
    print()
