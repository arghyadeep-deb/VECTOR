"""
Module: core/training/openmythos/data_prep.py
Data preparation for fine-tuning.
"""

import sys

__all__ = [
    "DataPreparator",
    "main",
]

from pathlib import Path

from core.config import CONFIG
from loguru import logger
import httpx
import asyncio
import json
import re
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.scraper.engines.static import aensure_public_url


class DataPreparator:
    """Data preparation utilities for model fine-tuning."""

    def __init__(self):
        self.github_token = CONFIG["api_keys"].get("github_token", "")
        self.output_dir = CONFIG.get("openmythos", {}).get("data_dir", "./data/training")
        self._client = httpx.AsyncClient(timeout=60.0)
        logger.info("[OpenMythos] Data preparator initialized")

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def scrape_github_repos(
        self,
        org: str,
        repo_pattern: str = "*",
        max_repos: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch code from GitHub repositories matching a pattern.

        Args:
            org: GitHub organization or username
            repo_pattern: Repository name pattern (supports * wildcard)
            max_repos: Maximum number of repositories to fetch

        Returns:
            List of repository data with code contents
        """
        if not self.github_token:
            logger.warning("[OpenMythos] GitHub token not configured, using limited access")

        headers = {"Authorization": f"token {self.github_token}"} if self.github_token else {}

        search_url = f"https://api.github.com/search/repositories"
        params = {"q": f"org:{org} {repo_pattern}", "per_page": max_repos, "sort": "updated"}

        try:
            response = await self._client.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            repos = data.get("items", [])
            logger.info(f"[OpenMythos] Found {len(repos)} repositories for org: {org}")
        except Exception as e:
            logger.error(f"[OpenMythos] GitHub search failed: {e}")
            return []

        results = []
        for repo in repos[:max_repos]:
            repo_name = repo.get("name", "")
            repo_data = {
                "name": repo_name,
                "full_name": repo.get("full_name"),
                "description": repo.get("description", ""),
                "language": repo.get("language", ""),
                "stars": repo.get("stargazers_count", 0),
                "code": [],
            }

            contents_url = f"https://api.github.com/repos/{org}/{repo_name}/contents"
            try:
                contents_response = await self._client.get(contents_url, headers=headers)
                contents = contents_response.json()

                for item in contents[:20]:
                    if item.get("type") == "file" and item.get("name", "").endswith((".py", ".js", ".ts", ".go", ".rs")):
                        file_response = await self._client.get(item["url"], headers=headers)
                        file_data = file_response.json()
                        content = file_data.get("content", "")
                        if content:
                            import base64
                            decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
                            repo_data["code"].append({
                                "path": item["path"],
                                "content": decoded[:5000],
                                "language": item["name"].split(".")[-1],
                            })
            except Exception as e:
                logger.warning(f"[OpenMythos] Failed to fetch contents for {repo_name}: {e}")

            results.append(repo_data)
            logger.info(f"[OpenMythos] Fetched {len(repo_data['code'])} files from {repo_name}")

        return results

    def clean_text(self, text: str) -> str:
        """
        Normalize and clean text data for training.

        Args:
            text: Raw text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        text = re.sub(r'\r\n', '\n', text)

        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)

        text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        text = re.sub(r'<\s*!--[\s\S]*?--\s*>', '', text)
        text = re.sub(r'<[^>]+>', '', text)

        text = re.sub(r'\{[^{}]+\}', '', text)

        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)

        text = text.strip()

        return text

    async def create_qa_pairs(
        self,
        knowledge_base: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """
        Generate Q&A training pairs from knowledge base documents.

        Args:
            knowledge_base: List of documents with 'content' and optional 'title'

        Returns:
            List of Q&A pairs in format {'instruction': ..., 'input': ..., 'output': ...}
        """
        qa_pairs = []

        for doc in knowledge_base:
            content = doc.get("content", "")
            title = doc.get("title", "Document")

            if not content:
                continue

            cleaned = self.clean_text(content)
            if len(cleaned) < 50:
                continue

            sentences = re.split(r'(?<=[.!?])\s+', cleaned)
            for i in range(len(sentences) - 1):
                if len(sentences[i]) > 20 and len(sentences[i + 1]) > 20:
                    qa_pairs.append({
                        "instruction": f"Summarize the following:",
                        "input": sentences[i][:200],
                        "output": sentences[i + 1][:200],
                    })

            paragraphs = [p for p in cleaned.split("\n\n") if len(p) > 50 and len(p) < 500]
            for para in paragraphs[:3]:
                qa_pairs.append({
                    "instruction": f"Based on {title}, answer:",
                    "input": f"What is the key point in: {para[:150]}",
                    "output": para[:200],
                })

            if len(qa_pairs) >= 100:
                break

        logger.info(f"[OpenMythos] Generated {len(qa_pairs)} Q&A pairs")
        return qa_pairs[:500]

    def build_instruction_dataset(
        self,
        raw_dir: str,
        output_dir: str,
    ) -> str:
        """
        Build an instruction-tuning dataset from raw data.

        Args:
            raw_dir: Directory containing raw data files
            output_dir: Output directory for the prepared dataset

        Returns:
            Path to the output dataset
        """
        raw_path = Path(raw_dir)
        if not raw_path.exists():
            logger.error(f"[OpenMythos] Raw data directory not found: {raw_dir}")
            return ""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        output_file = output_path / "instruction_dataset.jsonl"

        all_examples = []

        for file_path in raw_path.rglob("*"):
            if file_path.is_file():
                try:
                    if file_path.suffix == ".json":
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                for item in data:
                                    processed = self._process_example(item)
                                    if processed:
                                        all_examples.append(processed)
                            elif isinstance(data, dict):
                                processed = self._process_example(data)
                                if processed:
                                    all_examples.append(processed)
                    elif file_path.suffix in [".txt", ".md"]:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            cleaned = self.clean_text(content)
                            chunks = self._chunk_text(cleaned, chunk_size=500)
                            for chunk in chunks:
                                all_examples.append({
                                    "instruction": "Complete or continue:",
                                    "input": chunk[:200],
                                    "output": chunk[200:400] if len(chunk) > 200 else "",
                                })
                except Exception as e:
                    logger.warning(f"[OpenMythos] Failed to process {file_path}: {e}")

        with open(output_file, "w", encoding="utf-8") as f:
            for example in all_examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")

        logger.info(f"[OpenMythos] Dataset built with {len(all_examples)} examples at {output_file}")
        return str(output_file)

    def _process_example(self, item: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Process a single example into instruction format."""
        if "instruction" in item and "output" in item:
            return {
                "instruction": item["instruction"],
                "input": item.get("input", ""),
                "output": item["output"],
            }
        elif "prompt" in item and "completion" in item:
            return {
                "instruction": item["prompt"],
                "input": "",
                "output": item["completion"],
            }
        elif "question" in item and "answer" in item:
            return {
                "instruction": item["question"],
                "input": "",
                "output": item["answer"],
            }
        return None

    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """Split text into chunks of specified size."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk:
                chunks.append(chunk)
        return chunks

    async def download_dataset(self, url: str, output_path: str) -> str:
        """
        Download a dataset from URL.

        Args:
            url: URL to download from
            output_path: Local path to save

        Returns:
            Path to the downloaded file
        """
        try:
            await aensure_public_url(url)
            response = await self._client.get(url)
            response.raise_for_status()

            output_root = Path(self.output_dir).resolve()
            requested = Path(output_path)
            target = requested.resolve() if requested.is_absolute() else (output_root / requested).resolve()
            if not target.is_relative_to(output_root):
                raise ValueError("Output path must stay within the configured training data directory")

            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as f:
                f.write(response.content)

            logger.info(f"[OpenMythos] Dataset downloaded to {target}")
            return str(target)
        except Exception as e:
            logger.error(f"[OpenMythos] Download failed: {e}")
            return ""


async def main():
    """Test the data preparator."""
    preparator = DataPreparator()
    try:
        test_text = "This is a test `code` with [links](url) and {some} tags."
        cleaned = preparator.clean_text(test_text)
        logger.info(f"Cleaned: {cleaned}")


        qa_pairs = await preparator.create_qa_pairs([
            {"content": "V.E.C.T.O.R is a cognitive assistant. It helps with tasks.", "title": "About"}
        ])
        logger.info(f"QA pairs: {len(qa_pairs)}")

    finally:
        await preparator.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
    print("✅ data_prep.py OK")
