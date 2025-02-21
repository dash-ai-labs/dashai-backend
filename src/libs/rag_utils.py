import logging
import re
from typing import Any, List, Sequence

from llama_index.core.constants import DEFAULT_CHUNK_SIZE
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.core.node_parser.text.sentence import SENTENCE_CHUNK_OVERLAP
from llama_index.core.schema import BaseNode, ObjectType, TextNode


class SafeSemanticSplitter(SemanticSplitterNodeParser):

    safety_chunker: SentenceSplitter = SentenceSplitter(
        chunk_size=DEFAULT_CHUNK_SIZE * 4, chunk_overlap=SENTENCE_CHUNK_OVERLAP
    )

    def _parse_nodes(
        self,
        nodes: Sequence[BaseNode],
        show_progress: bool = False,
        **kwargs: Any,
    ) -> List[BaseNode]:
        all_nodes: List[BaseNode] = super()._parse_nodes(
            nodes=nodes, show_progress=show_progress, **kwargs
        )
        all_good = True
        for node in all_nodes:
            if node.get_type() == ObjectType.TEXT:
                node: TextNode = node
                if self.safety_chunker._token_size(node.text) > self.safety_chunker.chunk_size:
                    logging.info(
                        "Chunk size too big after semantic chunking: switching to static chunking"
                    )
                    all_good = False
                    break
        if not all_good:
            all_nodes = self.safety_chunker._parse_nodes(
                nodes, show_progress=show_progress, **kwargs
            )
        return all_nodes


def clean_up_text(content: str) -> str:
    """
    Remove unwanted characters and patterns in text input.

    :param content: Text input.

    :return: Cleaned version of original text input.
    """

    # Fix hyphenated words broken by newline
    if isinstance(content, str) and content and content.strip():
        # Check if content is valid (e.g., not just whitespace)
        content = re.sub(r"(\w+)-\n(\w+)", r"\1\2", content)

        # Remove specific unwanted patterns and characters
        unwanted_patterns = [
            "\\n",
            "  —",
            "——————————",
            "—————————",
            "—————",
            r"```.+?```",
            r"\\u[\dA-Fa-f]{4}",
            r"\uf075",
            r"\uf0b7",
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            r"<code>.+?</code>",
            r"<style>.+?</style>",
            r"<[^>]+>",
            r"\{[^}]+\}",  # Remove CSS tags like { padding-bottom: 20px !important; }
            r"\[.+?\]",  # Remove markdown links like [text](url)
            r"~~/[^/]+/~~",
            r"@[^\s]+",  # Remove tailwind tags like @apply
            r'\s*style\s*=\s*"[^"]*"',
            r'\s*id\s*=\s*"[^"]*"',
            r"<!--[\s\S]*?-->",
            r"&amp;[^;\s]*;",
            r"(&\w+;|\\u[0-9a-fA-F]{4})",
            r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>",
        ]
        for pattern in unwanted_patterns:
            content = re.sub(pattern, "", content)

        # Fix improperly spaced hyphenated words and normalize whitespace
        content = re.sub(r"(\w)\s*-\s*(\w)", r"\1-\2", content)
        content = re.sub(r"\s+", " ", content)

        return content
    else:
        return ""
