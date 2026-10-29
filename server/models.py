from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

# shared/*.schema.json ile birebir; biri degisirse digeri de degismeli.

Kimlik = Annotated[str, Field(min_length=1, max_length=32)]
MesajId = Annotated[str, Field(min_length=1, max_length=64)]
Oran = Annotated[float, Field(ge=0, le=1)]
Imza = Annotated[str, Field(pattern=r"^[A-Za-z0-9+/]{22}==$")]
Tur = Literal["SOS", "hazir_mesaj", "ack"]
Ttl = Annotated[int, Field(ge=0, le=16)]
Yuk = Annotated[str, Field(max_length=200)]


class Sema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Kutu(Sema):
    x: Oran
    y: Oran
    w: Annotated[float, Field(gt=0, le=1)]
    h: Annotated[float, Field(gt=0, le=1)]


class Olay(Sema):
    olay_id: MesajId
    kaynak: Literal["kamera", "mikrofon"]
    etiket: Literal["insan", "vurus"]
    guven: Oran
    zaman: AwareDatetime
    kutu: Kutu | None = None

    @model_validator(mode="after")
    def vurusta_kutu_olmaz(self):
        if self.etiket == "vurus" and self.kutu is not None:
            raise ValueError("vurus olayinda kutu olmaz")
        return self


class Gps(Sema):
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class Taslak(Sema):
    """Sifrelenmeden onceki mesaj; imzayi sifreleme uretir."""

    id: MesajId
    tur: Tur
    kaynak: Kimlik
    hedef: Kimlik
    ttl: Ttl
    yuk: Yuk
    gps: Gps | None = None
    sayac: Annotated[int, Field(ge=0)]


class Mesaj(Taslak):
    imza: Imza


class Paket(Sema):
    id: MesajId
    tur: Tur
    kaynak: Kimlik
    hedef: Kimlik
    ttl: Ttl
    sayac: Annotated[int, Field(ge=0)]
    sifreli: Annotated[str, Field(min_length=1)]
    imza: Imza


class Sinyal(Sema):
    dugum_id: Kimlik
    rssi: Annotated[float, Field(ge=-120, le=0)]
    paket_alim_orani: Oran
    zaman: AwareDatetime
    pil: Annotated[float, Field(ge=0, le=100)] | None = None
    mod: Literal["dusuk_guc", "acil"] | None = None


class SiginakOzellik(BaseModel):
    ad: Annotated[str, Field(min_length=1)]
    kapasite: Annotated[int, Field(ge=0)]
    kaynak: Literal["AFAD", "OSM", "tahmin"]


class Nokta(BaseModel):
    type: Literal["Point"]
    coordinates: tuple[Annotated[float, Field(ge=-180, le=180)], Annotated[float, Field(ge=-90, le=90)]]


class Siginak(BaseModel):
    type: Literal["Feature"]
    geometry: Nokta
    properties: SiginakOzellik


class Siginaklar(BaseModel):
    type: Literal["FeatureCollection"]
    features: list[Siginak]


class MesajIstek(Sema):
    tur: Literal["SOS", "hazir_mesaj"]
    yuk: Yuk
    gps: Gps | None = None


class DurumIstek(Sema):
    durum: Literal["yeni", "ekip_yonlendirildi", "kurtarildi"]


class KanalIstek(Sema):
    acik: bool


class DugumOzellik(BaseModel):
    id: Kimlik
    tur: Literal["dugum", "kamera", "mikrofon"]
    menzil_m: Annotated[float, Field(gt=0)] | None = None
    kaynak: Literal["olcum", "hesap", "tahmin"]


class Dugum(BaseModel):
    type: Literal["Feature"]
    geometry: Nokta
    properties: DugumOzellik


class Dugumler(BaseModel):
    type: Literal["FeatureCollection"]
    features: list[Dugum]


class SenaryoIstek(Sema):
    dosya: Annotated[str, Field(min_length=1, max_length=100)]
    temizle: bool = False


class KareKutusu(Kutu):
    guven: Oran


class KameraKaresi(Sema):
    # 640 piksel genislik, JPEG kalite 70: tipik kare 30-60 KB; sinir tasma ve kotu niyetli istek icin.
    jpeg: Annotated[str, Field(min_length=1, max_length=600_000)]
    kutular: Annotated[list[KareKutusu], Field(max_length=100)]
    kaynak: Annotated[str, Field(max_length=100)]
