# Vuruş tespiti ölçümü — 29.10.2026

Betikler: `python -m scripts.vurus_veri_indir`, sonra `python -m scripts.vurus_olc`.
Dedektör: `vurus/tespit.py` (bant geçiren filtre 150–1500 Hz, ani enerji yükselişi,
sönme ve bant oranı kontrolü, en az 3 düzenli vuruş). Makine öğrenmesi yok.

Veri: ESC-50 [Piczak, ACM MM 2015], CC BY-NC 3.0. 5 saniyelik gerçek kayıtlar.
Pozitif: `door_wood_knock` (kapıya vurma, 40 kayıt). Negatif: vuruşla karışabilecek
6 sınıf (alkış, ayak sesi, fare tıklaması, klavye, saat tıkırtısı, kutu açma; 240 kayıt).
Bir kayıtta en az bir vuruş serisi bulunursa "tespit" sayıldı.

Eşikler yalnızca 1–2. bölümlere (112 kayıt) bakılarak seçildi; aşağıdaki asıl sonuç
hiç bakılmayan 3–5. bölümler (168 kayıt).

| Sınıf | Test (3–5) | Ayar (1–2) |
|---|---|---|
| Kapıya vurma, duyarlılık | 12/24 = %50 | 10/16 = %62 |
| Alkış, yanlış alarm | 5/24 = %21 | 6/16 = %38 |
| Ayak sesi | 5/24 = %21 | 6/16 = %38 |
| Fare tıklaması | 0/24 = %0 | 4/16 = %25 |
| Klavye | 1/24 = %4 | 0/16 = %0 |
| Saat tıkırtısı | 7/24 = %29 | 5/16 = %31 |
| Kutu açma | 1/24 = %4 | 0/16 = %0 |
| Negatif toplam | 19/144 = %13 | 21/96 = %22 |

Süre: 5 saniyelik kayıt başına ortalama 23 ms (Ryzen 5 5600H), gerçek zamanın çok altında.

Geliştirme sırasında:

- İlk sürüm (sabit süre eşiği) ayar bölümünde %44 duyarlılık, %57 yanlış alarm verdi.
  Tahta vuruşu 100–250 ms tınladığı ve hızlı vuruşlar birleştiği için "kısa ses" kuralı
  gerçek vuruşları eliyordu; "ani yükseliş + sönme" kuralına geçildi.
- Bant oranı (darbe enerjisinin 150–1500 Hz'deki payı) en etkili parametre çıktı;
  diğerleri ayar bölümünde 1–2 kayıttan fazla fark yaratmadı.

Sınırlar:

- Kapıya vurma kayıtlarının bir kısmında yalnızca 1–2 vuruş var; 3 vuruş şartı bunları
  bilerek kaçırıyor.
- Saat tıkırtısı ve alkış düzenli darbe dizisi olduğu için kural tabanlı yöntemle
  ayrılması zor; makine öğrenmesi ya da daha uzun örüntü (ör. üç vuruş + duraklama) gerekir.
- Enkaz altı vuruşu (beton, boru) kapıya vurmadan farklı ses verir; gerçek enkaz
  kaydıyla ölçülmedi. Test kümesi küçük (24 pozitif).
