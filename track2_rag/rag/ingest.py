import fitz  # PyMuPDF
import json
from pathlib import Path

def process_pdfs(raw_dir: str, output_file: str):
    chunks = []
    raw_path = Path(raw_dir)
    if not raw_path.exists():
        print(f"Directory {raw_dir} does not exist. Please create it and add PDFs.")
        return

    for pdf_path in raw_path.glob("*.pdf"):
        doc = fitz.open(pdf_path)
        doc_name = pdf_path.stem
        for page_num in range(len(doc)):
            text = doc[page_num].get_text()
            if not text.strip():
                continue
            chunk_id = f"{doc_name}-p{page_num + 1}"
            chunks.append({
                "chunk_id": chunk_id,
                "doc": doc_name,
                "page": page_num + 1,
                "text": text.strip()
            })
            
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"Processed {len(chunks)} chunks into {output_file}.")

if __name__ == "__main__":
    process_pdfs("track2_rag/corpus/raw", "track2_rag/corpus/chunks.json")