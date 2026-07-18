#!/usr/bin/env python3
"""mini-researcher: plan -> parallel search/scrape/compress -> synthesize."""

import argparse

from dotenv import load_dotenv

load_dotenv()

from researcher.config import Config
from researcher.pipeline import ResearchPipeline


def main():
    parser = argparse.ArgumentParser(description="mini-researcher: parallel web research -> report")
    parser.add_argument("query", help="Research question")
    parser.add_argument("--sub-queries", type=int, default=4, help="Max number of sub-questions to research")
    parser.add_argument("--top-k", type=int, default=5, help="Chunks kept per sub-query after compression")
    parser.add_argument("--model", default=None, help="Override DEFAULT_MODEL")
    args = parser.parse_args()

    config = Config()
    config.max_sub_queries = args.sub_queries
    config.top_k_chunks = args.top_k
    if args.model:
        config.model = args.model

    pipeline = ResearchPipeline(config)
    report = pipeline.run(args.query)

    print(report.to_markdown())
    print(f"\n---\ncost: ${report.usage.cost:.4f} | tokens: {report.usage.total_tokens} | research time: {report.timing['research_seconds']:.1f}s")


if __name__ == "__main__":
    main()
