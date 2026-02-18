import os
from django.conf import settings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

CHROMA_PERSIST_DIR = os.path.join(settings.BASE_DIR, "chroma_db")

# Inisialisasi Model
embedding_function = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def get_vectorstore():
    return Chroma(
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=embedding_function,
        collection_name="academic_rag"
    )
