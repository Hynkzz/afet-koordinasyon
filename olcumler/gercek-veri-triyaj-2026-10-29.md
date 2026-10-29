# Gerçek deprem mesajlarıyla triyaj ölçümü — 29.10.2026

Betikler: `python -m scripts.gercek_veri_indir`, sonra `python -m scripts.gercek_olc`.

Veri: Hugging Face `deprem-private/intent_test_v13_anonymized` — 6 Şubat 2023
depremlerinde Açık Kaynak Deprem Yardım projesinin topladığı ve etiketlediği
2.028 Türkçe yardım mesajı (çoğu tweet). İsimler `[MASK]` ile gizlenmiş,
adresler duruyor; lisans belirtilmemiş. Bu yüzden veri depoya konmadı
(`data/gercek/` git dışında), yalnızca indirme betiği var.

Veri setinin etiketleri bizimkinden farklı; eşleştirme:

| Bizim alan | Veri setindeki karşılığı |
|---|---|
| sıkışma | "Enkaz Kaldirma" etiketi (919 mesaj) |
| yardım çağrısı (öncelik 1–2) | yalnızca "Alakasiz" olmayan mesaj (377 mesaj alakasız) |
| öncelik | enkaz → 1, diğer ihtiyaçlar (barınma, yemek, ısınma…) → 2, alakasız → 3 |

LLM için 300 mesajlık rastgele örneklem (tohum 42). Her iki yöntem de mesajı
"SOS düğmesinden gelmemiş" sayarak sınıflandırdı.

Donanım: RTX 3050 Laptop 4 GB (Vulkan), llama.cpp b11982, Qwen3-4B-Instruct-2507 Q4_K_M.

| Yöntem | n | Sıkışma doğruluk / kesinlik / duyarlılık | Yardım çağrısı doğruluk / kesinlik / duyarlılık | Öncelik doğruluk |
|---|---|---|---|---|
| Kural, tüm veri | 2.028 | %76 / %89 / %54 | %45 / %94 / %35 | %43 |
| Kural, örneklem | 300 | %77 / %87 / %56 | %46 / %94 / %36 | %43 |
| LLM, örneklem | 300 | %78 / %75 / %74 | %85 / %92 / %90 | %71 |

LLM süresi (300 mesaj): ortalama 1,10 sn, medyan 1,08 sn, p95 1,25 sn, en yüksek
2,19 sn. 1 mesajda LLM iki denemede de geçersiz kişi sayısı verdi (>1000),
kural tabanlı yedeğe düştü.

Gözlemler:

- Kural tabanlı yedek az şey yakalıyor ama yakaladığında genelde doğru
  (yüksek kesinlik, düşük duyarlılık): gerçek mesajların çoğu anahtar
  kelimelerimizi içermiyor.
- LLM enkaz mesajlarının %74'ünü yakalıyor; kuralın %56'sından iyi, ama
  yanlış alarm biraz daha fazla (kesinlik %75).
- Ölçüm sırasında kural tabanlı triyajda bir hata bulundu: telefon numarasının
  arkasındaki "kişi" kelimesi numarayı kişi sayısı yapıyordu ve triyaj
  çöküyordu. Düzeltildi, test eklendi.
- Eşleştirme yaklaşıktır: veri setinde "ihtiyaç türü" etiketlenmiş, aciliyet
  değil. Öncelik doğruluğu bu yüzden kaba bir göstergedir.
