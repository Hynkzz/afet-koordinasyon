import json
import sqlite3
from datetime import datetime
from pathlib import Path

DURUMLAR = ["yeni", "ekip_yonlendirildi", "kurtarildi"]

SEMA = """
CREATE TABLE IF NOT EXISTS vakalar (
    id TEXT PRIMARY KEY,
    kaynak TEXT NOT NULL,          -- olay | mesaj | portal
    oncelik INTEGER NOT NULL,      -- 1 en acil
    durum TEXT NOT NULL DEFAULT 'yeni',
    zaman TEXT NOT NULL,
    guncellendi TEXT,
    veri TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gecmis (
    no INTEGER PRIMARY KEY AUTOINCREMENT,
    vaka_id TEXT NOT NULL,
    olay TEXT NOT NULL,
    zaman TEXT NOT NULL
);
"""


def simdi() -> str:
    return datetime.now().astimezone().isoformat()


class Vakalar:
    """Olay, SOS ve portal kayitlarinin durumu; sunucu yeniden acilinca kaybolmasin diye SQLite'ta."""

    def __init__(self, yol: Path | str):
        # Sorgular milisaniye surer; ayri is parcacigina tasimaya deger degil.
        self.baglanti = sqlite3.connect(yol, check_same_thread=False)
        self.baglanti.row_factory = sqlite3.Row
        self.baglanti.executescript(SEMA)

    def kapat(self):
        self.baglanti.close()

    @staticmethod
    def _sozluk(satir: sqlite3.Row) -> dict:
        vaka = dict(satir)
        vaka["veri"] = json.loads(vaka["veri"])
        return vaka

    def kaydet(self, id: str, kaynak: str, oncelik: int, veri: dict) -> dict:
        """Yeni vaka acar ya da var olanin verisini ve onceligini gunceller; durumu korur."""
        with self.baglanti:
            self.baglanti.execute(
                """INSERT INTO vakalar (id, kaynak, oncelik, zaman, veri) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET oncelik = excluded.oncelik, veri = excluded.veri,
                   guncellendi = ?""",
                (id, kaynak, oncelik, simdi(), json.dumps(veri, ensure_ascii=False), simdi()),
            )
        return self.getir(id)

    def acik_olay_vakasi(self, anahtar: str) -> dict | None:
        satir = self.baglanti.execute(
            "SELECT * FROM vakalar WHERE kaynak = 'olay' AND durum != 'kurtarildi' "
            "AND json_extract(veri, '$.anahtar') = ? ORDER BY zaman DESC LIMIT 1", (anahtar,)
        ).fetchone()
        return self._sozluk(satir) if satir else None

    def getir(self, id: str) -> dict | None:
        satir = self.baglanti.execute("SELECT * FROM vakalar WHERE id = ?", (id,)).fetchone()
        return self._sozluk(satir) if satir else None

    def durum_degistir(self, id: str, durum: str) -> dict:
        if durum not in DURUMLAR:
            raise ValueError(f"gecersiz durum: {durum}")
        with self.baglanti:
            degisen = self.baglanti.execute(
                "UPDATE vakalar SET durum = ?, guncellendi = ? WHERE id = ?", (durum, simdi(), id)
            ).rowcount
            if not degisen:
                raise KeyError(id)
            self.gecmise_yaz(id, durum)
        return self.getir(id)

    def gecmise_yaz(self, id: str, olay: str):
        with self.baglanti:
            self.baglanti.execute("INSERT INTO gecmis (vaka_id, olay, zaman) VALUES (?, ?, ?)", (id, olay, simdi()))

    def gecmis(self, id: str) -> list[dict]:
        return [dict(s) for s in self.baglanti.execute(
            "SELECT olay, zaman FROM gecmis WHERE vaka_id = ? ORDER BY no", (id,))]

    def kuyruk(self) -> list[dict]:
        # Once en acil, esit oncelikte en uzun bekleyen.
        return [self._sozluk(s) for s in self.baglanti.execute(
            "SELECT * FROM vakalar WHERE durum != 'kurtarildi' ORDER BY oncelik, zaman")]

    def hepsi(self, kaynak: str | None = None) -> list[dict]:
        if kaynak:
            sorgu = self.baglanti.execute("SELECT * FROM vakalar WHERE kaynak = ? ORDER BY zaman", (kaynak,))
        else:
            sorgu = self.baglanti.execute("SELECT * FROM vakalar ORDER BY zaman")
        return [self._sozluk(s) for s in sorgu]

    def sayilar(self) -> dict[str, int]:
        return {d: n for d, n in self.baglanti.execute("SELECT durum, COUNT(*) FROM vakalar GROUP BY durum")}
