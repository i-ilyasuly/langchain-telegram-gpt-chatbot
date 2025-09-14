import pandas as pd
import chromadb
from sentence_transformers import SentenceTransformer
from rich.console import Console
from rich.progress import track

console = Console()

# Жергілікті жерде жұмыс істейтін embedding моделін жүктеу
# Бірінші рет іске қосқанда модель интернеттен жүктеледі (шамамен 500 МБ)
model = SentenceTransformer('all-MiniLM-L6-v2')

client_chroma = chromadb.PersistentClient(path="./db")
collection = client_chroma.get_or_create_collection(
    name="halal_data",
    metadata={"hnsw:space": "cosine"}
)

def main():
    try:
        df_est = pd.read_csv('establishments.csv', dtype=str).fillna('')
        df_add = pd.read_csv('additives.csv', dtype=str).fillna('')
        console.print("✅ CSV файлдар сәтті оқылды.", style="green")
    except FileNotFoundError:
        console.print("❌ CSV файлдар табылмады. Алдымен 'converter.py' іске қосыңыз.", style="bold red")
        return

    documents = []
    metadatas = []
    ids = []

    for index, row in df_est.iterrows():
        doc_text = f"Мекеме аты: {row['name']}. Санаты: {row['category']}. Қаласы: {row['city']}. Мекенжайы: {row['address']}. Кілт сөздер: {row['keywords']}"
        documents.append(doc_text)
        metadatas.append({'source': 'establishments', 'original_text': doc_text})
        ids.append(f"est_{row['id']}")

    for index, row in df_add.iterrows():
        doc_text = f"E-қоспа: {row['ecode']}. Атауы: {row['name']}. Статусы: {row['halal_status_name']}. Сипаттамасы: {row['description']}"
        documents.append(doc_text)
        metadatas.append({'source': 'additives', 'original_text': doc_text})
        ids.append(f"add_{row['id']}")

    console.print(f"Барлығы {len(documents)} құжат дайындалды. Векторлық түрге айналдыру басталды...", style="cyan")
    
    # Модель арқылы векторларды жасау
    embeddings = model.encode(documents, show_progress_bar=True)
    
    # Деректерді базаға қосу
    collection.add(
        embeddings=embeddings.tolist(),
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    console.print("✅ Векторлық деректер қоры сәтті жасалды! Енді 'main.py' файлын іске қосуға болады.", style="bold green")

if __name__ == "__main__":
    main()