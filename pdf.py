import os
import camelot
import pandas as pd

PDF_PATH = "Jadwal Mata Kuliah Semester GANJIL TA.2024-2025.pdf"
OUT_DIR = "out_csv"
os.makedirs(OUT_DIR, exist_ok=True)

def pdf_to_csv_camelot(pdf_path: str, pages: str = "all") -> None:
    """
    Extract tables from PDF using Camelot and save as:
    1) per-table CSV
    2) one combined CSV
    """
    # Coba lattice dulu (untuk tabel dengan garis)
    tables = camelot.read_pdf(pdf_path, pages=pages, flavor="lattice")

    # Kalau lattice gagal/hasilnya minim, fallback ke stream (tabel tanpa garis tegas)
    if tables.n == 0:
        tables = camelot.read_pdf(pdf_path, pages=pages, flavor="stream")

    all_frames = []
    for i, t in enumerate(tables):
        df = t.df.copy()

        # Buang baris kosong penuh
        df = df.dropna(how="all")

        # Simpan per tabel
        out_path = os.path.join(OUT_DIR, f"table_{i+1}.csv")
        df.to_csv(out_path, index=False, header=False)

        # Tambahkan kolom metadata biar gampang tracking asalnya
        df2 = df.copy()
        df2.insert(0, "table_index", i + 1)
        all_frames.append(df2)

    # Gabungkan semua tabel
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        combined.to_csv(os.path.join(OUT_DIR, "combined_tables.csv"), index=False)

    print(f"Done. Extracted {tables.n} tables into '{OUT_DIR}/'.")

if __name__ == "__main__":
    pdf_to_csv_camelot(PDF_PATH, pages="all")
