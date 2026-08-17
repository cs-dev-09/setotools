# Smooth Edge — Feedback & Update Log

Bu dosya Smooth Edge'in güncelleme defteri. Gelen feedback/fikirler buraya
düşülür, uygulananlar aşağı taşınır. (Geliştirme dili Türkçe, kullanıcıya görünen
metin İngilizce.)

## Açık — Feedback / Fikir

_(henüz yok — buraya eklenecek)_

Format:
```
### [TARİH] Başlık
**Kaynak:** kim/nereden
**İstek:** ne isteniyor
**Durum:** açık / inceleniyor / reddedildi (gerekçe)
```

## Uygulandı

_(henüz yok)_

## Mevcut durum (10 Ağu 2026 itibarıyla)

Modül: `void_tools/smooth_edge/` — `geometry.py`, `operators.py`,
`properties.py`, `object_settings.py`, `textures.py`, `ui.py`.

Ayarlar (üç yerde paylaşılıyor: Scene defaults, operatör F9 paneli, obje üstü
canlı ayarlar — `settings_annotations()`):
`width`, `surface_offset`, `merge_distance`, `alpha_center`, `alpha_outer`,
`invert_fade`, `color_rgb`, `flip_direction`, `material_mode`.

Davranış: seçili kenarlardan `smooth_edge_00N` şeridi üretir, `smooth_edge`
koleksiyonuna koyar, otomatik shade smooth, bundled normal map ile
`decal_normal_only.sps`, Color 1 alpha fade, origin şeridin kendi merkezinde.
"Selected Edge" alt paneli şeridi canlı yeniden kurar (`live_update` kapalıysa
Rebuild butonu).

Testler: `tests/smoothedge.py` (+ paylaşılan `panels.py`, `bundled.py`,
`corner_alpha.py`, `border.py`, `params.py`, `vcolor.py`).
Headless çalıştırma:

```
D:\Blender52\blender.exe --background --python tests\smoothedge.py
```
