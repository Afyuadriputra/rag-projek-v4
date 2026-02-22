def extract_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as handle:
        return handle.read()

