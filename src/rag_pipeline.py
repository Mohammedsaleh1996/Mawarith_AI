import os
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MawarithRAG:
    def __init__(self):
        self.books_dir = Path("corpus/Books")
        self.db_path = Path("corpus/index/chroma_db")
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # نموذج embeddings خفيف ومناسب لجهازك (4GB VRAM)
        self.embedding_model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
        
        # إعداد ChromaDB
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(
            name="mawarith_books",
            metadata={"hnsw:space": "cosine"}
        )

    def load_all_books(self) -> List[Dict]:
        """تحميل كل الـ 19 مرحلة"""
        documents = []
        for file_path in self.books_dir.glob("*.txt"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                    if len(text) > 50:  # تجاهل الملفات الفارغة
                        documents.append({
                            "id": file_path.stem,
                            "text": text,
                            "metadata": {
                                "filename": file_path.name,
                                "stage": file_path.stem.split("_")[1] if "_" in file_path.stem else "unknown"
                            }
                        })
            except Exception as e:
                logger.error(f"خطأ في قراءة {file_path}: {e}")
        logger.info(f"تم تحميل {len(documents)} مرحلة من الـ 19 مرحلة")
        return documents

    def create_index(self):
        """إنشاء الـ Vector Database لأول مرة"""
        if self.collection.count() > 0:
            logger.info("الـ index موجود بالفعل")
            return

        documents = self.load_all_books()
        if not documents:
            logger.warning("لم يتم العثور على ملفات في corpus/Books")
            return

        texts = [doc["text"] for doc in documents]
        ids = [doc["id"] for doc in documents]
        metadatas = [doc["metadata"] for doc in documents]

        # تقسيم النصوص إلى chunks ذكية
        chunks = []
        chunk_ids = []
        chunk_metadatas = []
        
        for i, text in enumerate(texts):
            # تقسيم كل مرحلة إلى أجزاء (حوالي 800-1000 كلمة)
            words = text.split()
            for j in range(0, len(words), 400):
                chunk = " ".join(words[j:j+600])
                chunks.append(chunk)
                chunk_ids.append(f"{ids[i]}_chunk_{j}")
                chunk_metadatas.append(metadatas[i])

        # إنشاء الـ embeddings وإضافتها
        embeddings = self.embedding_model.encode(chunks, show_progress_bar=True)
        
        self.collection.add(
            embeddings=embeddings.tolist(),
            documents=chunks,
            ids=chunk_ids,
            metadatas=chunk_metadatas
        )
        logger.info(f"تم إنشاء الـ index بنجاح - {len(chunks)} chunk")

    def retrieve(self, query: str, k: int = 5) -> str:
        """استرجاع أفضل المعلومات من الـ 19 مرحلة"""
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )
        
        context = "\n\n".join([
            f"من مرحلة {meta.get('filename', 'غير معروف')}:\n{doc}"
            for doc, meta in zip(results["documents"][0], results["metadatas"][0])
        ])
        return context

    def as_retriever(self):
        """للاستخدام داخل الـ Agent"""
        return self.retrieve

# للاختبار
if __name__ == "__main__":
    rag = MawarithRAG()
    rag.create_index()
    print("تم إنشاء الـ RAG بنجاح")
    print(rag.retrieve("ما هو العول في علم المواريث؟"))