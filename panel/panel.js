// panel.js
// ------------------------------------------------------------
// Panelin DAVRANIŞI.
//
// Tarayıcı, Mosquitto'ya WebSocket üzerinden bağlanan bir MQTT
// istemcisidir (tıpkı Python'daki cihazlar gibi):
//   1. "ev/#" topic'ine abone olur, gelen mesajlarla ekranı günceller.
//   2. Düğmelere basılınca "<cihaz topic'i>/komut" adresine komut yayınlar.
//
// Topic adları ve eşikler kodda tekrar yazılmaz; panel.py bunları
// ayarlar.py'den okuyup "/ayarlar.json" adresinden verir.
// ------------------------------------------------------------

"use strict";

// Ekranda gösterilecek Türkçe karşılıklar
const GORUNEN_AD = {
  acik: "Açık", kapali: "Kapalı",
  sogutma: "Soğutma", isitma: "Isıtma",
  devre_disi: "Devre dışı", kurulu: "Kurulu", caliyor: "ÇALIYOR!",
  var: "Var", yok: "Yok",
  cevrimici: "Çevrimiçi", cevrimdisi: "Çevrimdışı",
};

const GRAFIK_NOKTA_SAYISI = 90;   // Grafikte tutulacak ölçüm sayısı (2 sn arayla = 3 dk)
const GUNLUK_SATIR_SAYISI = 150;  // Günlükte tutulacak en fazla satır
const SIMULASYON_SURESI_MS = 4000; // Simüle edilen hareket/kapı olayının süresi

let A = null;       // ayarlar.json içeriği
let client = null;  // MQTT istemcisi

// Evin panelde bilinen son durumu (null = henüz haber gelmedi)
const ev = {
  sicaklik: null,
  sicaklikZamani: null,
  gecmis: [],          // [{ v: sıcaklık, k: o andaki klima durumu }]
  klima: null,
  lamba: null,
  hareket: null,
  hareketZamani: null, // Hareket durumunun son değiştiği an
  kapi: null,
  alarm: null,
  cihazlar: {},        // { cihaz_id: "cevrimici" | "cevrimdisi" }
  topicCihaz: {},      // { topic: o topic'e yayın yapan cihaz_id }
};

const $ = (id) => document.getElementById(id);
const ad = (durum) => GORUNEN_AD[durum] ?? durum ?? "—";

// ============================================================
// BAŞLANGIÇ
// ============================================================

async function basla() {
  try {
    const yanit = await fetch("ayarlar.json");
    A = await yanit.json();
  } catch {
    brokerDurumu("hata", "ayarlar.json okunamadı. Paneli 'python panel.py' ile açın.");
    return;
  }

  dugmeleriBagla();
  ciz();
  gunlukBosMu();
  baglan();

  // Her saniye "x sn önce" yazılarını güncelle
  setInterval(sureleriGuncelle, 1000);
  // Pencere boyutu değişince grafiği yeniden çiz
  new ResizeObserver(grafikCiz).observe($("sicaklik-grafik"));
}

// ============================================================
// MQTT BAĞLANTISI
// ============================================================

function baglan() {
  // Sayfa hangi bilgisayardan açıldıysa broker'ın da orada olduğunu varsayıyoruz.
  const adres = `ws://${location.hostname || "localhost"}:${A.websocket_portu}`;

  client = mqtt.connect(adres, {
    // Her sekme kendine özel bir kimlik alır (aynı kimlik broker'da çakışırdı).
    clientId: "panel-" + Math.random().toString(16).slice(2, 8),
    clean: true,
    reconnectPeriod: 2000,  // Bağlantı koparsa 2 sn'de bir yeniden dene
    connectTimeout: 5000,
  });

  client.on("connect", () => {
    brokerDurumu("bagli", "Broker'a bağlı");
    client.subscribe(A.abone_topic, { qos: A.qos });
  });
  client.on("reconnect", () => brokerDurumu("baglaniyor", "Yeniden bağlanıyor…"));
  client.on("close", () => brokerDurumu("kopuk", "Broker bağlantısı yok"));
  client.on("message", mesajGeldi);
}

function brokerDurumu(durum, metin) {
  $("broker-durum").dataset.durum = durum;
  $("broker-metin").textContent = metin;
  // Bağlantı yokken komut düğmeleri kullanılamaz
  document.querySelectorAll("button[data-cihaz], #lamba-dugme, button[data-sim]")
    .forEach((d) => { d.disabled = durum !== "bagli"; });
}

/** Bir eyleyiciye komut gönderir, ör. komutGonder("lamba", "acik") */
function komutGonder(cihaz, durum) {
  const topic = A.topicler[cihaz] + A.komut_eki;
  yayinla(topic, { durum, kaynak: "panel" });
}

function yayinla(topic, veri) {
  if (!client?.connected) return;
  const mesaj = JSON.stringify({ ...veri, zaman: zamanDamgasi() });
  client.publish(topic, mesaj, { qos: A.qos });
}

/**
 * Bir sensör olayını taklit eder: önce "aktif" durumu, birkaç saniye sonra
 * "pasif" durumu yayınlar. Gerçek sensörün yapacağı mesajın aynısıdır;
 * otomasyon da bunu gerçek bir olay gibi işler.
 */
function simuleEt(dugme, sensor, aktif, pasif) {
  const topic = A.topicler[sensor];
  yayinla(topic, { durum: aktif, kaynak: "panel-simulasyon" });
  dugme.disabled = true;
  setTimeout(() => {
    yayinla(topic, { durum: pasif, kaynak: "panel-simulasyon" });
    dugme.disabled = !client?.connected;
  }, SIMULASYON_SURESI_MS);
}

// ============================================================
// GELEN MESAJLAR
// ============================================================

function mesajGeldi(topic, payload, paket) {
  const metin = new TextDecoder().decode(payload);
  const veri = jsonCoz(metin);
  // paket.retain = true ise broker'ın sakladığı "son bilinen durum" mesajıdır
  gunlugeEkle(topic, metin, veri, paket.retain);

  // Bağlantı bilgisi: ev/sistem/baglanti/<cihaz_id>  ->  "cevrimici" / "cevrimdisi"
  const kok = A.baglanti_topic_koku + "/";
  if (topic.startsWith(kok)) {
    ev.cihazlar[topic.slice(kok.length)] = metin;
    cihazlariCiz();
    cevrimDurumlariniCiz();
    return;
  }

  if (!veri || topic.endsWith(A.komut_eki)) return;  // Komutlar sadece günlüğe yazılır

  // Bu topic'e hangi cihazın yayın yaptığını not et (çevrimdışı uyarısı için)
  if (veri.cihaz_id) ev.topicCihaz[topic] = veri.cihaz_id;

  const T = A.topicler;
  switch (topic) {
    case T.sicaklik:
      if (typeof veri.sicaklik !== "number") return;
      ev.sicaklik = veri.sicaklik;
      ev.sicaklikZamani = Date.now();
      ev.gecmis.push({ v: veri.sicaklik, k: ev.klima });
      if (ev.gecmis.length > GRAFIK_NOKTA_SAYISI) ev.gecmis.shift();
      break;
    case T.klima:  ev.klima = veri.durum; break;
    case T.lamba:  ev.lamba = veri.durum; break;
    case T.kapi:   ev.kapi = veri.durum; break;
    case T.alarm:  ev.alarm = veri.durum; break;
    case T.hareket:
      if (veri.durum !== ev.hareket && !paket.retain) ev.hareketZamani = Date.now();
      ev.hareket = veri.durum;
      break;
    default:
      return;
  }
  ciz();
  cevrimDurumlariniCiz();
}

function jsonCoz(metin) {
  try {
    const v = JSON.parse(metin);
    return v && typeof v === "object" && !Array.isArray(v) ? v : null;
  } catch {
    return null;
  }
}

// ============================================================
// EKRANI GÜNCELLEME
// ============================================================

function ciz() {
  // Sıcaklık ve klima
  $("sicaklik-deger").textContent = ev.sicaklik === null ? "--" : ev.sicaklik.toFixed(1);
  durumYaz("klima-durum", ev.klima);
  segmentiIsaretle("klima", ev.klima);

  // Lamba
  $("lamba-gorsel").dataset.durum = ev.lamba ?? "";
  durumYaz("lamba-durum", ev.lamba);
  $("lamba-dugme").textContent = ev.lamba === "acik" ? "Lambayı kapat" : "Lambayı aç";

  // Hareket ve kapı
  durumYaz("hareket-durum", ev.hareket);
  durumYaz("kapi-durum", ev.kapi);

  // Alarm
  $("alarm-kutu").dataset.durum = ev.alarm ?? "";
  durumYaz("alarm-durum", ev.alarm);
  segmentiIsaretle("alarm", ev.alarm);

  sureleriGuncelle();
  grafikCiz();
}

function durumYaz(id, durum) {
  const el = $(id);
  el.textContent = ad(durum);
  el.dataset.durum = durum ?? "";
}

/** Seçenek düğmelerinden mevcut duruma karşılık geleni "basılı" gösterir. */
function segmentiIsaretle(cihaz, durum) {
  document.querySelectorAll(`button[data-cihaz="${cihaz}"]`).forEach((d) => {
    d.setAttribute("aria-pressed", String(d.dataset.durum === durum));
  });
}

function sureleriGuncelle() {
  $("sicaklik-zaman").textContent = ev.sicaklikZamani
    ? `Son ölçüm ${kacSaniyeOnce(ev.sicaklikZamani)}`
    : "Veri bekleniyor…";

  let hareketMetni = "";
  if (ev.hareketZamani && ev.hareket === "var") {
    hareketMetni = `${kacSaniyeOnce(ev.hareketZamani)} başladı`;
  } else if (ev.hareketZamani && ev.hareket === "yok") {
    const kalan = A.lamba_kapanma_suresi - Math.floor((Date.now() - ev.hareketZamani) / 1000);
    hareketMetni = `Son hareket ${kacSaniyeOnce(ev.hareketZamani)}`;
    if (ev.lamba === "acik" && kalan > 0) hareketMetni += ` · lamba ~${kalan} sn sonra kapanacak`;
  }
  $("hareket-zaman").textContent = hareketMetni;
}

function kacSaniyeOnce(zaman) {
  const sn = Math.max(0, Math.round((Date.now() - zaman) / 1000));
  if (sn < 2) return "az önce";
  if (sn < 60) return `${sn} sn önce`;
  return `${Math.floor(sn / 60)} dk önce`;
}

/** Bir sensör/cihaz çevrimdışıysa kartındaki küçük kırmızı etiketi gösterir. */
function cevrimDurumlariniCiz() {
  document.querySelectorAll("[data-cevrim]").forEach((el) => {
    const cihazId = ev.topicCihaz[A.topicler[el.dataset.cevrim]];
    el.hidden = !(cihazId && ev.cihazlar[cihazId] === "cevrimdisi");
  });
}

function cihazlariCiz() {
  const liste = $("cihaz-listesi");
  const idler = Object.keys(ev.cihazlar).sort();
  liste.replaceChildren(...idler.map((id) => {
    const li = document.createElement("li");
    li.dataset.durum = ev.cihazlar[id];
    li.innerHTML = `<span class="nokta"></span><span class="ad"></span><span class="durum"></span>`;
    li.querySelector(".ad").textContent = id;
    li.querySelector(".durum").textContent = ad(ev.cihazlar[id]);
    return li;
  }));
}

// ============================================================
// SICAKLIK GRAFİĞİ (kütüphanesiz, elle çizilen SVG)
// ============================================================

function grafikCiz() {
  const svg = $("sicaklik-grafik");
  const g = svg.clientWidth, y = svg.clientHeight;  // genişlik, yükseklik (piksel)
  if (!g || !A) return;
  svg.setAttribute("viewBox", `0 0 ${g} ${y}`);

  const pay = { sol: 34, sag: 8, ust: 10, alt: 16 };  // kenar boşlukları
  const cizimG = g - pay.sol - pay.sag;
  const cizimY = y - pay.ust - pay.alt;
  const E = A.klima_esikleri;
  const degerler = ev.gecmis.map((n) => n.v);

  if (degerler.length < 2) {
    svg.innerHTML = `<text class="g-bos" x="${g / 2}" y="${y / 2}" text-anchor="middle">Grafik için ölçümler bekleniyor…</text>`;
    return;
  }

  // Dikey eksen aralığı: veriyi ve soğutma eşiklerini kapsasın
  const enAz = Math.floor(Math.min(...degerler, E.sogutma_dur) - 0.5);
  const enCok = Math.ceil(Math.max(...degerler, E.sogutma_basla) + 0.5);
  const yKoord = (v) => pay.ust + cizimY * (1 - (v - enAz) / (enCok - enAz));
  const xKoord = (i) => pay.sol + (cizimG * i) / (GRAFIK_NOKTA_SAYISI - 1);

  let s = "";

  // Yatay ızgara çizgileri ve sol eksen yazıları
  const adim = enCok - enAz > 8 ? 2 : 1;
  for (let v = enAz; v <= enCok; v += adim) {
    s += `<line class="g-izgara" x1="${pay.sol}" x2="${pay.sol + cizimG}" y1="${yKoord(v)}" y2="${yKoord(v)}"/>`;
    s += `<text class="g-eksen-yazi" x="${pay.sol - 6}" y="${yKoord(v) + 4}" text-anchor="end">${v}°</text>`;
  }

  // Otomasyon eşikleri (aralık içinde kalanlar)
  const esikler = [
    [E.sogutma_basla, "soğutma başlar"], [E.sogutma_dur, "soğutma durur"],
    [E.isitma_basla, "ısıtma başlar"], [E.isitma_dur, "ısıtma durur"],
  ];
  for (const [v, yazi] of esikler) {
    if (v < enAz || v > enCok) continue;
    s += `<line class="g-esik" x1="${pay.sol}" x2="${pay.sol + cizimG}" y1="${yKoord(v)}" y2="${yKoord(v)}"/>`;
  }

  // Eşik yazıları ayrı bir değişkende toplanır ve en son eklenir.
  // SVG'de sonra çizilen üstte görünür; böylece veri çizgisi yazıyı örtmez.
  let ustKatman = "";
  for (const [v, yazi] of esikler) {
    if (v < enAz || v > enCok) continue;
    ustKatman += `<text class="g-esik-yazi" x="${pay.sol + 6}" y="${yKoord(v) - 4}">${yazi} (${v}°)</text>`;
  }

  // En yeni ölçüm sağ kenarda olacak şekilde noktaları yerleştir
  const kayma = GRAFIK_NOKTA_SAYISI - degerler.length;
  const noktalar = ev.gecmis.map((n, i) => [xKoord(i + kayma), yKoord(n.v)]);

  // Alttaki şerit: klimanın o anda ne yaptığı
  const seritG = cizimG / (GRAFIK_NOKTA_SAYISI - 1) + 0.5;
  ev.gecmis.forEach((n, i) => {
    if (n.k === "sogutma" || n.k === "isitma") {
      s += `<rect class="g-${n.k}" x="${xKoord(i + kayma) - seritG / 2}" y="${y - 6}" width="${seritG}" height="5"/>`;
    }
  });

  // Çizginin altındaki hafif dolgu ve sıcaklık çizgisi
  const yol = noktalar.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
  const tabanY = pay.ust + cizimY;
  s += `<path class="g-alan" d="${yol}L${noktalar.at(-1)[0]},${tabanY}L${noktalar[0][0]},${tabanY}Z"/>`;
  s += `<path class="g-cizgi" d="${yol}"/>`;

  svg.innerHTML = s + ustKatman;
}

// ============================================================
// OLAY GÜNLÜĞÜ
// ============================================================

function gunlugeEkle(topic, metin, veri, kayitli) {
  // Sıcaklık 2 sn'de bir geldiği için istenmedikçe günlüğü kalabalıklaştırmasın
  if (topic === A.topicler.sicaklik && !$("sicaklik-goster").checked) return;

  const komutMu = topic.endsWith(A.komut_eki);
  let icerik;
  if (!veri) icerik = ad(metin);
  else if (typeof veri.sicaklik === "number") icerik = `${veri.sicaklik} °C`;
  else if ("durum" in veri) icerik = ad(veri.durum);
  else icerik = metin;
  if (komutMu) icerik = `KOMUT → ${icerik}`;
  if (veri?.kaynak) icerik += `  (${veri.kaynak})`;

  const li = document.createElement("li");
  li.dataset.tur = komutMu ? "komut" : "durum";
  li.innerHTML = `<time></time><code></code><span class="icerik"></span>`;
  // textContent kullanıyoruz: mesaj içeriği HTML olarak yorumlanmasın (güvenlik)
  li.querySelector("time").textContent = new Date().toLocaleTimeString("tr-TR");
  li.querySelector("code").textContent = topic;
  li.querySelector(".icerik").textContent = icerik;
  if (kayitli) {
    const k = document.createElement("span");
    k.className = "kayitli";
    k.textContent = "(kayıtlı son durum)";
    li.querySelector(".icerik").append(k);
  }

  const gunluk = $("gunluk");
  gunluk.querySelector(".bos")?.closest("li")?.remove();
  gunluk.prepend(li);  // En yeni mesaj en üstte
  while (gunluk.children.length > GUNLUK_SATIR_SAYISI) gunluk.lastElementChild.remove();
}

function gunlukBosMu() {
  const gunluk = $("gunluk");
  if (!gunluk.children.length) {
    gunluk.innerHTML = `<li><span class="bos">Henüz mesaj yok</span></li>`;
  }
}

// ============================================================
// DÜĞMELER
// ============================================================

function dugmeleriBagla() {
  // Klima ve alarm seçenek düğmeleri: data-cihaz / data-durum özelliklerinden okunur
  document.querySelectorAll("button[data-cihaz]").forEach((d) => {
    d.addEventListener("click", () => komutGonder(d.dataset.cihaz, d.dataset.durum));
  });

  $("lamba-dugme").addEventListener("click", () => {
    komutGonder("lamba", ev.lamba === "acik" ? "kapali" : "acik");
  });

  document.querySelectorAll("button[data-sim]").forEach((d) => {
    d.addEventListener("click", () => {
      if (d.dataset.sim === "hareket") simuleEt(d, "hareket", "var", "yok");
      else simuleEt(d, "kapi", "acik", "kapali");
    });
  });

  $("gunluk-temizle").addEventListener("click", () => {
    $("gunluk").replaceChildren();
    gunlukBosMu();
  });
}

function zamanDamgasi() {
  // Python tarafıyla aynı biçim: 2026-10-10T16:10:46 (yerel saat)
  const s = new Date();
  const iki = (n) => String(n).padStart(2, "0");
  return `${s.getFullYear()}-${iki(s.getMonth() + 1)}-${iki(s.getDate())}` +
         `T${iki(s.getHours())}:${iki(s.getMinutes())}:${iki(s.getSeconds())}`;
}

basla();
