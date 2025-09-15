import chromadb
from sentence_transformers import SentenceTransformer
from rich.console import Console

console = Console()
TXT_SOURCE_FILE = '2kezen-qmdb_output.txt'
DB_PATH = "./db_text"  # Жаңа база үшін жаңа папка
COLLECTION_NAME = "halal_data_from_text"

# Embedding моделін жүктеу
model = SentenceTransformer('all-MiniLM-L6-v2')

# Векторлық базаны құру
client_chroma = chromadb.PersistentClient(path=DB_PATH)
collection = client_chroma.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)

def main():
    try:
        with open(TXT_SOURCE_FILE, 'r', encoding='utf-8') as f:
            full_text = f.read()
        console.print(f"✅ '{TXT_SOURCE_FILE}' файлы сәтті оқылды.", style="green")
    except Exception as e:
        console.print(f"❌ Файлды оқу кезінде қате: {e}", style="bold red")
        return
    
    # Файлды "------------------------------" белгісі арқылы жеке жазбаларға бөлу
    records = full_text.split('------------------------------')
    
    # Бос жазбаларды алып тастау
    documents = [rec.strip() for rec in records if rec.strip() and len(rec.strip()) > 50]
    
    console.print(f"Барлығы {len(documents)} құжат дайындалды. Векторға айналдыру басталды...", style="cyan")

    # Векторларды жасау
    embeddings = model.encode(documents, show_progress_bar=True)
    
    # ID-ларды генерациялау
    ids = [f"doc_{i}" for i in range(len(documents))]

    # Деректерді базаға қосу
    collection.add(
        embeddings=embeddings.tolist(),
        documents=documents,
        ids=ids
    )

    console.print(f"✅ Векторлық база '{DB_PATH}' папкасында сәтті жасалды!", style="bold green")

if __name__ == "__main__":
    main()