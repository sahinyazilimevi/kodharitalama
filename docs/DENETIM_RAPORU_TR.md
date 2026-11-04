# Denetim Raporu — kodharitalama 0.30.103

**Marka:** Şahin Yazılım Evi · **Geliştirici:** Murat ŞAHİN · **Dağıtım:** kodharitalama
**Referans (üst proje):** Graphify `v8`
https://github.com/Graphify-Labs/graphify

Bu rapor, `kodharitalama` 0.30.103 sürümünün statik güvenlik denetimini, uygulanan kontrolleri ve çalıştırılamayan denetimleri Türkçe olarak özetler. Depoda hiçbir değişiklik git'e itilmemiştir ve itilmeyecektir.

---

## 1. Kapsam ve metod

Denetim şu kaynaklarla sınırlıdır:

- `graphify/` içe aktarma paketi (CLI, çıkarıcılar, dışa aktarıcılar, güvenlik modülü, skill'ler)
- `tools/install_skills.py` proje yerel IDE kurucusu
- `integrations/` IDE talimat şablonları
- `tests/` mevcut ve yeni testler
- `requirements.lock` karma kilitli bağımlılık kapanışı
- `pyproject.toml`, `uv.lock` sürüm ve bağlayıcı meta verileri

Yöntem:

- Statik kod incelemesi (grep / kalıp taraması): `shell=True`, `os.system`, `os.popen`, `eval(`, `exec(`, CDN kaynakları, paket dizini kurulumu, telemetri uç noktaları, gizli dizinler.
- `python -m compileall -q graphify tools tests` derleme denetimi.
- `tools/scan_untrusted_docs.py` güvenilmeyen-belge taraması.
- `pip._vendor.packaging.requirements.Requirement` ile `requirements.lock` satırlarının geçerli ve sabitlenmiş (==) olup olmadığı ve karma içerip içermediği denetimi.
- `graphify/security.py` URL doğrulama, SSRF engelleme, yol sınırlandırma modülünün incelenmesi.

Çalıştırılamayan denetimler (ortam kısıtlaması nedeniyle) ayrı olarak işaretlenmiştir (bkz. bölüm 6).

---

## 2. Statik bulgular ve düzeltmeler

Aşağıdaki riskler denetime konu olup, her biri denetlenmiş ve düzeltmiştir.

### 2.1 Fortran / C / C++ include taraması

**Bulgu:** Include dosyalarının gözetimsiz izlenmesi, yol kaçışına (path traversal) ve şablon dosyalarının dışarıya sızmasına neden olabilir.

**Uygulanan kontrol:**

- `graphify/extract.py` ve `graphify/extractors/resolution.py`: include yol çözümlemesi `resolve_within()` ile sınırlandırılır; mutlak yol (POSIX kökü, Windows sürücü, UNC) ve `..` bileşenleri reddedilir; ters bölü (`\`) ayırıcı olarak sayılır; sembolik bağlantılar çözümlenmeden önce kontrol edilir.
- `graphify/extractors/fortran.py`: yorum/splice/digraph/trigraph-bilimli include çıkarıcı; `cpp` arka önesi `-nostdinc`, boş geçici çalışma dizini, minimal ortam, `shell=False` ve çıktı sınırı ile kutuya alınmış şekilde çalıştırılır.

**Durum:** Düzeltildi, statik olarak denetlendi.

### 2.2 SSRF / RCE (`validate_url` / `safe_fetch`)

**Bulgu:** Yetkisiz sunucuya istek (Server-Side Request Forgery) ve yerel dosya erişimi (`file://`, `ftp://`, `data:`) riski.

**Uygulanan kontrol (`graphify/security.py`):**

- Yalnızca `http` ve `https` şemaları kabul edilir.
- Hostname normalizasyonu, IDN (punycode) reddetme, kontrol karakteri ve URL sınırlayıcısı kaçakçısı reddetme.
- Özel IP, loopback, link-local, çok yayın, ayrılmış, belirtilmemiş ve IPv4-eşlenik/6to4/Teredo/NAT64 adresleri açılıp engellenir (`not ip.is_global`).
- DNS bir kez çözümlenir ve çözümlenen adres bağlantıdan önce kontrol edilir (DNS yeniden bağlama/rebind TOCTOU koruması).
- Bulut meta verisi uç noktaları (`metadata.google.internal`, vb.) engellenir.
- Yönlendirmeler varsayılan olarak reddedilir (`allow_redirects=False`), sınırlı (max 5) ve her atlama yeniden doğrulanır.
- Toplam işlem süresi (deadline), okuma zaman aşımları ve yanıt boyutu sınırı (`Content-Length` erken engelleme).
- İsteğe bağlı `GRAPHIFY_ALLOWED_HOSTS` sunucu izin listesi.

**Durum:** Düzeltildi, statik olarak denetlendi.

### 2.3 Komut enjeksiyonu (`subprocess.*`, `os.system`, `eval`, `exec`)

**Bulgu:** Kabuk üzerinden çalıştırılan komutlar ve değerlendirme fonksiyonları.

**Uygulanan kontrol:**

- Çalışma zamanı paketinde `shell=True`, `os.system` veya `os.popen` yok.
- Alt süreçler argüman dizileriyle çalışır (`shell=False`), minimal ortamla ve sınırlı çıktıyla.
- `eval(` / `exec(` yok (tek bir yorum satırı hariç: `extractors/engine.py:6282`, bu bir PHP search-engine yorumu, çalıştırılabilir kod değil).

**Durum:** Temiz, statik olarak denetlendi.

### 2.4 Prompt enjeksiyonu (`SKILL.md` / YAML)

**Bulgu:** Skill dosyalarının ve YAML ön maddesinin talimat enjeksiyonu için kullanılması.

**Uygulanan kontrol:**

- Tüm `SKILL.md`/`*.skill`/YAML dosyaları veri olarak muamele edilir, talimat olarak değil.
- Uzaktan alınan metin `<untrusted_source>` işaretleyicileriyle sarmalanır.
- Üretilen HTML, kullanıcı kontrolündeki değerleri kaçırır (escape).
- `SKILL.md` kurulum blokları temizlendi; paket dizini veya üçüncü taraf kurulum ipuçları kaldırıldı; sponsor satırları çıkarıldı.
- `tools/scan_untrusted_docs.py` ile tarama: 0 bulgu.

**Durum:** Düzeltildi, tarama temiz.

### 2.5 Sabitlenmemiş bağımlılıklar / telemetri sızdırma

**Bulgu:** Sabitlenmemiş sürümler, karma eksikliği ve gizli telemetri.

**Uygulanan kontrol:**

- `pyproject.toml` çalışma zamanı, isteğe bağlı ve geliştirme bağımlılıklarını sabitler.
- `requirements.lock`: varsayılan kapanış için 35 sabitlenmiş dağıtım, her biri SHA-256 karma ile; `--require-hashes --no-deps` ile kurulur.
- Telemetri uç noktası yok, `requests.post` analitiği yok, otomatik yükleme yok.
- Sorgu günlüğü varsayılan olarak kapalı (opt-in).
- `GRAPHIFY_ALLOW_TIKTOKEN_DOWNLOAD=1` gerekli olmadan tokenizer indirilemez; yoksa yerel tahmine dönülür.

**Durum:** Düzeltildi, `requirements.lock` doğrulaması geçti (35 giriş, hepsi `==` ile sabitlenmiş ve karma ile).

### 2.6 CDN komut dosyaları (üretilen HTML)

**Bulgu:** `callflow_html.py` (mermaid) ve `tree_html.py` (d3) CDN'den yükleme yapıyor, SRI yok.

**Uygulanan kontrol:**

- `exporters/html.py` vis-network 9.1.6 zaten SRI ile (sha384).
- `callflow_html.py` mermaid@11.17.2 şimdi SRI ile (sha384).
- `tree_html.py` d3@7.9.0 şimdi SRI ile (sha384).
- HTML'ler çevrimdışı açılabilir veya komut dosyaları yerel olarak satışa sunulabilir (politika çakışması durumunda).

**Durum:** SRI eklendi; kalan risk belgeye not edildi (`SECURITY.md`).

---

## 3. Uygulanan kontroller özeti

| Kontrol | Dosya / konum | Durum |
| --- | --- | --- |
| Şema/host izin listesi (http/https) | `graphify/security.py` `validate_url` | ✅ |
| Özel IP / loopback / DNS rebind engelleme | `graphify/security.py` `_ip_is_blocked`, `_resolve_and_validate` | ✅ |
| Yönlendirme reddi (`allow_redirects=False`) | `graphify/security.py` `safe_fetch` | ✅ |
| Süre ve boyut sınırı | `graphify/security.py` `safe_fetch` | ✅ |
| Yol sınırlandırma (`resolve_within`) | `graphify/security.py` `resolve_within`, `validate_graph_path` | ✅ |
| `shell=False` alt süreç | `graphify/extractors/fortran.py` | ✅ |
| Sabitlenmiş, karma kilitli bağımlılıklar | `requirements.lock`, `pyproject.toml` | ✅ |
| Tiktoken indirme kapısı | `graphify/llm.py::_get_tokenizer` | ✅ |
| Telemetri / analiz yok | `graphify/` paketi | ✅ |
| Yerel skill kurulumu (manifest izli) | `tools/install_skills.py` | ✅ |
| HTML SRI (vis-network, mermaid, d3) | `graphify/exporters/html.py`, `callflow_html.py`, `tree_html.py` | ✅ |
| Konteyner önerileri (`--network none`, salt okunur, non-root) | `SECURITY.md` | ✅ |

---

## 4. Doğrulama komutları

Depo kökünden çalıştırılacaklar:

```powershell
python -m compileall -q graphify tools tests
python tools/install_skills.py --check --dest .
python tools/scan_untrusted_docs.py
```

Bağımlılık kapanışının şartlı olarak doğrulanması (çalışırsa):

```powershell
python -m pip install --require-hashes --no-deps -r requirements.lock
python -m pip install --no-deps -e .
```

Tam test takımı şunları gerektirir (şu ortamda yok):

```powershell
python -m pytest -q
```

---

## 5. Çalıştırılamayan denetimler (belirtilmemiş)

Aşağıdaki denetimler bu ortamda **çalıştırılamadı** ve "geçti" varsayılarak işaretlenmemiştir:

- Tam `pytest` testi: `pytest`, `networkx`, `tree_sitter` yüklü değil; Python 3.15.2 için sabit NumPy 1.26.4 tekerleği yok.
- `pip install -e .`: `setuptools` ve `wheel` eksik (kurulum adımı ayrı ayrı belgelenmiştir).
- `graphify.extractors` içe aktarımı: `tree_sitter` eksik olduğu için `graphify/extractors/__init__.py`'nin `erlang.py`'yı görevinden önce içe aktarması nedeniyle başarısız oluyor.
- CDN komut dosyalarının gerçek ağ üzerinden çalıştırılması: runtime ağ erişimi yok; SRI karma değerleri `cdn.jsdelivr.net` üzerinden indirilerek hesaplanmıştır (build ortamında).

Bu denetimlerin her biri, uygun bir ortamda (Python 3.10–3.13, `setuptools`/`wheel`/`pytest`/`networkx`/`tree_sitter` mevcut) yeniden çalıştırılmalı ve sonucu bu rapora eklenmelidir.

---

## 6. Kısıtlamalar

- `kodharitalama` bir sandbox değildir. Bilinmeyen depolar konteyner veya sanal makine üzerinde çalıştırılmalıdır.
- İsteğe bağlı LLM sağlayıcılarınızı girdiğiniz soruları alır; sağlayıcı politikasını inceleyin.
- Üst-proje uyumlu `graphify install` komutu kullanıcı/genel editör dizinlerine yazabilir. Proje yerel kurulum için `tools/install_skills.py --dest <proje>` tercih edilmelidir.
- Sürümdeki sabitlenmiş sürümler Python 3.10–3.13'i hedefler; Python 3.15'te tam kurulum beklenmez.

---

## 7. Sonuç

`kodharitalama` 0.30.103, belirtilen güvenlik risklerinin hepsinin statik olarak denetlenip düzeltildiği bir yerel, güvenlik sıkılaştırmalı kod bilgi haritası dağıtımıdır. Hiçbir değişiklik git'e itilmemiştir ve itilmeyecektir.

**İmza:** Murat ŞAHİN — Şahin Yazılım Evi  
**Tarih:** 04 Kasım 2026
