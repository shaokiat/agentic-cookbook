from dataclasses import dataclass, field

from researcher.llm import Usage


@dataclass
class Report:
    query: str
    sub_queries: list[str]
    content: str
    usage: Usage
    timing: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        sub_query_list = "\n".join(f"- {q}" for q in self.sub_queries)
        return (
            f"# Research Report: {self.query}\n\n"
            f"**Sub-questions researched:**\n{sub_query_list}\n\n"
            f"---\n\n"
            f"{self.content}"
        )
