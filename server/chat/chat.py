import asyncio
import re
import time

import httpx
from typing import List, Optional
from abc import ABC
from openai import OpenAI
from ollama import Client
from starlette.concurrency import run_in_threadpool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.config import Configs
from db.repository.conversation_repository import add_conversation_to_db
from db.repository.message_repository import get_conversation_messages, add_message_to_db
from rag.kb.api.kb_doc_api import search_docs
from rag.reranker.reranker import LangchainReranker
from server.utils.utils import LLMType, replace_ip_with_targetip
from utils.log_common import build_logger

logger = build_logger()

_LLM_SEP = "=" * 72


def _log_llm_request(model_name: str, history: List) -> None:
    """Print the full LLM request (message history) to stdout.

    The output is captured by the benchmark runner and written to the
    per-benchmark .log file alongside all other stdout.
    """
    print(f"\n{_LLM_SEP}", flush=True)
    print(f"  [LLM-REQUEST]  model={model_name}  messages={len(history)}", flush=True)
    print(_LLM_SEP, flush=True)
    for i, msg in enumerate(history, 1):
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        print(f"\n  -- Message {i}/{len(history)} | role={role} --", flush=True)
        print(content, flush=True)
    print(f"\n{_LLM_SEP}\n", flush=True)



class OpenAIChat(ABC):
    def __init__(self, config):
        self.config = config
        self.client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url, timeout=config.timeout)
        self.model_name = self.config.llm_model_name

    @retry(
        stop=stop_after_attempt(3),  # Stop after 3 attempts
    )
    def chat(self, history: List, think: bool = False) -> str:
        try:
            _log_llm_request(self.model_name, history)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=history,
                temperature=self.config.temperature,
            )
            ans = response.choices[0].message.content
            print(ans)
            return ans
        except (httpx.HTTPStatusError, httpx.ReadTimeout,
                    httpx.ConnectTimeout, ConnectionError) as e:
            if getattr(e, "response", None) and e.response.status_code == 429:
                # Rate limit error, wait longer
                time.sleep(2)
            raise  # Re-raise the exception to trigger retry
        except Exception as e:
            return f"**ERROR**: {str(e)}"

# def _log_llm_response(answer: str, thinking: str | None = None) -> None:
#     """Print the full LLM response (and optional reasoning trace) to stdout."""
#     print(f"\n{_LLM_SEP}", flush=True)
#     print("  [LLM-RESPONSE]", flush=True)
#     print(_LLM_SEP, flush=True)
#     if thinking:
#         print("\n  -- <think> (reasoning trace) --", flush=True)
#         print(thinking, flush=True)
#         print("\n  -- </think> --\n", flush=True)
#     print("  -- Final Answer --", flush=True)
#     print(answer, flush=True)
#     print(f"\n{_LLM_SEP}\n", flush=True)

class OllamaChat(ABC):
    def __init__(self, config):
        self.config = config
        self.client = Client(host=self.config.base_url)
        self.model_name = self.config.llm_model_name

    def chat(self, history: List[dict], think: bool = False) -> str:

        try:
            _log_llm_request(self.model_name, history)
            stream = self.client.chat(
                model=self.model_name,
                messages=history,
                options={
                    "temperature": self.config.temperature,
                },
                think=think,
                keep_alive=-1,
                stream=True
            )

            in_thinking = False
            thinking_chunks: list[str] = []
            answer_chunks: list[str] = []
            print(f"\n{_LLM_SEP}", flush=True)
            print("  [LLM-RESPONSE]", flush=True)
            print(_LLM_SEP, flush=True)

            for chunk in stream:
                if chunk.message.thinking and not in_thinking:
                    in_thinking = True
                    print("\n  -- <think> (reasoning trace) --", flush=True)

                if chunk.message.thinking:
                    thinking_chunks.append(chunk.message.thinking)
                    print(chunk.message.thinking, end='', flush=True)
                elif chunk.message.content:
                    answer_chunks.append(chunk.message.content)
                    if in_thinking:
                        in_thinking = False
                        print("\n  -- </think> --\n", flush=True)
                        print("  -- Final Answer --", flush=True)
                    print(chunk.message.content, end='', flush=True)

            print(f"\n{_LLM_SEP}\n", flush=True)
            # thinking = ''.join(thinking_chunks)
            answer = ''.join(answer_chunks)

            # for chunk in stream:
            #     msg = chunk.message if hasattr(chunk, "message") else chunk.get("message", {})
            #     t = getattr(msg, "thinking", None) or (msg.get("thinking") if isinstance(msg, dict) else None)
            #     c = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
            #     if t:
            #         thinking_parts.append(t)
            #     if c:
            #         content_parts.append(c)

            # thinking = "".join(thinking_parts) or None
            # ans = "".join(content_parts)
            return answer
        except httpx.HTTPStatusError as e:
            return f"**ERROR**: {str(e)}"


def _chat(query: str, kb_name=None, conversation_id=None, kb_query=None, summary=True, think=False):
    try:
        if Configs.basic_config.enable_rag and kb_name is not None:
            docs = asyncio.run(run_in_threadpool(search_docs,
                                                 query=kb_query,
                                                 knowledge_base_name=kb_name,
                                                 top_k=Configs.kb_config.top_k,
                                                 score_threshold=Configs.kb_config.score_threshold,
                                                 file_name="",
                                                 metadata={}))

            reranker_model = LangchainReranker(top_n=Configs.kb_config.top_n,
                                               name_or_path=Configs.llm_config.rerank_model)

            docs = reranker_model.compress_documents(documents=docs, query=kb_query)

            if len(docs) == 0:
                context = ""
            else:
                context = "\n".join([doc["page_content"] for doc in docs])

            if context:
                context = replace_ip_with_targetip(context)
                query = f"{query}\n\n\n Ensure that the **Overall Target** IP or the IP from the **Initial Description** is prioritized. You will respond to questions and generate tasks based on the provided penetration test case materials: {context}. \n"

        if conversation_id is not None and len(query) > 10000:
            query = query[:10000]
        else:
            query = query[:Configs.llm_config.context_length]

        # Initialize or retrieve conversation ID
        conversation_id = add_conversation_to_db(Configs.llm_config.llm_model_name, conversation_id)

        history = [
            {
                "role": "system",
                "content": "You are a helpful assistant",
            }
        ]
        # Retrieve message history from database, and limit the number of messages
        for msg in get_conversation_messages(conversation_id)[-Configs.llm_config.history_len:]:
            history.append({"role": "user", "content": msg.query})
            history.append({"role": "assistant", "content": msg.response})

        # Add user query to the message history
        history.append({"role": "user", "content": query})

        # Initialize the correct model client
        if Configs.llm_config.llm_model == LLMType.OPENAI:
            client = OpenAIChat(config=Configs.llm_config)
        elif Configs.llm_config.llm_model == LLMType.OLLAMA:
            client = OllamaChat(config=Configs.llm_config)
        else:
            return "Unsupported model type", conversation_id

        # Get response from the model
        response_text = client.chat(history, think)

        # Save both query and response to the database
        if summary:
            add_message_to_db(conversation_id, Configs.llm_config.llm_model_name, query, response_text)

        return response_text, conversation_id

    except Exception as e:
        print(e)
        return f"**ERROR**: {str(e)}", conversation_id
