"use strict";

const renk = Object.fromEntries(
  ["yazi-2", "yazi-3", "cizgi", "notr", "kritik", "uyari", "normal", "panel"].map(
    (ad) => [ad, getComputedStyle(document.documentElement).getPropertyValue("--" + ad).trim()]
  )
);
const EN_FAZLA_SATIR = 200;
const KUTU_OMRU_MS = 1500;

function saatYaz(zaman) {
  return new Date(zaman).toLocaleTimeString("tr-TR", { hour12: false });
}

function hucre(satir, metin, sinif) {
  const td = satir.insertCell();
  if (metin instanceof Node) td.append(metin);
  else td.textContent = metin;
  if (sinif) td.className = sinif;
  return td;
}

function etiket(metin, sinif) {
  const s = document.createElement("span");
  s.className = "etiket " + sinif;
  s.textContent = metin;
  return s;
}

function satirSinirla(tbody) {
  while (tbody.rows.length > EN_FAZLA_SATIR) tbody.deleteRow(-1);
}

// --- Saat ---
const saat = document.getElementById("saat");
setInterval(() => (saat.textContent = new Date().toLocaleString("tr-TR", { hour12: false })), 1000);

// --- Olay listesi ---
const olaylar = document.getElementById("olaylar");
const olaySatirlari = new Map();
const olaySayisi = document.getElementById("olay-sayisi");

function olaySatiri(id, doldur, sos) {
  // Birlesen olay ayni satiri gunceller ve en uste tasinir; liste "en son ne oldu" sorusunu cevaplasin.
  let satir = olaySatirlari.get(id);
  if (satir) satir.remove();
  satir = document.createElement("tr");
  if (sos) satir.className = "sos";
  doldur(satir);
  olaylar.prepend(satir);
  olaySatirlari.set(id, satir);
  satirSinirla(olaylar);
  for (const [anahtar, s] of olaySatirlari) if (!s.isConnected) olaySatirlari.delete(anahtar);
  olaySayisi.textContent = olaylar.rows.length;
}

function olayAl(olay, canli = true) {
  const ad = olay.etiket === "insan" ? "İnsan" : "Vuruş";
  olaySatiri(olay.olay_id, (s) => {
    hucre(s, saatYaz(olay.zaman));
    hucre(s, etiket(ad, olay.etiket));
    hucre(s, olay.kaynak === "kamera" ? "Kamera" : "Mikrofon");
    hucre(s, olay.guven.toFixed(2), "sag");
    hucre(s, olay.adet, "sag");
  });
  if (olay.kutu && canli) kutular.set(olay.olay_id, { ...olay, alindi: performance.now() });
}

// --- Canli izleme ---
const kamera = document.getElementById("kamera");
const ciz = kamera.getContext("2d");
const kutular = new Map();
const kameraAdi = document.getElementById("kamera-adi");
// Kamera programi --kare ile kare gonderiyorsa goruntu ve tum kutular ondan cizilir.
let sonKare = null;
const KARE_OMRU_MS = 2000;

function kareAl(k) {
  const resim = new Image();
  resim.onload = () => (sonKare = { resim, kutular: k.kutular, alindi: performance.now() });
  resim.src = "data:image/jpeg;base64," + k.jpeg;
  kameraAdi.textContent = "Kamera 1 · " + k.kaynak + " (benzetim)";
}

function kutuCiz(k, ox, oy, gw, gh) {
  ciz.strokeStyle = renk.uyari;
  ciz.lineWidth = 2;
  ciz.strokeRect(ox + k.x * gw, oy + k.y * gh, k.w * gw, k.h * gh);
  const yazi = "insan " + k.guven.toFixed(2);
  ciz.fillStyle = renk.uyari;
  ciz.fillRect(ox + k.x * gw - 1, oy + k.y * gh - 17, ciz.measureText(yazi).width + 8, 16);
  ciz.fillStyle = "#121417";
  ciz.fillText(yazi, ox + k.x * gw + 3, oy + k.y * gh - 5);
}

function kameraCiz() {
  const olcek = window.devicePixelRatio || 1;
  const w = kamera.clientWidth, h = kamera.clientHeight;
  if (kamera.width !== Math.round(w * olcek) || kamera.height !== Math.round(h * olcek)) {
    kamera.width = Math.round(w * olcek);
    kamera.height = Math.round(h * olcek);
  }
  ciz.setTransform(olcek, 0, 0, olcek, 0, 0);
  ciz.fillStyle = "#0d0f11";
  ciz.fillRect(0, 0, w, h);

  ciz.font = "12px system-ui, sans-serif";
  const simdi = performance.now();
  if (sonKare && simdi - sonKare.alindi < KARE_OMRU_MS) {
    // Goruntu oranini bozmadan panele sigdir.
    const r = sonKare.resim, olcekR = Math.min(w / r.width, h / r.height);
    const gw = r.width * olcekR, gh = r.height * olcekR, ox = (w - gw) / 2, oy = (h - gh) / 2;
    ciz.drawImage(r, ox, oy, gw, gh);
    sonKare.kutular.forEach((k) => kutuCiz(k, ox, oy, gw, gh));
  } else {
    ciz.strokeStyle = renk.cizgi;
    ciz.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      ciz.beginPath(); ciz.moveTo((w * i) / 4, 0); ciz.lineTo((w * i) / 4, h); ciz.stroke();
      ciz.beginPath(); ciz.moveTo(0, (h * i) / 4); ciz.lineTo(w, (h * i) / 4); ciz.stroke();
    }
    ciz.fillStyle = renk["yazi-3"];
    ciz.fillText("Görüntü yok (yer tutucu)", 10, h - 10);
    ciz.fillText(new Date().toLocaleTimeString("tr-TR", { hour12: false }), w - 70, 18);
    kameraAdi.textContent = "Kamera 1";
    for (const [id, o] of kutular) {
      if (simdi - o.alindi > KUTU_OMRU_MS) { kutular.delete(id); continue; }
      kutuCiz({ ...o.kutu, guven: o.guven }, 0, 0, w, h);
    }
  }
  requestAnimationFrame(kameraCiz);
}
requestAnimationFrame(kameraCiz);

// --- Harita ---
// Karolar data/tiles/yozgat.pmtiles dosyasindan gelir; internet gerekmez.
const BOLGE = L.latLngBounds([39.75, 34.72], [39.87, 34.9]);
const harita = L.map("harita", { maxBounds: BOLGE.pad(0.1), minZoom: 12, maxZoom: 18 }).setView([39.818, 34.808], 14);
protomapsL.leafletLayer({
  url: "/karolar/yozgat.pmtiles",
  flavor: "dark",
  lang: "tr",
  maxDataZoom: 15,
  attribution: "&copy; OpenStreetMap katkıcıları, Protomaps",
}).addTo(harita);
harita.attributionControl.setPrefix("Leaflet");
const katman = {
  siginak: L.layerGroup().addTo(harita),
  mesaj: L.layerGroup().addTo(harita),
  // Renk yalnizca uyari-kritik araliginda: yogunluk = bekleyen vaka.
  isi: L.heatLayer([], { radius: 28, blur: 22, maxZoom: 17, gradient: { 0.3: renk.uyari, 0.7: renk.kritik, 1: "#ff9b9e" } }).addTo(harita),
  dugum: L.layerGroup().addTo(harita),
  kapsama: L.layerGroup(),
  sensor: L.layerGroup().addTo(harita),
};
L.control.layers(null, {
  "Sığınaklar": katman.siginak,
  "Mesajlar ve SOS": katman.mesaj,
  "Isı haritası (açık vakalar)": katman.isi,
  "Düğümler": katman.dugum,
  "Kapsama alanları": katman.kapsama,
  "Kamera ve mikrofon": katman.sensor,
}).addTo(harita);
const dugumIsaretleri = new Map();

fetch("/api/dugumler")
  .then((c) => c.json())
  .then((veri) => {
    for (const f of veri.features) {
      const [lon, lat] = f.geometry.coordinates;
      const p = f.properties;
      if (p.tur === "dugum") {
        L.circle([lat, lon], { radius: p.menzil_m, color: renk.notr, weight: 1, dashArray: "4 4", fillOpacity: 0.06 })
          .addTo(katman.kapsama);
        const m = L.circleMarker([lat, lon], { radius: 5, color: renk.panel, weight: 2, fillColor: renk.notr, fillOpacity: 1 })
          .bindPopup(popup([["Düğüm " + p.id], [null, "Menzil: " + p.menzil_m + " m (" + p.kaynak + ")"]]))
          .addTo(katman.dugum);
        dugumIsaretleri.set(p.id, m);
      } else {
        L.circleMarker([lat, lon], { radius: 4, color: "#fff", weight: 1, fillColor: renk["yazi-3"], fillOpacity: 1 })
          .bindPopup(popup([[p.tur === "kamera" ? "Kamera " + p.id : "Mikrofon " + p.id], [null, "Konum: " + p.kaynak]]))
          .addTo(katman.sensor);
      }
    }
  });
let mesajNoktasi = 0;

function popup(satirlar) {
  const div = document.createElement("div");
  for (const [baslik, metin] of satirlar) {
    const p = document.createElement("div");
    if (baslik) {
      const b = document.createElement("b");
      b.textContent = baslik;
      p.append(b);
    } else p.textContent = metin;
    div.append(p);
  }
  return div;
}

fetch("/api/siginaklar")
  .then((c) => c.json())
  .then((veri) => {
    for (const f of veri.features) {
      const [lon, lat] = f.geometry.coordinates;
      const p = f.properties;
      L.circleMarker([lat, lon], { radius: 7, color: "#fff", weight: 2, fillColor: renk.notr, fillOpacity: 1 })
        .bindPopup(popup([[p.ad], [null, "Kapasite: " + p.kapasite + " kişi"], [null, "Kaynak: " + p.kaynak]]))
        .addTo(katman.siginak);
    }
    haritaOzet(veri.features.length);
  });

function haritaOzet(siginak) {
  if (siginak !== undefined) haritaOzet.siginak = siginak;
  document.getElementById("harita-ozet").textContent =
    (haritaOzet.siginak ?? 0) + " sığınak, " + mesajNoktasi + " konumlu mesaj";
}

function haritayaMesaj(m, zaman) {
  const sos = m.tur === "SOS";
  L.circleMarker([m.gps.lat, m.gps.lon], {
    radius: sos ? 8 : 6, color: sos ? renk.kritik : renk["yazi-2"], weight: 2,
    fillColor: sos ? renk.kritik : renk.panel, fillOpacity: sos ? 0.9 : 0.8,
  })
    .bindPopup(popup([[sos ? "SOS" : "Mesaj"], [null, m.yuk], [null, m.kaynak + ", " + saatYaz(zaman)]]))
    .addTo(katman.mesaj);
  mesajNoktasi++;
  haritaOzet();
}

// --- Mesajlar ---
const mesajlar = document.getElementById("mesajlar");
const TUR_ADI = { SOS: "SOS", hazir_mesaj: "Hazır mesaj", ack: "Onay" };
const kaynakAdi = (k) => (k === "merkez" ? "Merkez (gönderildi)" : k);

function iletimEtiketi(iletim) {
  const s = document.createElement("span");
  s.className = "iletim" + (iletim.kanal ? "" : " hata");
  s.textContent = iletim.kanal
    ? iletim.kanal + " · " + iletim.boyut + " B" + (iletim.kirpildi ? " · kırpıldı" : "")
    : "Gönderilemedi";
  s.title = iletim.denenen.join("\n") + "\nJSON olsaydı: " + iletim.json_boyut + " B";
  return s;
}

function mesajAl(m, alindi) {
  const sos = m.tur === "SOS";
  // Mesajda alinma zamani yok; sunucunun yayinladigi an, o da yoksa panelin gordugu an.
  const zaman = alindi ? new Date(alindi) : new Date();
  const s = mesajlar.insertRow(0);
  if (sos) s.className = "sos";
  hucre(s, saatYaz(zaman));
  hucre(s, kaynakAdi(m.kaynak));
  hucre(s, etiket(TUR_ADI[m.tur], sos ? "sos" : "mesaj"));
  const metinHucresi = hucre(s, m.yuk + " ", "metin");
  if (m.iletim) metinHucresi.append(iletimEtiketi(m.iletim));
  satirSinirla(mesajlar);

  if (sos) {
    olaySatiri("mesaj-" + m.id, (r) => {
      hucre(r, saatYaz(zaman));
      hucre(r, etiket("SOS", "sos"));
      hucre(r, kaynakAdi(m.kaynak));
      hucre(r, m.yuk);
      r.lastChild.colSpan = 2;
    }, true);
  }
  if (m.gps) haritayaMesaj(m, zaman);
}

const gonderim = document.getElementById("gonderim");
const dugmeler = document.querySelectorAll(".dugmeler button");

async function mesajGonder(tur, yuk) {
  dugmeler.forEach((d) => (d.disabled = true));
  gonderim.className = "gonderim";
  gonderim.textContent = "Gönderiliyor...";
  try {
    const cevap = await fetch("/api/mesaj", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tur, yuk }),
    });
    if (!cevap.ok) throw new Error("sunucu " + cevap.status + " döndü");
    const m = await cevap.json();
    gonderim.textContent = m.iletim.kanal
      ? saatYaz(new Date()) + " gönderildi: " + yuk + " (" + m.iletim.kanal + ", " + m.iletim.boyut + " bayt)"
      : "Gönderilemedi: tüm kanallar çökük ya da mesaj sığmıyor";
    if (!m.iletim.kanal) gonderim.className = "gonderim hata";
  } catch (hata) {
    gonderim.className = "gonderim hata";
    gonderim.textContent = "Gönderilemedi: " + hata.message;
  } finally {
    dugmeler.forEach((d) => (d.disabled = false));
  }
}

for (const d of document.querySelectorAll(".dugmeler button[data-yuk]")) {
  d.addEventListener("click", () => mesajGonder("hazir_mesaj", d.dataset.yuk));
}
document.getElementById("sos").addEventListener("click", () => mesajGonder("SOS", "Yardım gerekiyor"));

// --- Portal ---
const PORTAL_DURUM = { enkaz: "Enkaz altında", yarali: "Yaralı var", guvende: "Güvende", baska: "Başka durum" };
const portalSatirlari = new Map();
const portalNoktalari = new Map();

function portalOzet(k) {
  const parcalar = [PORTAL_DURUM[k.durum]];
  if (k.kisi) parcalar.push(k.kisi + " kişi");
  if (k.yarali !== null) parcalar.push(k.yarali ? "yaralı var" : "yaralı yok");
  if (k.tarif) parcalar.push(k.tarif);
  if (k.mesaj) parcalar.push(k.mesaj);
  if (k.ad) parcalar.push(k.ad);
  if (k.adet > 1) parcalar.push(k.adet + " çağrı");
  return parcalar.join(" · ");
}

function asilsizDugmesi(k) {
  const d = document.createElement("button");
  d.className = "kucuk";
  d.textContent = k.asilsiz ? "Geri al" : "Asılsız";
  d.addEventListener("click", async () => {
    d.disabled = true;
    await fetch("/api/portal/" + encodeURIComponent(k.kod) + "/asilsiz" + (k.asilsiz ? "?kaldir=true" : ""), { method: "POST" });
  });
  return d;
}

function triyajEtiketi(k) {
  const span = document.createElement("span");
  const t = k.triyaj;
  span.append(etiket("Ö" + t.oncelik, "o" + t.oncelik), " ");
  const y = document.createElement("span");
  y.className = "yontem";
  y.textContent = t.yontem === "llm" ? "LLM" : "kural";
  y.title = "Sınıflandırma yöntemi";
  span.append(y);
  return span;
}

function portalAl(k) {
  const sos = k.tur === "SOS" && !k.asilsiz;
  const ozet = portalOzet(k) + (k.triyaj.ozet && k.triyaj.yontem === "llm" ? " · Özet: " + k.triyaj.ozet : "");
  const zaman = k.guncellendi || k.zaman;
  const tur = k.asilsiz ? etiket("Asılsız", "asilsiz") : etiket(k.tur === "SOS" ? "SOS" : "Güvende", sos ? "sos" : "mesaj");

  olaySatiri("portal-" + k.kod, (r) => {
    if (k.asilsiz) r.classList.add("asilsiz");
    hucre(r, saatYaz(zaman));
    hucre(r, tur.cloneNode(true)).append(" ", triyajEtiketi(k));
    hucre(r, "Portal " + k.kod);
    hucre(r, ozet, "metin");
    r.lastChild.colSpan = 2;
  }, sos);

  // Guncellenen kayit yeni satir acmaz, ayni satir en uste tasinir.
  portalSatirlari.get(k.kod)?.remove();
  const s = mesajlar.insertRow(0);
  if (sos) s.className = "sos";
  if (k.asilsiz) s.className = "asilsiz";
  hucre(s, saatYaz(zaman));
  hucre(s, "Portal " + k.kod);
  const turHucresi = hucre(s, tur);
  turHucresi.append(" ", triyajEtiketi(k));
  if (k.onceden_asilsiz && !k.asilsiz) turHucresi.append(" ", etiket("Önceden asılsız", "asilsiz"));
  const metin = hucre(s, ozet + " ", "metin");
  if (k.iletim) metin.append(iletimEtiketi(k.iletim), " ");
  metin.append(asilsizDugmesi(k));
  portalSatirlari.set(k.kod, s);
  satirSinirla(mesajlar);

  if (k.gps) {
    portalNoktalari.get(k.kod)?.remove();
    const nokta = L.circleMarker([k.gps.lat, k.gps.lon], {
      radius: sos ? 8 : 6, color: sos ? renk.kritik : renk["yazi-2"], weight: 2,
      fillColor: sos ? renk.kritik : renk.panel, fillOpacity: sos ? 0.9 : 0.8,
    })
      .bindPopup(popup([["Portal " + k.kod], [null, ozet], [null, "Konum: erişim noktası"]]))
      .addTo(katman.mesaj);
    if (!portalNoktalari.has(k.kod)) mesajNoktasi++;
    portalNoktalari.set(k.kod, nokta);
    haritaOzet();
  }
}

const qrKutu = document.getElementById("qr-kutu");
document.getElementById("qr-ac").addEventListener("click", async () => {
  const { adres } = await (await fetch("/api/portal/adres")).json();
  const qr = qrcode(0, "M");
  qr.addData(adres);
  qr.make();
  document.getElementById("qr").innerHTML = qr.createSvgTag({ cellSize: 6, margin: 4 });
  document.getElementById("qr-adres").textContent = adres;
  qrKutu.showModal();
});

// --- Kanallar ---
const kanalKutusu = document.getElementById("kanallar");

function kanallarCiz(liste) {
  kanalKutusu.replaceChildren();
  for (const k of liste) {
    const b = document.createElement("button");
    b.className = k.acik ? "acik" : "cokuk";
    b.textContent = k.ad + (k.acik ? " açık" : " çökük");
    b.title = "Sınır " + k.sinir + " bayt. Tıklayınca " + (k.acik ? "çökertilir" : "açılır") + ".";
    b.addEventListener("click", () => {
      b.disabled = true;
      fetch("/api/kanal/" + k.ad, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ acik: !k.acik }),
      });
    });
    kanalKutusu.append(b);
  }
}
fetch("/api/kanallar").then((c) => c.json()).then(kanallarCiz);

// --- Kuyruk ---
const kuyrukGovde = document.getElementById("kuyruk");
const vakalar = new Map();
const DURUM_ADI = { yeni: "Yeni", ekip_yonlendirildi: "Ekip yönlendirildi", kurtarildi: "Kurtarıldı" };
const SONRAKI = { yeni: ["ekip_yonlendirildi", "Ekip Yönlendir"], ekip_yonlendirildi: ["kurtarildi", "Kurtarıldı"] };
let kuyrukBekliyor = false;

function vakaKaynagi(v) {
  if (v.kaynak === "olay") return v.veri.kaynak === "kamera" ? "Kamera" : "Mikrofon";
  if (v.kaynak === "mesaj") return "Düğüm " + v.veri.kaynak;
  return "Portal " + v.id;
}

function vakaOzeti(v) {
  if (v.kaynak === "olay") {
    const ad = v.veri.etiket === "insan" ? "İnsan tespiti" : "Vuruş";
    return ad + " · " + v.veri.seri + " seri, " + v.veri.tespit + " tespit · en yüksek güven " +
      v.veri.en_yuksek_guven.toFixed(2) + " · son " + saatYaz(v.veri.son_olay.zaman);
  }
  if (v.kaynak === "mesaj") return "SOS: " + v.veri.yuk;
  return portalOzet(v.veri);
}

function durumGonder(id, durum, dugme) {
  dugme.disabled = true;
  fetch("/api/vaka/" + encodeURIComponent(id) + "/durum", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ durum }),
  }).then((c) => { if (!c.ok) dugme.disabled = false; });
}

function kuyrukCiz() {
  kuyrukBekliyor = false;
  const acik = [...vakalar.values()]
    .filter((v) => v.durum !== "kurtarildi")
    .sort((a, b) => a.oncelik - b.oncelik || a.zaman.localeCompare(b.zaman));
  kuyrukGovde.replaceChildren();
  for (const v of acik) {
    const s = kuyrukGovde.insertRow();
    const asilsiz = v.kaynak === "portal" && v.veri.asilsiz;
    if (asilsiz) s.className = "asilsiz";
    else if (v.oncelik === 1 && v.durum === "yeni") s.className = "sos";
    hucre(s, etiket("Ö" + v.oncelik, "o" + v.oncelik));
    hucre(s, saatYaz(v.zaman));
    hucre(s, vakaKaynagi(v));
    hucre(s, vakaOzeti(v), "metin");
    const islem = hucre(s, "", "islem");
    const d = document.createElement("span");
    d.className = "durum-etiketi " + v.durum;
    d.textContent = DURUM_ADI[v.durum];
    islem.append(d);
    const sonraki = SONRAKI[v.durum];
    if (sonraki) {
      const b = document.createElement("button");
      b.className = "kucuk";
      b.textContent = sonraki[1];
      b.addEventListener("click", () => durumGonder(v.id, sonraki[0], b));
      islem.append(b);
    }
  }
  document.getElementById("kuyruk-sayisi").textContent = acik.length;
  const AGIRLIK = { 1: 1, 2: 0.6, 3: 0.3 };
  katman.isi.setLatLngs(acik.map((v) => v.konum || v.veri.gps).map((k, i) => k && [k.lat, k.lon, AGIRLIK[acik[i].oncelik]]).filter(Boolean));
  const kurtarilan = [...vakalar.values()].filter((v) => v.durum === "kurtarildi").length;
  document.getElementById("kurtarilan").textContent = kurtarilan ? kurtarilan + " kurtarıldı" : "";
}

function vakaAl(v) {
  vakalar.set(v.id, v);
  // Saniyede onlarca guncelleme gelebilir; tabloyu kare basina bir kez kur.
  if (!kuyrukBekliyor) {
    kuyrukBekliyor = true;
    requestAnimationFrame(kuyrukCiz);
  }
}

async function kuyrukYukle() {
  const { kuyruk } = await (await fetch("/api/kuyruk")).json();
  for (const [id, v] of vakalar) if (v.durum !== "kurtarildi") vakalar.delete(id);
  kuyruk.forEach(vakaAl);
}

for (const b of document.querySelectorAll(".sekmeler button")) {
  b.addEventListener("click", () => {
    for (const d of document.querySelectorAll(".sekmeler button")) d.classList.toggle("secili", d === b);
    document.getElementById("sekme-kuyruk").hidden = b.dataset.sekme !== "kuyruk";
    document.getElementById("sekme-olaylar").hidden = b.dataset.sekme !== "olaylar";
  });
}

// --- Senaryo ---
const senaryoSec = document.getElementById("senaryo-sec");
const senaryoDugme = document.getElementById("senaryo-dugme");
const senaryoBilgi = document.getElementById("senaryo-durum");
let senaryoDurumu = { durum: "bos" };

function dakika(sn) {
  return Math.floor(sn / 60) + ":" + String(Math.floor(sn % 60)).padStart(2, "0");
}

function senaryoCiz() {
  const d = senaryoDurumu;
  const calisiyor = d.durum === "calisiyor";
  senaryoDugme.textContent = calisiyor ? "Durdur" : "Senaryoyu başlat";
  senaryoDugme.classList.toggle("calisiyor", calisiyor);
  senaryoSec.disabled = calisiyor;
  if (d.durum === "bos") {
    senaryoBilgi.textContent = "";
    return;
  }
  const gecen = calisiyor ? (Date.now() - new Date(d.baslangic)) / 1000 : d.sure;
  const ad = { calisiyor: "", bitti: "Bitti · ", durduruldu: "Durduruldu · " }[d.durum];
  senaryoBilgi.textContent = ad + d.adim + "/" + d.toplam + " · " + dakika(Math.min(gecen, d.sure)) + " / " +
    dakika(d.sure) + (d.not_ ? " · " + d.not_ : "");
  senaryoBilgi.title = d.ad;
}

function senaryoAl(d) {
  senaryoDurumu = d;
  senaryoCiz();
}
setInterval(() => senaryoDurumu.durum === "calisiyor" && senaryoCiz(), 1000);

fetch("/api/senaryolar")
  .then((c) => c.json())
  .then(({ senaryolar, durum }) => {
    for (const s of senaryolar) {
      const o = document.createElement("option");
      o.value = s.dosya;
      o.textContent = s.ad + " (" + dakika(s.sure) + ")";
      o.title = s.aciklama;
      senaryoSec.append(o);
    }
    if (!senaryolar.length) senaryoDugme.disabled = true;
    senaryoAl(durum);
  });

senaryoDugme.addEventListener("click", async () => {
  if (senaryoDurumu.durum === "calisiyor") {
    await fetch("/api/senaryo/durdur", { method: "POST" });
    return;
  }
  const temizle = document.getElementById("senaryo-temizle").checked;
  if (temizle && !confirm("Kuyruktaki tüm vakalar ve portal kayıtları silinecek. Devam edilsin mi?")) return;
  senaryoDugme.disabled = true;
  const cevap = await fetch("/api/senaryo/baslat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dosya: senaryoSec.value, temizle }),
  });
  senaryoDugme.disabled = false;
  if (!cevap.ok) senaryoBilgi.textContent = "Başlatılamadı: " + (await cevap.json()).detail;
});

// --- Durum raporu ---
function raporAl(r) {
  document.getElementById("rapor-metin").textContent = r.metin;
  document.getElementById("rapor-bilgi").textContent =
    saatYaz(r.zaman) + " · " + (r.yontem === "llm" ? "LLM" : "kural tabanlı");
}
fetch("/api/rapor").then((c) => c.json()).then((r) => r && raporAl(r));

// --- Sinyal ---
// Renk durumu anlatir: esigin altindaki dugum turuncu/kirmizi, digerleri gri.
const ESIK = { rssi: [-85, -95], oran: [80, 60], pil: [40, 20] };
const sinyaller = new Map();
Chart.defaults.color = renk["yazi-2"];
Chart.defaults.font.family = "system-ui, sans-serif";
Chart.defaults.font.size = 11;

function grafik(id, min, max, adim) {
  return new Chart(document.getElementById(id), {
    type: "bar",
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 2, barPercentage: 0.7 }] },
    options: {
      indexAxis: "y",
      animation: false,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { displayColors: false } },
      scales: {
        x: { min, max, ticks: { stepSize: adim }, grid: { color: renk.cizgi }, border: { display: false } },
        y: { grid: { display: false }, border: { color: renk.cizgi } },
      },
    },
  });
}

const gRssi = grafik("g-rssi", -110, -30, 20);
const gOran = grafik("g-oran", 0, 100, 20);
const gPil = grafik("g-pil", 0, 100, 20);

function durumRengi(deger, [uyari, kritik]) {
  if (deger <= kritik) return renk.kritik;
  if (deger <= uyari) return renk.uyari;
  return renk.notr;
}

function grafikleriGuncelle() {
  const dugumler = [...sinyaller.keys()].sort();
  const rssi = dugumler.map((d) => sinyaller.get(d).rssi);
  const oran = dugumler.map((d) => Math.round(sinyaller.get(d).paket_alim_orani * 100));
  const pil = dugumler.map((d) => sinyaller.get(d).pil ?? 0);
  // Acil moddaki dugum etiketinde belirtilir; renk yine yalnizca durum (esik) icin.
  const etiketler = dugumler.map((d) => d + (sinyaller.get(d).mod === "acil" ? " · acil" : ""));
  const acilSayisi = dugumler.filter((d) => sinyaller.get(d).mod === "acil").length;
  document.getElementById("mod-ozet").textContent = acilSayisi ? acilSayisi + " düğüm acil modda" : "düşük güç";
  for (const [g, veri, esik] of [[gRssi, rssi, ESIK.rssi], [gOran, oran, ESIK.oran], [gPil, pil, ESIK.pil]]) {
    g.data.labels = etiketler;
    // RSSI negatif; cubuk eksenin solundan baslasin diye taban en alt degerde.
    g.data.datasets[0].data = g === gRssi ? veri.map((v) => [-110, v]) : veri;
    g.data.datasets[0].backgroundColor = veri.map((v) => durumRengi(v, esik));
    g.update();
  }
  for (const [id, s] of sinyaller) dugumIsaretleri.get(id)?.setStyle({ fillColor: durumRengi(s.rssi, ESIK.rssi) });
}
gRssi.options.plugins.tooltip.callbacks = { label: (b) => b.raw[1] + " dBm" };
gOran.options.plugins.tooltip.callbacks = { label: (b) => "%" + b.raw };
gPil.options.plugins.tooltip.callbacks = { label: (b) => "%" + b.raw.toFixed(1) };
// Sinyal saniyede dugum basina bir kez gelir; her pakette degil saniyede bir cizmek yeterli.
setInterval(() => sinyaller.size && grafikleriGuncelle(), 1000);

// --- WebSocket ---
const durum = document.getElementById("durum");
let bekleme = 1000;

function paketAl({ tip, veri, alindi }) {
  if (tip === "olay") olayAl(veri, !alindi);
  else if (tip === "mesaj") mesajAl(veri, alindi);
  else if (tip === "sinyal") sinyaller.set(veri.dugum_id, veri);
  else if (tip === "portal") portalAl(veri);
  else if (tip === "rapor") raporAl(veri);
  else if (tip === "vaka") vakaAl(veri);
  else if (tip === "kanallar") kanallarCiz(veri.kanallar);
  else if (tip === "senaryo") senaryoAl(veri);
  else if (tip === "kare") kareAl(veri);
  // Kuyruk temizlendi: listeleri bastan kurmanin en kisa yolu sayfayi yenilemek.
  else if (tip === "sifirla") location.reload();
}

function baglan() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => {
    bekleme = 1000;
    // Kopuk kaldigimiz surede degisenleri kacirmamak icin kuyruk bastan alinir.
    kuyrukYukle();
    durum.className = "durum bagli";
    durum.textContent = "Bağlı";
  };
  ws.onmessage = (e) => paketAl(JSON.parse(e.data));
  ws.onclose = () => {
    durum.className = "durum kopuk";
    durum.textContent = "Bağlantı yok, " + Math.round(bekleme / 1000) + " sn sonra yeniden denenecek";
    setTimeout(baglan, bekleme);
    // Sunucu uzun sure kapaliysa tarayici saniyede bir denemesin.
    bekleme = Math.min(bekleme * 2, 10000);
  };
}
// Sayfa yenilenince listeler bos kalmasin: once son yayinlar oynatilir, sonra canli akisa baglanilir.
fetch("/api/gecmis")
  .then((c) => c.json())
  .then((paketler) => paketler.forEach(paketAl))
  .finally(baglan);
