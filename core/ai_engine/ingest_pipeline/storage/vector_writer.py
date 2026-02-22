from typing import Any, Dict, List


def write_chunks(vectorstore: Any, chunks: List[str], metadatas: List[Dict[str, Any]]) -> None:
    vectorstore.add_texts(texts=chunks, metadatas=metadatas)

