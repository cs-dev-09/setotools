# Material Maker

Tek bir diffuse görüntüsünden **Height**, **Normal** ve **Specular** haritası üreten
araç. Algoritmalar [Bounding Box Software'in Materialize](https://github.com/BoundingBoxSoftware/Materialize)
programından (GPL-3) portlanmıştır.

> Bu araç, [@gecu3d](https://github.com/gecu3d) tarafından **Velxor Materialize**
> adıyla bağımsız bir eklenti olarak yazıldı ve Void Tools'a olduğu gibi
> katıldı. Bu dosya o günden kalan geliştirici notlarıdır; kullanım rehberinin
> güncel hâli **<https://seto3d.github.io/void-tools/tools/material-maker/>**
> adresindedir.

## Kurulum

Ayrıca kurulum gerekmez: Void Tools'un içinde gelir. Eklentiyi kurmak için
[kurulum sayfasına](https://seto3d.github.io/void-tools/installation/) bak.

Panel: **3D Viewport > N tuşu > Void Tools > Materials > Material Maker**.

Bağımlılık yok — Blender'ın kendi NumPy'ı yeterli (scipy/PIL gerekmez).

Arayüz metinleri İngilizce, kod yorumları Türkçe.

### Haritaları önizleme

Her sekmedeki **görüntü** ikonu ve Output panelindeki **göz** ikonu haritayı
sahnenin yanında gösterir. Buton bir anahtar gibi çalışır:

| Durum | Basınca |
|---|---|
| Önizleme kapalı | 3D Viewport'u böler, **sol tarafta** Image Editor açar |
| Başka harita görünüyor | Kapatmaz, sadece o haritaya geçer |
| Aynı harita görünüyor | Önizlemeyi kapatır, viewport eski genişliğine döner |

Yeni pencere açmaz, mevcut yerleşimin içinde çalışır. Önizleme genişliği
viewport'un yaklaşık %28'i.

## Simple / Advanced

Panel iki modda çalışır. **Mod değiştirmek üretimi hiçbir şekilde etkilemez** —
sadece kaç kontrolün göründüğünü değiştirir; gizlenen ayarlar arka planda
aynen çalışmaya devam eder (test edilmiş: iki modun çıktısı bit düzeyinde
aynı).

**Simple** (varsayılan) — sonucu en çok değiştiren birkaç ayar:

| Sekme | Görünen |
|---|---|
| Height | Look preset'leri, Final Contrast, Final Bias, Normalize, Invert |
| Normal | Slope From, Strength, Look preset'leri, Final Contrast, Flip Y |
| Specular | Blur Size, Final Contrast, Final Bias, Channel Packing modu |

**Advanced** — her şey: frekans ekolayzerları, renk örnekleri, şekil tanıma,
açısallık, kanal başına paketleme ayarları, bit derinliği.

Her ayarın üstüne geldiğinde ne işe yaradığını anlatan bir açıklama çıkar —
78 ayarın tamamı ve enum seçeneklerinin hepsi açıklamalı.

## Sıfırlama

Ana paneldeki **↺** butonu Height, Normal ve Specular ayarlarının tamamını
varsayılanlarına döndürür ve üç haritayı sıfırdan üretir. Elle yapılan tüm
ayarlar gideceği için önce onay ister.

Sıfırlama `property_unset` kullanır, yani değerler elle yazılmaz — her ayar
kendi tanımındaki varsayılana döner. Kaynak görüntüye, export ayarlarına ve
materyal seçimine dokunmaz.

## İş akışı

1. Kaynak diffuse görüntüsünü seç. Yeni bir doku seçmek önceki haritaları
   temizler ve üçünü sıfırdan üretir — eski dokunun haritaları asla ekranda
   ya da materyalde kalmaz.
2. **Generate All** — ya da sekme sekme ilerle.
3. **Settings** panelinden parametreleri kur, **Generate**'e tekrar bas.
4. **Create / Update Material** ile node ağacına bağla (Principled BSDF ya da
   Sollumz shader — aşağıya bak).
5. **Export** panelinden PNG / JPG / TGA / EXR olarak kaydet.

## Materyal kurulumu

Output panelindeki **Material Type** iki mod sunar.

### Principled BSDF

Standart Blender PBR materyali: diffuse → Base Color, normal → Normal Map,
specular → invert → Roughness, height → Displacement.

### Sollumz Shader (GTA V)

Sollumz kuruluysa gerçek bir GTA V shader materyali kurar — `create_shader()`
ile, `sollum_type`, `shader_properties.filename` ve render bucket doğru
şekilde ayarlanmış olarak. Haritalar sampler'lara otomatik yerleşir:

| Sampler | Harita | Colorspace |
|---|---|---|
| `DiffuseSampler` | kaynak diffuse | sRGB |
| `BumpSampler` | üretilen normal | Non-Color (`is_data`) |
| `SpecSampler` | üretilen specular | Non-Color (`is_data`) |
| `heightSampler` | üretilen height | Non-Color — *sadece pxm/parallax varyantlarında* |

Specular `Channels = Packed (GTA)` ise `specMapIntMask` parametresi de
`(1, 0, 0)` olarak ayarlanır.

Varsayılan shader **`normal_spec.sps`**. Dropdown, Sollumz'un shader
veritabanındaki bu üç sampler'ı taşıyan **100 shader'ın** tamamını listeler
(`normal_spec_alpha`, `_cutout`, `_decal`, `_pxm`, `cloth_normal_spec` …).
Seçilen shader'da olmayan sampler panelde gösterilmez.

Aynı add-on Sollumz kurulu olmadan da çalışır — o modda buton kapalı kalır ve
panel neden kapalı olduğunu söyler. Sollumz'u oturum ortasında etkinleştirirsen
Material Type'ı değiştirmen listeyi tazeler.

Materyal yerinde güncellenir: tekrar bastığında yeni materyal yaratılmaz,
nesnenin materyal slotları bozulmaz, shader'ı değiştirsen bile atama korunur.

Üç harita da varsayılan olarak **doğrudan diffuse'tan** üretilir:

```
Diffuse ─┬─→ Height
         ├─→ Normal      (Slope From = Diffuse, varsayılan)
         └─→ Specular
```

Normal sekmesindeki **Slope From** seçicisiyle eğimin nereden okunacağını
belirlersin:

- **Diffuse** (varsayılan) — eğim doğrudan kaynak diffuse'un luminance'ından
  okunur. Height boru hattının frekans şekillendirmesinden bağımsızdır, yani
  height'ın yuttuğu ince detay normal'de korunur. Ölçüm: aynı dokuda yüksek
  frekans enerjisi height kaynağına göre **1.38 kat** fazla.
- **Height Map** — Materialize'ın yaptığı: eğim üretilen height haritasından
  okunur. Height'ın frekans şekillendirmesini normal'in de takip etmesini
  istediğinde kullan.

`Slope From = Diffuse` iken Normal üretmek Height'a hiç ihtiyaç duymaz ve
Height'ı boşuna hesaplamaz.

## Parametreler

### Height (Diffuse'dan)

Luminance'ın **7 kademeli blur piramidi** kurulur. Kademeler doğrudan
ortalanmaz: her biri ortak bir **çok geniş ortalamadan** çıkarılıp yüksek
geçirgen banda çevrilir, kontrast o bandı ölçekler. Kontrastın negatif
olabilmesinin sebebi budur — o frekans bandını ters çevirir, `Cracks` ve
`Funky` preset'leri tam olarak bunu yapar.

Varsayılanlar Materialize'ın kendi değerleri:
ağırlıklar `0.15 / 0.19 / 0.30 / 0.50 / 0.70 / 0.90 / 1.00`,
kontrastlar hepsi `1.0`, Final Contrast `1.5`, Final Gain `0.0`.

**Preset'ler:** ağırlık için `Default / Details / Displace`,
kontrast için `Default / Cracks / Funky` — Materialize'ın butonlarıyla
birebir aynı değerler.

`Final Gain` bir S-eğrisidir: negatif orta tonları sertleştirir, pozitif
yumuşatır, 0 nötrdür.

#### Blur piramidi kademeleri

Panelde her kademe numarayla değil, **taşıdığı ölçekle** adlandırılır ve
yanında o kademenin bu görüntü için geçerli **etkin yarıçapı** yazar:

| Kademe | Ne taşır | 1024² için |
|---|---|---|
| Pixel Detail | Ham piksel detayı: grain, çizik, gözenek. Yükselt = keskinlik, alçalt = gürültü temizliği | 1 px |
| Fine Grain | Piksel üstü ince yüzey dokusu | ~1 px |
| Small Detail | Küçük öğeler: derz çizgileri, perçin, ince çatlak | ~2 px |
| Medium Form | Orta ölçekli şekiller: tek tuğla, tahta, taş | ~5 px |
| Large Form | Büyük şekiller: öğe grupları, panel bölünmeleri | ~9 px |
| Broad Shape | Doku boyunca geniş dalgalanma | ~18 px |
| Overall Shape | Görüntünün genel açık-koyu gradyanı. Yükselt = kubbeleşme, alçalt = düz yüzey | ~37 px |

Yarıçaplar görüntü boyutuyla otomatik ölçeklenir, yani aynı doku 512'de de
4K'da da aynı görünür. `Blur Scale` hepsini birden çarpar.

Settings altındaki **What the levels do** paneli bu tabloyu Blender içinde,
o anki görüntünün gerçek yarıçaplarıyla gösterir.

| Parametre | İşlevi |
|---|---|
| Pre Contrast | Blur zincirinden önce luminance'a uygulanır |
| Blur Weights (0–6) | Her kademenin sonuca katkısı. **Asıl kalite kolu burası** |
| Blur Contrasts (1–6) | Kademe başına şekil vurgusu |
| Blur Scale | Tüm kademeleri birlikte ölçekler |
| Normalize Range | Sonucu 0..1'e gerdirir (aykırı piksellere dayanıklı, %0.5–%99.5 aralığı) |
| Final Contrast / Bias / Gain | Normalize'dan **sonra** uygulanan son rötuş |
| Color Samples (2 adet) | Seçilen renge yakın bölgeleri sabit bir yüksekliğe çeker |

**Color Sample** tuğla/derz, fayans/derz gibi dokularda belirleyici. Örnekler
`Blit_Sample.shader` portudur ve **blur zincirinden önce** uygulanır — yani
frekans merdiveninin girdisini değiştirirler.

Maske HSL uzayında, kanal başına yakınlık hesaplanıp ağırlıklara bölünerek
kurulur. `Isolate` bir **önizleme kipidir**: yükseklik yerine maskenin kendisini
gösterir, böylece ne seçtiğini görürsün.

Materialize'ın varsayılan maske aralığı (`Mask Low = 0`, `Mask High = 1`)
kasten çok geniştir ve pratikte her şeyi seçer. Gerçek kullanım: derz rengini
seç, `Isolate`'i aç, `Mask Low`'u maske temizlenene kadar yükselt, `Isolate`'i
kapat, `Height = 0` ver.

> **Not:** `Normalize Range` açıkken örneğin derinlik etkisi büyük ölçüde geri
> alınır (yüzdelik gerdirme tam da o genlik değişimini normalize eder). Panel
> bunu uyarır; örneğin tam etkisini görmek için Normalize Range'i kapat.

### Normal (Height'tan)

İleri fark türevinden cross product ile taban normal üretilir, sonra aynı
7 kademeli piramitten geçip yeniden normalize edilir.

Eğim komşu piksel farkından hesaplandığı için ham haliyle çözünürlüğe
bağımlıdır: aynı doku 2048'de 1024'e göre yarısı kadar piksel-başı eğim
üretir ve normal düz görünür. Bu yüzden eğim, blur yarıçapları gibi 1024
referansına göre ölçeklenir — **Processing Size'ı değiştirmek normal'in
gücünü değiştirmez.**

Varsayılanlar Materialize'ın kendi değerleri: Pre Contrast (**Strength**) `20`,
Final Contrast `5`, ağırlıklar `0.30 / 0.35 / 0.50 / 0.80 / 1.00 / 0.95 / 0.80`
(dikkat: **artan** — geniş form ağır basar), Slope Blur `50`.
**Preset'ler:** `Default / Smooth / Crisp / Mids`.

| Parametre | İşlevi |
|---|---|
| Strength | Eğim çarpanı (Materialize'daki "Pre Contrast"). **Normal düz görünüyorsa yükseltilecek ayar bu.** |
| Frequency Weights | Yüksek kademeler geniş yüzey eğimini taşır |
| Final Contrast | Tüm normal'i dikleştirir: XY'yi ölçekler, Z'yi kuvvet alır. 1.0 nötr, 0 tamamen düz |
| Flip Y | Kapalı: OpenGL / Blender / GTA. Açık: DirectX / Unity |

#### Shape Recognition

Türev tabanlı normal yalnızca komşu piksel farkını görür — bu yüzden tuğla
gibi geniş düz yüzeyler boş çıkar, sadece derz kenarları belirir. Shape
Recognition, height'ın yüksek geçirgen bandını bir **ışık yönü** boyunca eğim
olarak yorumlayıp yüzeylere gerçek hacim kazandırır.

| Parametre | İşlevi |
|---|---|
| Shape Recognition | Katmanın gücü. 0 = kapalı |
| Slope Blur | Ne kadar geniş bir şeyin "şekil" sayılacağı. Düşük = küçük detay, yüksek = büyük form |
| Shape Bias | Neyin çıkıntı, neyin çukur sayılacağını kaydırır. 0.5 nötr |
| Light Rotation | Şeklin hangi yönden aydınlatıldığı |
| Read Shapes From Diffuse | Şekilleri height yerine kaynak diffuse'tan okur — height'ın kaybettiği detay diffuse'ta duruyorsa |

Ölçüm: tuğla yüzlerinde eğim gücü `Shape Recognition = 0.8` ile
0.0500'den **0.1191'e** çıkıyor, yani boş yüzeyler dolduruluyor.

#### Angularity

Belirgin eğimi olan her pikseli **tek bir dikliğe** kilitler; yumuşak
geçişler yerine fasetli, sert kırılımlı bir yüzey verir. Taş duvar ve metal
panel gibi yüzeylerde işe yarar. `Angular Intensity` kilitlenen açıyı belirler
(0.5 → eğim 0.707, 0.8 → 0.970). Tam düz pikseller düz kalır.

### Specular (Diffuse'dan)

`fragCombineRoughSpec` (pass 10) portu. Zincir:

1. Diffuse'a contrast / bias
2. **Parlama ve gölge düzleştirme** — `maxLum` üzerinde `smoothstep` **eşikleri**.
   `Highlight Threshold`'un üstündeki ve `Shadow Threshold`'un altındaki
   pikseller blur'a doğru karıştırılır, yani dokuya pişmiş aydınlatma silinir.
3. Blur'a kendi kontrastı, sonra **Vivid Light** karışımı — asıl yüksek
   geçirgen mekanizma budur, çıkarma değil.
4. Final contrast / bias, sonra gri tona indirgeme.

`Keep Color` ve `Saturation` Materialize'ın bu pass'inde okunmaz (çıktı her
zaman gridir); renkli GTA specular'ı için ek olarak duruyorlar ve
varsayılanları nötr olduğundan temel davranış birebir aynıdır.

#### Kanal Paketleme (GTA)

GTA'nın spec dokusu tek bir gri harita olmak zorunda değil — RGB'ye **üç ayrı
veri** paketlenir ve shader hangisini okuyacağını `specMapIntMask` ile seçer.
Gerçek GTA dokularından ölçtüğüm külliyatta **18 spec haritasının 11'i paketli**.

`Channels` seçicisi iki mod sunar:

- **Grayscale** (varsayılan) — tek değer üç kanala kopyalanır. Külliyatın %39'u
  böyle, `deri_s` dahil.
- **Packed (GTA)** — R = yoğunluk, G = falloff, B = fresnel.

Ölçülen gerçek düzen (`tl_dlc_vw_casino_details_03_s.dds`):

| Kanal | Ortalama | Std | Detay | Karakter |
|---|---|---|---|---|
| R — Intensity | 0.584 | 0.136 | yüksek | en detaylı maske |
| G — Falloff | 0.797 | 0.027 | orta | daha yumuşak, dar aralık |
| B — Fresnel | 0.923 | 0.013 | düşük | neredeyse düz, en parlak |

R doğrudan specular çıktısıdır. G ve B aynı sinyalden türetilir; her biri için
**Level** (sonucun ortalaması, doğrudan ayarlanır), **Variation** (ne kadar
değişim taşır) ve **Softness** (yumuşaklık) vardır.

`Invert Fresnel`, bazı GTA dokularında görülen "B = R'nin tam tersi" düzenini
üretir (`CV_Interior_s.dds`'te R-B korelasyonu ölçülen değer: **−1.000**).

Paketli modda `Create / Update Material`, Sollumz materyalindeki
`specMapIntMask` parametresini **(1, 0, 0)** yapar — yani shader'a yoğunluğu
R kanalından okumasını söyler.

> Kuantalanmış palet haritaları (`CV_Interior_s` kanal başına 2 seviye,
> `Micropulse` 6–8 seviye) hedeflenmez: bunlar spec değil **malzeme kimliği**
> haritalarıdır, elle yazılır ve türetilemezler.

## Ayarlar

- **Tileable Edges** — blur ve türev işlemlerinde kenarlar karşı tarafa
  sarılır. Seamless doku üretiyorsan açık bırak; değilse kapat, kenarlar
  tekrarlanarak doldurulur.
- **Processing Size** — Full / Half / Quarter. Bunlar **bölen**dir, mutlak
  piksel sınırı değil: Half her zaman yarısı, Quarter her zaman çeyreği.
  Görünüm sabit kalır (ölçüldü: 2048 kaynakta sapma 1.08x), yalnızca hız
  değişir — işlenen boyut 512 px civarı ve üstünde kaldığı sürece. Altına
  inince ince detay gerçekten kaybolmaya başlar.
- **Auto Update** — varsayılan **açık**. Ayarı değiştirdiğin anda haritaları
  yeniden kurar. Büyük dokularda Processing Size'ı Half veya Quarter'a al;
  panel işlenen boyut 2048'i aşarken bunu ayrıca hatırlatır.

## Export renk uzayı — "gördüğümle aynı çıkmıyor"

Export **hiçbir renk dönüşümü uygulamaz**: dosyaya yazılan değerler
datablock'takilerle birebir aynıdır (ölçülen sapma 0.0000, tüm formatlarda).

Sorun dosyayı **geri okurken** çıkar. PNG ve TGA renk uzayı bilgisi taşımaz,
ve hem Blender hem sıradan görüntü programları bu dosyaları sRGB varsayar.
Ham veri içeren bir dosya sRGB sanılarak açılırsa değerler kayar — ölçülen
sapma: height 0.089, normal 0.191, specular 0.175.

Bu yüzden Export panelinde **Written As** seçeneği var:

| Mod | Dosyadaki bayt | Doğru okuma | Ne zaman |
|---|---|---|---|
| **Raw data** (varsayılan) | harita değerinin kendisi | Non-Color | Oyun motoru, Sollumz, CodeWalker |
| **sRGB encoded** | sRGB kodlanmış | sRGB (Blender'ın varsayılanı) | Dosyayı görüntü programında ya da normal PNG olarak açacaksan |

Her iki mod da kendi yorumu altında **birebir** turlanıyor (ölçülen sapma
0.0000). Yanlış yorumla açarsan yukarıdaki sapmaları görürsün.

Kısaca: haritayı Blender'a geri alırken **görüntüyü Non-Color yap** (Raw data
modunda), ya da export'u sRGB encoded moduna çevir. EXR zaten float veri
formatı olduğu için bu seçenek ona uygulanmaz.

## Yenileme ve kalıcılık

Piksel verisini değiştirmek Blender'ı kendiliğinden yeniden çizdirmez, ayrıca
materyal önizlemesi dokunun GPU kopyasını ayrıca önbelleğe alır. Üretim
sonrasında her iki önbellek de temizlenir (`gl_free()` + ilgili alanlara
`tag_redraw()`), yani sonuç Image Editor'de de, rendered viewport'ta da anında
görünür.

Üretilen görüntüler her üretimde **paketlenir** (`image.pack()`). Bu yalnızca
`.blend` kalıcılığı için değil, veri bütünlüğü için de zorunlu:

> Blender'da `GENERATED` kaynaklı bir görüntüde `colorspace_settings`'e
> dokunmak tamponu geçersiz kılar ve görüntü `generated_width/height`'tan
> **boş** olarak yeniden üretilir — yani piksel verisi silinir. Materyal
> kurarken node'lara colorspace atandığı için paketlenmemiş haritalar bu
> noktada sıfırlanır. Paketlenmiş (FILE) görüntüde aynı işlem veriyi
> paketten geri çözer ve veri korunur.

Maliyeti 4K'da harita başına ~0.19 sn, yani üretimin yanında ihmal edilebilir.
Ayrıca kod artık colorspace'e yalnızca gerçekten değişmesi gerektiğinde
dokunuyor.

### Etkisiz görünen ayarlar

Bazı slider'lar ön koşulları sağlanmadan matematiksel olarak hiçbir şey
yapamaz; bunlar arayüzde kilitli gösterilir:

| Ayar | Koşul |
|---|---|
| Specular > Saturation | `Keep Color` 0'ın üzerinde olmalı — tamamen gri specular'ın değiştirilecek doygunluğu yoktur |
| Height > Blur Contrast, seviye 0 | Seviye 0 bulanıklaştırılmaz, kontrastı da yoktur |
| Color Sample > Spread Boost | `Spread` 0'ın üzerinde olmalı |

## Performans

Ryzen sınıfı bir CPU'da, üç haritanın tamamı:

| Çözünürlük | Süre |
|---|---|
| 512² | 0.08 sn |
| 1024² | 0.43 sn |
| 2048² | 1.7 sn |
| 4096² | 8.2 sn |

## Neden GPU değil de NumPy

Blender'ın `gpu` modülünde ham GLSL yalnızca OpenGL backend'inde çalışır ve
Blender Vulkan/Metal'e kayıyor — shader yolu kırılgan olurdu. Piramit
hızlandırmalı gaussian ile CPU yolu her backend'de aynı sonucu veriyor ve
hiçbir harici bağımlılık gerektirmiyor.

Blur zinciri kademeli olarak küçültülmüş çözünürlükte taşınır ve seviyeler
kendi kademelerinde toplanıp en sonda **tek bir** büyütme zinciriyle
birleştirilir. Naif (tam çözünürlükte, seviyeler bellekte) uygulamaya göre
sapma ≤ 0.0003, bellek kullanımı 4K normal map'te ~1.4 GB yerine sabit.

## Materialize'dan henüz portlanmayanlar

### Birebir portlananlar

| Materialize | Bizdeki karşılığı |
|---|---|
| `fragCombineHeight` (pass 2) | `generators.height_from_diffuse` |
| `fragNormal` (pass 3) | `_height_to_normal` + `_apply_shape_recognition` |
| `fragCombineNormal` (pass 4) | `normal_map` birleştirme + `_apply_angularity` |
| `fragCombineRoughSpec` (pass 10) | `specular_from_diffuse` |
| `Blit_Sample.shader` / `fragSample` | `_apply_samples` + `imageops.color_mask` |
| `Photoshop.cginc` / `BlendVividLightf` | `generators._vivid_light` |
| `fragBlur` (Hann, `_BlurSamples`) | `imageops.blur` + `HANN_SIGMA_PER_SPREAD` |

Tüm varsayılanlar ve altı preset kaynak koddan birebir alındı.
(`Blit_Normal_From_Height.shader` ve `Blit_Height_From_Diffuse.shader` depoda
duruyor ama GUI onları kullanmıyor — eski sürümler.)

### Portlanmayanlar

AO, Edge, Metallic, Smoothness sekmeleri; Edit Diffuse sekmesi (`fragEditDiffuse`,
pass 11); Tiling Texture Maker; Normal → Height dönüşümü; Height sekmesindeki
`Diffuse / Original Diffuse / Normal` kaynak seçicisi (bizde her zaman
Original Diffuse).

### Bilinçli farklarımız

| Ek | Neden |
|---|---|
| `Normalize Range` | Materialize'da canlı önizlemeye bakıp Final Contrast'ı elle çevirirsin; bizde buton tabanlı akışta harita dar bir banda sıkışıp düz kalıyordu |
| Normal `Slope From: Diffuse` | Materialize yalnızca şekil tanımayı diffuse'tan besleyebiliyor; eğimin de diffuse'tan gelmesi ince detayı koruyor |
| Çözünürlük normalizasyonu | Materialize kaynak çözünürlüğünde çalışır; bizde Processing Size olduğu için tüm yarıçaplar ve eğim 1024 referansına bağlandı |
| Aykırı pikselden korunma | Ham min/max yerine %0.5–%99.5 yüzdelikleri |
| Specular `Keep Color` / `Saturation` | GTA specular'ı renkli olabiliyor; varsayılanları nötr |
| Color Sample `Spread` | Maskeyi yumuşatmak için; varsayılanı 0 (kapalı) |

## Lisans

GPL-3.0-or-later. Materialize (Bounding Box Software) da GPL-3'tür.

## Dosya düzeni

    imageops.py     saf numpy: blur piramidi, kontrast remap, HSL renk maskesi
    imageio.py      bpy.types.Image <-> numpy köprüsü, renk uzayı çevrimi
    generators.py   üç dönüşüm, bpy'den bağımsız (test edilebilir)
    sollumz_link.py Sollumz shader köprüsü (opsiyonel bağımlılık)
    properties.py   PropertyGroup'lar (scene.vmat)
    operators.py    üretim, materyal kurulumu, export
    ui.py           3D Viewport N-Panel
