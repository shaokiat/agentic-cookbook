import os


class Config:
    def __init__(self):
        self.model = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.search_provider = os.getenv("SEARCH_PROVIDER", "duckduckgo")
        self.max_sub_queries = 4
        self.results_per_query = 3
        self.chunk_size = 800
        self.chunk_overlap = 100
        self.top_k_chunks = 5
