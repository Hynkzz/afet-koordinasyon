"""ESC-50'den vurus olcumu icin gereken siniflari indirir (yaklasik 280 dosya, 120 MB).

ESC-50: K. J. Piczak, "ESC: Dataset for Environmental Sound Classification", ACM MM 2015.
Lisans CC BY-NC 3.0; dosyalar depoya konmaz, data/gercek/esc50/ git disinda.
"""
import csv
import io
import urllib.request

from server.main import KOK

KAYNAK = "https://raw.githubusercontent.com/karolpiczak/ESC-50/master"
POZITIF = "door_wood_knock"
# Vurusla en kolay karisabilecek kisa, darbeli sesler.
NEGATIF = ["clapping", "footsteps", "mouse_click", "keyboard_typing", "clock_tick", "can_opening"]


def main():
    hedef = KOK / "data" / "gercek" / "esc50"
    hedef.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{KAYNAK}/meta/esc50.csv", timeout=60) as cevap:
        meta = cevap.read().decode()
    (hedef / "esc50.csv").write_text(meta)
    satirlar = [r for r in csv.DictReader(io.StringIO(meta)) if r["category"] in [POZITIF, *NEGATIF]]
    for no, r in enumerate(satirlar, 1):
        dosya = hedef / r["filename"]
        if not dosya.exists():
            with urllib.request.urlopen(f"{KAYNAK}/audio/{r['filename']}", timeout=60) as cevap:
                dosya.write_bytes(cevap.read())
        if no % 40 == 0:
            print(f"{no}/{len(satirlar)}")
    print(f"{len(satirlar)} dosya: {hedef}")


if __name__ == "__main__":
    main()
