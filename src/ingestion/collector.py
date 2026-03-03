"""
多源信息采集器 — 从搜索引擎、arXiv、RSS、网页等来源收集素材。
采集结果存入向量数据库供后续 RAG 检索使用。
"""

import logging
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CollectedDoc:
    title: str
    content: str
    source: str
    url: str = ""
    doc_type: str = "web"  # web | arxiv | blog | doc | manual
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.md5(self.content.encode()).hexdigest()


class InfoCollector:
    """多源信息采集，统一输出 CollectedDoc 列表。"""

    def __init__(self, config: dict):
        self.config = config
        self.max_search = config.get("max_search_results", 10)
        self.arxiv_max = config.get("arxiv_max_results", 20)
        self._seen_hashes: set[str] = set()

    def collect(self, topic: str, extra_urls: list[str] = None, local_docs: list[str] = None) -> list[CollectedDoc]:
        docs = []
        docs.extend(self._search_web(topic))
        docs.extend(self._search_arxiv(topic))
        if extra_urls:
            docs.extend(self._scrape_urls(extra_urls))
        if local_docs:
            docs.extend(self._load_local_docs(local_docs))
        docs = self._dedup(docs)
        logger.info(f"采集完成: {len(docs)} 篇去重后文档")
        return docs

    def _search_web(self, topic: str) -> list[CollectedDoc]:
        docs = []
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(topic, max_results=self.max_search))
                for r in results:
                    docs.append(CollectedDoc(
                        title=r.get("title", ""),
                        content=r.get("body", ""),
                        source="duckduckgo",
                        url=r.get("href", ""),
                        doc_type="web",
                    ))
        except ImportError:
            logger.warning("duckduckgo_search 未安装，跳过网页搜索")
        except Exception as e:
            logger.error(f"网页搜索失败: {e}")
        return docs

    def _search_arxiv(self, topic: str) -> list[CollectedDoc]:
        docs = []
        try:
            import arxiv
            search = arxiv.Search(
                query=topic,
                max_results=self.arxiv_max,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            client = arxiv.Client()
            for paper in client.results(search):
                docs.append(CollectedDoc(
                    title=paper.title,
                    content=f"{paper.title}\n\n{paper.summary}",
                    source="arxiv",
                    url=paper.entry_id,
                    doc_type="arxiv",
                ))
        except ImportError:
            logger.warning("arxiv 未安装，跳过论文搜索")
        except Exception as e:
            logger.error(f"arXiv 搜索失败: {e}")
        return docs

    def _scrape_urls(self, urls: list[str]) -> list[CollectedDoc]:
        docs = []
        for url in urls:
            try:
                doc = self._scrape_single(url)
                if doc:
                    docs.append(doc)
            except Exception as e:
                logger.error(f"抓取失败 {url}: {e}")
        return docs

    def _scrape_single(self, url: str) -> CollectedDoc | None:
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None
            text = trafilatura.extract(downloaded)
            if not text:
                return None
            return CollectedDoc(
                title=url.split("/")[-1],
                content=text,
                source="scrape",
                url=url,
                doc_type="web",
            )
        except ImportError:
            import httpx
            resp = httpx.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return CollectedDoc(
                title=soup.title.string if soup.title else url,
                content=text[:20000],
                source="scrape",
                url=url,
                doc_type="web",
            )

    def _load_local_docs(self, paths: list[str]) -> list[CollectedDoc]:
        docs = []
        for raw in paths:
            p = Path(raw)
            if not p.exists():
                logger.warning(f"本地文档路径不存在，已跳过: {raw}")
                continue

            if p.is_file():
                doc = self._load_local_file(p)
                if doc:
                    docs.append(doc)
                continue

            for fp in p.rglob("*"):
                if not fp.is_file():
                    continue
                doc = self._load_local_file(fp)
                if doc:
                    docs.append(doc)
        return docs

    def _load_local_file(self, file_path: Path) -> CollectedDoc | None:
        allowed = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".htm", ".py", ".js", ".ts", ".tsx"}
        suffix = file_path.suffix.lower()
        if suffix not in allowed:
            return None

        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"读取本地文档失败 {file_path}: {e}")
            return None

        text = text.strip()
        if len(text) < 100:
            return None

        max_chars = int(self.config.get("local_doc_max_chars", 30000))
        text = text[:max_chars]

        return CollectedDoc(
            title=file_path.name,
            content=text,
            source="local",
            url=str(file_path),
            doc_type="doc",
        )

    def _dedup(self, docs: list[CollectedDoc]) -> list[CollectedDoc]:
        unique = []
        for doc in docs:
            if doc.content_hash not in self._seen_hashes:
                self._seen_hashes.add(doc.content_hash)
                unique.append(doc)
        return unique


class VectorStore:
    """ChromaDB 向量知识库封装。"""

    def __init__(self, persist_dir: str, embedding_model: str = "all-MiniLM-L6-v2"):
        self.persist_dir = persist_dir
        self.embedding_model = embedding_model
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            try:
                import chromadb
            except ImportError:
                logger.warning("chromadb 未安装，跳过向量索引与检索")
                return None
            client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = client.get_or_create_collection(
                name="doc_chunks",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_docs(self, docs: list[CollectedDoc], chunk_size: int = 500, overlap: int = 50):
        collection = self._get_collection()
        if collection is None:
            return
        for doc in docs:
            chunks = self._chunk_text(doc.content, chunk_size, overlap)
            ids = [f"{doc.content_hash}_{i}" for i in range(len(chunks))]
            metadatas = [{"source": doc.source, "url": doc.url, "title": doc.title}] * len(chunks)
            if chunks:
                collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        logger.info(f"已索引 {len(docs)} 篇文档")

    def query(self, text: str, top_k: int = 5) -> list[dict]:
        collection = self._get_collection()
        if collection is None:
            return []
        results = collection.query(query_texts=[text], n_results=top_k)
        out = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            out.append({"content": doc, **meta})
        return out

    @staticmethod
    def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + size
            chunks.append(text[start:end])
            start = end - overlap
        return [c for c in chunks if len(c.strip()) > 50]
