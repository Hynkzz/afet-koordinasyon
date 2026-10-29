# Paket boyutu ve kanal sığması — 29.10.2026

Betik: `python -m scripts.boyut_olc` (önce `python -m scripts.gercek_veri_indir`).

6 Şubat 2023 depremlerinden 2.028 gerçek yardım mesajının ilk 200 karakteri yük
yapıldı, GPS eklendi, ChaCha20-Poly1305 ile şifrelendi; paket boyutu msgpack ve
JSON için ayrı hesaplandı. Kanal sınırları: BLE 380, LoRa 200, uydu 340 bayt
(simülasyon değerleri, `server/kanal.py`).

| | Ortalama | Medyan | p95 | En yüksek |
|---|---|---|---|---|
| Yük (UTF-8) | 191 | 209 | 225 | 271 bayt |
| Paket, msgpack | 329 | 347 | 364 | 416 bayt |
| Paket, JSON | 446 | 471 | 491 | 561 bayt |

| Kanal | msgpack ile sığan | JSON ile sığan |
|---|---|---|
| BLE (380 B) | %99 | %13 |
| LoRa (200 B) | %0 | %0 |
| Uydu (340 B) | %39 | %6 |

Ölçüm iki şey gösterdi:

1. **Düzeltilen hata:** Şifrelenen iç JSON önce Türkçe harfleri kaçış dizisiyle
   yazıyordu (`ı` → `ı`, 2 yerine 6 bayt). Düzeltmeden önce msgpack paket
   ortalaması 379 bayt, BLE'ye sığan oran %43 idi; düzeltmeden sonra 329 bayt
   ve %99.
2. **LoRa'ya uzun metin sığmıyor:** Başlık, alan adları, GPS ve şifreleme
   etiketi yaklaşık 138 bayt tutuyor; LoRa'nın 200 baytına yalnızca ~60 baytlık
   yük kalıyor. Uzun mesajlar LoRa'dan değil BLE ya da uydudan gidebiliyor;
   ikisi de kapalıysa portal mesajı en geniş açık kanala sığacak kadar kırpılıyor.
