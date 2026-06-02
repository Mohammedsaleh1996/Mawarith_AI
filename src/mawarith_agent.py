import os
from pathlib import Path
from typing import Dict, Any, Optional
from llama_cpp import Llama
from .rag_pipeline import MawarithRAG
from ..fiqh_engine.core_calculator import FaraidCalculator

class MawarithAgent:
    def __init__(self, model_path: str = None):
        # Load model path (Q8_0.gguf)
        if model_path is None:
            model_path = str(Path("models/local/Qwen2.5-3B-Mawarith-Q8_0.gguf"))
        
        self.llm = Llama(
            model_path=model_path,
            n_gpu_layers=28,          # مناسب لـ 4GB VRAM
            n_ctx=8192,
            n_batch=512,
            verbose=False,
        )
        
        self.rag = MawarithRAG()
        self.fiqh = FaraidCalculator()
        
        self.system_prompt = """
أنت Mawarith_AI، خبير فقهي متخصص في علم المواريث والفرائض.
- رد دايماً باللهجة اللي المستخدم بيتكلم بيها (مصري، خليجي، شامي...).
- كن ودود وطبيعي زي واحد بيشرح لصاحبه في القهوة.
- شرح كل حاجة بأمثلة بسيطة جداً.
- لو في حسابات فرضية استخدم Fiqh Engine واطبع النتيجة بشكل منظم.
- ما تسألش "قصدك إيه" إلا لو السؤال فعلاً غامض جداً.
- ابدأ الرد مباشرة بدون مقدمات روبوتية.
"""

    def chat(self, message: str, dialect: str = "مصري") -> str:
        # Retrieve from RAG
        rag_context = self.rag.retrieve(message, k=4)
        
        # If calculation needed, use Fiqh Engine
        if any(word in message.lower() for word in ["احسب", "تركة", "ميراث", "مناسخة", "عول", "رد"]):
            fiqh_result = self.fiqh.calculate_from_text(message)
            context = f"{rag_context}\n\nنتيجة الحساب من Fiqh Engine:\n{fiqh_result}"
        else:
            context = rag_context

        full_prompt = f"{self.system_prompt}\n\nالسياق من الكتب:\n{context}\n\nالسؤال: {message}\n\nالرد (باللهجة {dialect}):"

        response = self.llm(
            full_prompt,
            max_tokens=2048,
            temperature=0.7,
            stop=["</s>"],
        )

        return response['choices'][0]['text'].strip()

# For direct testing
if __name__ == "__main__":
    agent = MawarithAgent()
    while True:
        q = input("\nاسأل: ")
        if q.lower() in ["exit", "خروج"]:
            break
        print(agent.chat(q))