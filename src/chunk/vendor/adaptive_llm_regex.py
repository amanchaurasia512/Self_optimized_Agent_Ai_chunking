# Vendored from ekimetrics/adaptive-chunking, commit ea87ce8: _build_few_shot_prompt (paper/replicate.py, lines 97-134)
# and LLMRegexSplitter + extract_llm_regex (paper/splitters.py, line 532 to end). Verbatim.
# MIT License, Copyright (c) 2026 Ekimetrics; full text in src/chunk/vendor/LICENSE_adaptive_chunking
import json
import re
from pathlib import Path
from typing import Awaitable, Callable

from src.chunk.vendor.adaptive_splitters import combine_blocks, count_tokens, regex_splitter


def _build_few_shot_prompt() -> str:
    """Load the few-shot example and build the LLM regex prompt."""
    example_path = Path(__file__).parent.parent / "few_shot_examples" / "hccr_report_md_adi.json"
    with open(example_path, "r", encoding="utf-8") as f:
        example = json.load(f)

    return f"""<Task>
Your task is to split a long document into self-contained and logically complete chunks to be used in a Retrieval Augmented Generation (RAG) system. Given a document text, choose the best **unique** regular-expression to be used as a *delimiter* to split it into small chunks using the Python `re` engine and the `re.split` function.
</Task>

<Output requirements>
You **must** return only the answer in this format:
    <regex>regex pattern here</regex>
</Output requirements>

<Splitting guidelines>
    - The regex pattern **must** be valid.
    - The chunks should be self-contained, logically complete and not too large.
    - Do not split paragraphs.
    - Do not split tables, marked between <Table> </Table> tags.
    - Do not split figures, marked between <Figure> </Figure> tags.
    - Do not split lists of short elements.
    - Do not split titles from the text that follows them.
    - Do not split footnotes from their parent text.
</Splitting guidelines>

<Splitting example>
    <Example of input text>
{example["input"]}
    </Example of input text>

    <Expected answer>
        <regex>{example["output"]}</regex>
    </Expected answer>
</Splitting example>

Now, please apply this method to the following text between <Input> and </Input> markers:
"""


class LLMRegexSplitter():
    def __init__(self,
                 base_prompt: str,
                 async_client_completion_func: Awaitable[str],
                 count_tokens_func: Callable[[str], int] = count_tokens,
                 context_tokens: int = 8000,
                 ):

        self.base_prompt = base_prompt
        self.count_tokens_func = count_tokens_func
        self.async_client_completion_func = async_client_completion_func
        self.context_tokens = context_tokens

    async def split_text(self, text: str) -> list[str]:
        lines = text.splitlines(keepends=True)
        document_context = combine_blocks(lines, max_tokens=self.context_tokens, count_tokens_func=self.count_tokens_func)
        prompt = self.base_prompt + "<Input>" + document_context + "</Input>"
        response = await self.async_client_completion_func(prompt)
        regex_pattern = extract_llm_regex(response)
        if regex_pattern is None:
            return [text]
        splits = regex_splitter(text, regex_pattern, attach_to="start")
        return splits


def extract_llm_regex(answer: str) -> str:
    """
    Given an LLM answer containing a <regex>...</regex> block,
    returns the raw pattern string inside those tags and None if the pattern is not valid.
    """
    m = re.search(r"<regex>\s*([\s\S]+?)\s*</regex>", answer, re.IGNORECASE)
    if not m:
        return None
    pattern = m.group(1).strip()
    try:
        re.compile(pattern)
        return pattern
    except re.error:
        def _esc_hyphen(match: re.Match) -> str:
            return re.sub(r"(?<!\\)(?<=.)-(?=[^]])", r"\-", match.group(0))
        pattern = re.sub(r"\[[^\]]+\]", _esc_hyphen, pattern)
        try:
            re.compile(pattern)
            return pattern
        except re.error:
            return None
