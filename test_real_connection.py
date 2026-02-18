import os
import sys
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# 1. Load Environment Variables (.env)
load_dotenv()

def test_connection():
    print("="*50)
    print("  MEMULAI TES KONEKSI REAL KE OPENROUTER...")
    print("="*50)

    # Cek apakah API Key terbaca
    api_key = os.getenv("OPENROUTER_API_KEY")
    model_name = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")
    
    if not api_key:
        print(" ERROR: API Key tidak ditemukan di file .env!")
        return

    print(f" API Key terdeteksi: {api_key[:5]}...{api_key[-4:]}")
    print(f" Model Target: {model_name}")
    print("-" * 50)
    print(" Sedang menghubungi server Gemini... (Mohon tunggu)")

    try:
        # 2. Setup LLM (Konfigurasi SAMA PERSIS dengan retrieval.py)
        llm = ChatOpenAI(
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            model_name=model_name,
            temperature=0.7,
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "TestScriptConnection",
            }
        )

        # 3. Kirim Pesan Sederhana
        pesan = [HumanMessage(content="Halo AI, perkenalkan dirimu dalam satu kalimat singkat saja.")]
        
        response = llm.invoke(pesan)

        # 4. Tampilkan Hasil
        print("\n KONEKSI SUKSES!")
        print(" Jawaban AI:")
        print(f"> {response.content}")
        print("="*50)

    except Exception as e:
        print("\n KONEKSI GAGAL!")
        print(f"Error Detail: {str(e)}")
        print("="*50)
        print("TIPS TROUBLESHOOTING:")
        print("1. Pastikan internet lancar.")
        print("2. Cek saldo/kredit di OpenRouter (meski free model, akun harus valid).")
        print("3. Pastikan API Key di .env sudah yang terbaru.")

if __name__ == "__main__":
    test_connection()
