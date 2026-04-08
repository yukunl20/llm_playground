import re

def load_text_file(source: str | bytes, encoding: str = "utf-8") -> dict:
    """
    source: file path string OR raw bytes
    returns: {"text": str, "error": str | None}
    """

    try:
        if isinstance(source, bytes):
            text = source.decode(encoding, errors="replace")
        else:
            with open(source, "r", encoding=encoding, errors="replace") as f:
                text = f.read()
        
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return {"text": text.strip(), "error": None}
    
    except Exception as e:
        return {"text": "", "error": str(e)}

if __name__ == "__main__":
    path = "10-K/AMAT/0000006951-21-000043/full-submission.txt"
    result = load_text_file(source=path)
    text = result['text']
    print(text[0:1000])
