# kodharitalama

**Claude Code**, **OpenCode** ve **Antigravity IDE** için yerel, güvenlik
sıkılaştırmalı kod bilgi haritası.

**Marka:** Şahin Yazılım Evi · **Geliştirici:** Murat ŞAHİN · **Sürüm:** 0.30.103

> `kodharitalama`, Graphify projesinden uyarlanmıştır. Üst projenin telif ve lisans bildirimleri korunmuştur. Güvenlik açıkları giderilerek revize edilmiştir.Bkz. [`NOTICE`](NOTICE),
> [`REFERENCES.md`](REFERENCES.md) ve [`LICENSE`](LICENSE).
>
> Python içe aktarma paketi `graphify` adını korur; tarihsel `graphify` komutu
> da takma ad olarak tutulur. Birincil komut `kodharitalama`'dır.

---
 
## Ne yapar

`kodharitalama`, bir kaynak kod, belge, makale, görsel veya video klasörünü
kalıcı ve sorgulanabilir bir bilgi haritasına dönüştürür:

- **god node**'lar ve topluluk yapısı;
- dosyalar arası ilişkiler ve mimari özetleri;
- etkileşimli HTML, GraphRAG'e hazır JSON ve `GRAPH_REPORT.md`;
- isteğe bağlı wiki, GraphML, SVG, Neo4j, FalkorDB, MCP ve izleme modları.

Kodlama ajanları için önemli olan kısım erişimdir: ajan büyük bir depoyu
`grep` ile taramak yerine kapsamlı bir soru sorar ve küçük bir alt grafik alır.

```text
kodharitalama .                       # geçerli klasör için harita oluştur
kodharitalama query "auth flow"       # kapsamlı soru sor
kodharitalama explain "TokenCache"    # tek bir kavramı incele
kodharitalama path "A" "B"            # ilişki bul
kodharitalama update .                # yalnızca AST ile artımlı yenileme
kodharitalama --help                  # tam komut listesi
```

Çıktı, üst araç ve mevcut entegrasyonlarla uyumluluk için `graphify-out/`
klasörüne yazılır.

---

## Güvenlik duruşu

Bu yapı bilinçli olarak temkinlidir:

- **Telemetri yok** ve otomatik yükleme yok.
- **Dinamik üçüncü taraf skill kurulumu yok.** Skill'ler bu depoda gelir.
- **Varsayılan olarak reddeden URL getirme**; şema/sunucu denetimleri,
  özel IP ve DNS yeniden bağlama koruması, varsayılan olarak yönlendirme
  yok, süre ve boyut sınırları.
- Include taraması ve üretilen yollar için **yol sınırlandırma**.
- Çalışma zamanı paketinde **`shell=True`, `os.system` veya `os.popen` yok**;
  alt süreçler argüman dizileriyle çalışır.
- **Güvenilmeyen belgeler veridir**, talimat değildir.
- **Sabitlenmiş bağımlılıklar** ve karma kilitli varsayılan kapanış.
- `tools/install_skills.py` ile **proje yerel, manifest izli IDE kurulumu**.

Aracı güvenilmeyen kod üzerinde çalıştırmadan önce [`SECURITY.md`](SECURITY.md)
dosyasını okuyun. Araç bir sandbox değildir; bilinmeyen depolar için konteyner
veya sanal makine kullanın.

---

## Gereksinimler

| Gereksinim | Notlar |
| --- | --- |
| Python | 3.10–3.13 önerilir. Python 3.15'te sabitlenmiş NumPy 1.26.4 satırı için tekerlek yok. |
| İşletim sistemi | Windows 10/11, macOS, Linux |
| Disk | Varsayılan bağımlılık kapanışı için birkaç yüz MB |
| Ağ | Yalnızca ilk bağımlılık kurulumu için; çalışma zamanı getirmesi isteğe bağlı |

Tam çalışma zamanı `networkx`, `numpy`, `rapidfuzz`, `PyYAML` ve tree-sitter
dil bilgilerini gerektirir. `pytest` yalnızca test takımı için gereklidir.

---

## Bu depodan hızlı başlangıç

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --require-hashes --no-deps -r requirements.lock
python -m pip install setuptools==84.2.1 wheel==0.48.0
python -m pip install --no-build-isolation --no-deps -e .
kodharitalama --help
```

### macOS / Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --require-hashes --no-deps -r requirements.lock
python -m pip install setuptools==84.2.1 wheel==0.48.0
python -m pip install --no-build-isolation --no-deps -e .
kodharitalama --help
```

> `requirements.lock` yalnızca varsayılan çalışma zamanı kapanışını kapsar.
> İsteğe bağlı ekler (`mcp`, `neo4j`, `falkordb` ve büyük dil paketleri) ayrı
> çözülür. Etkinleştirmeden önce inceleyin.
>
> Bir paket dizininden **`graphifyy` kurmayın**. Desteklenen kaynak bu depodur.

Projeyi kurmadan da bağımlılıkları yükledikten sonra depodan çalıştırabilirsiniz:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m graphify --help
```

---

## IDE entegrasyonu

Kurucu yalnızca proje yerel dosyalar yazar. Hiçbir şey indirmez ve `--dest`
dışına yazmaz.

### Üç IDE için tek komut

```powershell
python tools\install_skills.py --ide all --dest .
```

```bash
python3 tools/install_skills.py --ide all --dest .
```

Başka bir projeye kurmak için `--dest C:\path\to\another-project` kullanın.
Planlanan yazmaları görmek için önce `--dry-run` kullanın.

### IDE başına komutlar

| IDE | Komut | Skill konumu | Her zaman açık talimatlar |
| --- | --- | --- | --- |
| Claude Code | `python tools/install_skills.py --ide claude-code --dest .` | `.claude/skills/kodharitalama/SKILL.md` | `.claude/CLAUDE.md` |
| OpenCode | `python tools/install_skills.py --ide opencode --dest .` | `.opencode/skills/kodharitalama/SKILL.md` | `AGENTS.md` |
| Antigravity IDE | `python tools/install_skills.py --ide antigravity --dest .` | `.agents/skills/kodharitalama/SKILL.md` | `.agents/rules/kodharitalama.md`, `.agents/workflows/kodharitalama.md` |

Her skill, `references/` yan dosyalarıyla birlikte kurulur. Kurucu skill ön
maddesini `name: kodharitalama` olarak yeniden yazar; gövde uyumlu `graphify`
komut örneklerini korur ve iki komut adı da çalışır.

### Kurulu düzen

```text
my-project/
├─ .claude/
│  ├─ CLAUDE.md                          # işaretli kodharitalama bölümü
│  └─ skills/kodharitalama/
│     ├─ SKILL.md
│     └─ references/*.md
├─ .opencode/
│  └─ skills/kodharitalama/
│     ├─ SKILL.md
│     └─ references/*.md
├─ .agents/
│  ├─ rules/kodharitalama.md             # Antigravity her zaman açık kuralı
│  ├─ workflows/kodharitalama.md
│  └─ skills/kodharitalama/
│     ├─ SKILL.md
│     └─ references/*.md
├─ AGENTS.md                             # işaretli kodharitalama bölümü
└─ .kodharitalama/
   └─ skills-manifest.json               # kurulan dosyalar ve SHA-256 karmaları
```

`tools/install_skills.py` idempotenttir. Depoyu güncelledikten sonra skill'leri
tazelemek için yeniden çalıştırın.

### Doğrula, güncelle, kaldır

```powershell
python tools\install_skills.py --check --dest .       # paketlenmiş kaynaklarla karşılaştır
python tools\install_skills.py --ide all --dest .     # tazele
python tools\install_skills.py --uninstall --ide all --dest .   # yalnızca yönetilen dosyaları kaldır
```

Kurucu, `--force` verilmedikçe yönetilmeyen veya yerel olarak değiştirilmiş
dosyaların üzerine yazmayı reddeder. `--uninstall` yalnızca manifestte kayıtlı
yolları kaldırır ve `AGENTS.md` ile `.claude/CLAUDE.md` içindeki kullanıcı
içeriğini korur.

### İsteğe bağlı MCP yapılandırması

Skill'ler CLI üzerinden çalışır. MCP tercih ediyorsanız, üretilen haritayı
işaret eden bir sunucu girdisi ekleyin:

**Claude Code** (`.mcp.json`):

```json
{
  "mcpServers": {
    "kodharitalama": {
      "command": "python",
      "args": ["-m", "graphify.serve", "graphify-out/graph.json"]
    }
  }
}
```

**OpenCode** (`opencode.json`):

```json
{
  "mcp": {
    "kodharitalama": {
      "type": "local",
      "command": ["python", "-m", "graphify.serve", "graphify-out/graph.json"],
      "enabled": true
    }
  }
}
```

**Antigravity** (`~/.gemini/antigravity/mcp_config.json`):

```json
{
  "mcpServers": {
    "kodharitalama": {
      "command": "python",
      "args": ["-m", "graphify.serve", "${workspace.path}/graphify-out/graph.json"]
    }
  }
}
```

MCP isteğe bağlıdır. Sunucuyu proje haritasına bağlı tutun ve kimlik doğrulama
eklemedikçe bir ağ arayüzünde açığa çıkarmayın.

---

## Kullanım notları

- Harita, girdi kadar iyidir. Depo kökünde `kodharitalama .` ile başlayın.
- `--update` yalnızca AST kullanır ve LLM çağırmaz.
- `--mode deep` daha zengin çıkarımsal kenarlar üretir ve daha yavaştır.
- `--watch` dosyalar değişirken haritayı güncel tutar.
- `--mcp` haritayı stdio üzerinden sunar.
- `--wiki`, `graphify-out/wiki/` altında ajanların tarayabileceği bir wiki üretir.
- `--no-viz`, yalnızca JSON ve rapor gerektiğinde HTML'i atlar.

Paketlenmiş skill'ler Obsidian, Neo4j, FalkorDB, GraphML, SVG, transkripsiyon ve
depolar arası haritalar dahil tam komut yüzeyini açıklar. Bir modu ilk kez
kullanmadan önce kurulu `SKILL.md` dosyasını okuyun.

---

## Depo düzeni

```text
kodharitalama/
├─ graphify/                      # içe aktarma paketi, CLI, çıkarıcılar, dışa aktarıcılar, skill'ler
├─ integrations/
│  ├─ claude-code/CLAUDE.section.md
│  ├─ opencode/AGENTS.section.md
│  └─ antigravity/{rules.md,workflow.md}
├─ tools/
│  ├─ install_skills.py           # proje yerel IDE kurucusu
│  ├─ generate_requirements_lock.py
│  └─ scan_untrusted_docs.py
├─ tests/                         # güvenlik, include çözümleme, kurucu testleri
├─ docs/                          # denetim ve işletim notları
├─ requirements.lock              # karma kilitli varsayılan bağımlılık kapanışı
├─ pyproject.toml
├─ SECURITY.md
├─ AGENTS.md
├─ REFERENCES.md
├─ Açıklama.md                    # bu README'nin Türkçe açıklaması
└─ README.md
```

---

## Doğrulama

Bunları depo kökünden çalıştırın:

```powershell
python -m compileall -q graphify tools tests
python tools/install_skills.py --check --dest .
python tools/scan_untrusted_docs.py
```

Tam test takımı ayrıca `pytest`, `networkx` ve tree-sitter dil bilgilerini
gerektirir:

```powershell
python -m pytest -q
```

Bir bağımlılık yoksa, atlanan denetimi geçti varsaymak yerine kaydedin.
[`docs/DENETIM_RAPORU_TR.md`](docs/DENETIM_RAPORU_TR.md) dosyasındaki denetim
raporu, statik olarak doğrulananları ve derleme ortamında çalıştırılamayanları
listeler.

---

## Sorun giderme

| Belirti | Neden ve çözüm |
| --- | --- |
| `pip` NumPy tekerleği bulamıyor | Python 3.14/3.15 kullanıyorsunuz. Python 3.12 veya 3.13 kullanın. |
| `ModuleNotFoundError: networkx` | Çalışma zamanı kapanışı kurulmadı. `requirements.lock` adımını çalıştırın. |
| `ModuleNotFoundError: tree_sitter` | Bir dil bilgisi veya çalışma zamanı eksik. Varsayılan kapanışı yeniden kurun. |
| `kodharitalama` tanınmıyor | Düzenlenebilir kurulum çalışmadı. `python -m graphify` kullanın veya yeniden kurun. |
| Skill IDE'de listelenmiyor | Yukarıdaki tablodaki yolu denetleyin ve IDE'yi yeniden başlatın. |
| `--check` sapma bildiriyor | Kurulumdan sonra depo değişti. Kurucuyu yeniden çalıştırın. |
| Kurucu üzerine yazmayı reddediyor | Dosya yönetilmiyor veya düzenlenmiş. İnceleyin, uygunsa `--force` kullanın. |

---

## Lisans ve atıf

- Apache License 2.0: [`LICENSE`](LICENSE)
- MIT lisanslı bölümler: [`LICENSE-MIT`](LICENSE-MIT)
- Üst proje ve uyarlama bildirimi: [`NOTICE`](NOTICE)
- Üst proje ve entegrasyon referansları: [`REFERENCES.md`](REFERENCES.md)

Üst proje Graphify: <https://github.com/Graphify-Labs/graphify>.
Üst proje bu dağıtımı sürdürmez, desteklemez veya onaylamaz.
