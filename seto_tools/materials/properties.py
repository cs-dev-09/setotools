# SPDX-License-Identifier: GPL-3.0-or-later
"""
properties.py -- PropertyGroup'lar. Hepsi scene.vmat altinda toplanir.

Parametre isimleri ve araliklari Materialize'in GUI kaynagindan alindi
(HeightFromDiffuseGui.cs / NormalFromHeightGui.cs / SpecularGui.cs).

Not: kod yorumlari Turkce, kullaniciya gorunen her metin Ingilizce.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from . import sollumz_link

# 7 blur seviyesi: 0 = orijinal, 1..6 = zincirleme blur.
# Etiketler kademe numarasi yerine o kademenin TASIDIGI OLCEGI anlatir --
# kullanici "Level 3"e degil, "orta olcekli forma" mudahale ettigini gorsun.
LEVELS = 7
LEVEL_LABELS = ("Pixel Detail", "Fine Grain", "Small Detail", "Medium Form",
                "Large Form", "Broad Shape", "Overall Shape")

# Materialize'in kendi preset degerleri (HeightFromDiffuseGui.cs /
# NormalFromHeightGui.cs icindeki SetWeightEQ* / SetContrastEQ* fonksiyonlari).
# Sira: seviye 0 (en keskin) -> seviye 6 (en genis).
PRESET_HEIGHT_WEIGHT = {
    "DEFAULT":  (0.15, 0.19, 0.30, 0.50, 0.70, 0.90, 1.00),
    "DETAILS":  (0.70, 0.40, 0.30, 0.50, 0.80, 0.90, 0.70),
    "DISPLACE": (0.02, 0.03, 0.10, 0.35, 0.70, 0.90, 1.00),
}
PRESET_HEIGHT_CONTRAST = {
    "DEFAULT": (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    "CRACKS":  (1.0, 1.0, 1.0, 1.0, -0.2, -2.0, -4.0),
    "FUNKY":   (-3.0, -1.2, 0.30, 1.3, 2.0, 2.5, 2.0),
}
PRESET_NORMAL_WEIGHT = {
    "DEFAULT": (0.30, 0.35, 0.50, 0.80, 1.00, 0.95, 0.80),
    "SMOOTH":  (0.10, 0.15, 0.25, 0.60, 0.90, 1.00, 1.00),
    "CRISP":   (1.00, 0.90, 0.60, 0.40, 0.25, 0.15, 0.10),
    "MIDS":    (0.15, 0.50, 0.85, 1.00, 0.85, 0.50, 0.15),
}

# Panelde her seviyenin altinda gosterilen kisa aciklama.
LEVEL_HINTS = (
    "Raw per-pixel detail: grain, scratches, pores. Raise for crispness, "
    "lower to kill noise",
    "Fine surface texture just above pixel level",
    "Small features: grout lines, rivets, small cracks",
    "Mid-scale shapes: individual bricks, planks, stones",
    "Large shapes: groups of elements, panel divisions",
    "Broad undulation across the texture",
    "Overall form: the general light-to-dark gradient of the whole image. "
    "Raise for a domed look, lower to keep the surface flat",
)


_pending = False
_pending_target = "AUTO"


def _run_pending():
    """Timer gorevi. Update callback icinden bpy.ops cagirmak guvenli
    olmadigi icin uretimi bir sonraki tick'e erteliyoruz."""
    global _pending, _pending_target
    _pending = False
    target, _pending_target = _pending_target, "AUTO"

    scene = bpy.context.scene
    props = getattr(scene, "vmat", None)
    if props is None or props.source_image is None:
        return None
    from . import operators
    try:
        operators.regenerate(scene, target)
    except Exception as exc:  # kullanici slider surukluyor, hata yuzunden durmasin
        print("[Velxor Materialize] auto update failed:", exc)
    return None


def _redraw(self, context):
    """Ayar degisince, otomatik guncelleme acikken yeniden hesapla."""
    global _pending
    props = getattr(context.scene, "vmat", None)
    if props is None or not props.auto_update or props.is_running:
        return
    if props.source_image is None or _pending:
        return
    _pending = True
    bpy.app.timers.register(_run_pending, first_interval=0.15)


def _source_changed(self, context):
    """
    Kaynak doku degisti: eski haritalar artik BASKA bir dokuya ait.
    Gostermeye ya da materyale baglamaya devam etmek yanlis olur, o yuzden
    isaretcileri temizleyip yeni doku icin sifirdan uretim planliyoruz.
    Datablock'lar silinmez -- ayni dokuya geri donulurse yeniden kullanilir.
    """
    global _pending, _pending_target
    self.height_image = None
    self.normal_image = None
    self.specular_image = None

    if self.source_image is None or self.is_running:
        return
    # Aktif sekme degil, UC haritayi birden uret -- doku tamamen yeni.
    _pending_target = "ALL"
    if _pending:
        return
    _pending = True
    bpy.app.timers.register(_run_pending, first_interval=0.05)


# --------------------------------------------------------------- height

class VMAT_HeightSample(PropertyGroup):
    """Bir renk ornegi: secilen renge yakin pikselleri belirli yukseklige cek."""

    use: BoolProperty(
        name="Enabled",
        description="Turn this colour sample on. It finds every pixel close to a "
                    "chosen colour and pushes it to a fixed height -- the usual "
                    "way to sink brick mortar or tile grout",
        default=False, update=_redraw,
    )
    isolate: BoolProperty(
        name="Isolate (show mask)",
        description="Preview mode: outputs the mask itself instead of the height, "
                    "so you can see exactly what the sample is selecting",
        default=False, update=_redraw,
    )
    color: FloatVectorProperty(
        name="Color",
        description="The colour to look for in the diffuse. Pick the mortar, "
                    "grout or rust colour you want to sink or raise",
        subtype="COLOR", size=3, min=0.0, max=1.0,
        default=(0.5, 0.5, 0.5), update=_redraw,
    )
    hue_weight: FloatProperty(
        name="Hue Weight",
        description="How much the colour's hue counts when matching. Raise it "
                    "when the target differs by colour, lower it when everything "
                    "is the same colour",
        default=1.0, min=0.0, max=1.0, update=_redraw,
    )
    sat_weight: FloatProperty(
        name="Saturation Weight",
        description="How much colour richness counts when matching. Useful for "
                    "separating a washed-out area from a vivid one",
        default=0.5, min=0.0, max=1.0, update=_redraw,
    )
    lum_weight: FloatProperty(
        name="Luminance Weight",
        description="How much brightness counts when matching. Raise it when the "
                    "target is simply darker or lighter than its surroundings",
        default=0.2, min=0.0, max=1.0, update=_redraw,
    )
    mask_low: FloatProperty(
        name="Mask Low", description="Pixels below this closeness stay out of the mask",
        default=0.0, min=0.0, max=1.0, update=_redraw,
    )
    mask_high: FloatProperty(
        name="Mask High", description="Pixels above this closeness are fully masked",
        default=1.0, min=0.0, max=1.0, update=_redraw,
    )
    height: FloatProperty(
        name="Height",
        description="The height the matched pixels are pushed to. 0 sinks them "
                    "to the floor, 1 raises them to the top",
        default=0.5, min=0.0, max=1.0, update=_redraw,
    )
    spread: FloatProperty(
        name="Spread",
        description="Blur the mask to soften its edges, so the sampled area "
                    "fades into the surroundings instead of cutting sharply. "
                    "0 turns this off",
        default=0.0, min=0.0, max=200.0, update=_redraw,
    )
    spread_boost: FloatProperty(
        name="Spread Boost",
        description="Strengthens the softened mask so blurring it does not also "
                    "weaken it. Only does anything while Spread is above 0",
        default=1.0, min=1.0, max=5.0, update=_redraw,
    )

    def as_dict(self):
        return {
            "use": self.use,
            "isolate": self.isolate,
            "color": tuple(self.color),
            "hue_weight": self.hue_weight,
            "sat_weight": self.sat_weight,
            "lum_weight": self.lum_weight,
            "mask_low": self.mask_low,
            "mask_high": self.mask_high,
            "height": self.height,
            "spread": self.spread,
            "spread_boost": self.spread_boost,
        }


class VMAT_HeightSettings(PropertyGroup):
    pre_contrast: FloatProperty(
        name="Pre Contrast", description="Applied to luminance before the blur chain",
        default=1.0, min=0.0, max=10.0, update=_redraw,
    )
    blur_weight: FloatVectorProperty(
        name="Frequency Weights", size=LEVELS, min=0.0, max=1.0,
        description="How much each scale contributes to the height. Low levels "
                    "carry fine surface detail, high levels carry the overall form",
        default=PRESET_HEIGHT_WEIGHT["DEFAULT"], update=_redraw,
    )
    blur_contrast: FloatVectorProperty(
        name="Frequency Contrasts", size=LEVELS, min=-5.0, max=5.0,
        description="Scales each frequency band. Negative values INVERT that "
                    "band -- this is how the Cracks and Funky presets work",
        default=PRESET_HEIGHT_CONTRAST["DEFAULT"], update=_redraw,
    )
    blur_spread: FloatProperty(
        name="Blur Scale", description="Scales every blur level together",
        default=1.0, min=0.1, max=5.0, update=_redraw,
    )
    sample_blend: FloatProperty(
        name="Sample Blend",
        description="How strongly the colour samples override the height. 0 "
                    "ignores them, 1 replaces the matched areas completely",
        default=0.5, min=0.0, max=1.0, update=_redraw,
    )
    final_contrast: FloatProperty(
        name="Final Contrast",
        description="Pushes highs and lows apart. Raise it for a deeper, more "
                    "dramatic surface, lower it for a flatter one",
        default=1.5, min=0.0, max=10.0, update=_redraw,
    )
    final_bias: FloatProperty(
        name="Final Bias",
        description="Shifts the whole map up or down, moving where the surface "
                    "sits relative to zero",
        default=0.0, min=-0.5, max=0.5, update=_redraw,
    )
    final_gain: FloatProperty(
        name="Final Gain",
        description="S-curve on the result. Negative hardens the midtones, "
                    "positive softens them. 0 is neutral",
        default=0.0, min=-0.5, max=0.5, update=_redraw,
    )
    normalize: BoolProperty(
        name="Normalize Range",
        description="Stretch the result to the full 0..1 range, ignoring outlier "
                    "pixels. Not part of Materialize (there you watch a live "
                    "preview and crank Final Contrast by hand) -- without it the "
                    "height usually lands in a narrow band and the normal looks flat",
        default=True, update=_redraw,
    )
    invert: BoolProperty(
        name="Invert",
        description="Flip the map, turning bumps into dents. Use it when the "
                    "source reads inside-out",
        default=False, update=_redraw,
    )

    # Not: Materialize'da ornek 2'nin varsayilan yuksekligi 0.3, ornek 1'inki
    # 0.5. Ikisi ayni PropertyGroup tipini paylastigi icin ikisi de 0.5 baslar.
    sample1: PointerProperty(type=VMAT_HeightSample)
    sample2: PointerProperty(type=VMAT_HeightSample)

    def as_dict(self):
        return {
            "pre_contrast": self.pre_contrast,
            "blur_weight": list(self.blur_weight),
            "blur_contrast": list(self.blur_contrast),
            "blur_spread": self.blur_spread,
            "sample_blend": self.sample_blend,
            "final_contrast": self.final_contrast,
            "final_bias": self.final_bias,
            "final_gain": self.final_gain,
            "normalize": self.normalize,
            "invert": self.invert,
            "samples": (self.sample1.as_dict(), self.sample2.as_dict()),
        }


# --------------------------------------------------------------- normal

class VMAT_NormalSettings(PropertyGroup):
    source: EnumProperty(
        name="Slope From",
        description="Which image the surface slope is read from",
        items=(
            ("DIFFUSE", "Diffuse",
             "Read the slope straight from the source diffuse. Keeps every bit "
             "of detail the diffuse has, independent of how the height map was "
             "shaped"),
            ("HEIGHT", "Height Map",
             "Read the slope from the generated height map. Use this when the "
             "height map's frequency shaping is what you want the normal to follow"),
        ),
        default="DIFFUSE", update=_redraw,
    )
    strength: FloatProperty(
        name="Strength",
        description="Slope multiplier (Materialize's 'Pre Contrast'). Raise this "
                    "if the normal looks too flat. Scaled to the image size, so "
                    "changing Processing Size does not change how strong it looks",
        default=20.0, min=0.0, max=50.0, update=_redraw,
    )
    blur_weight: FloatVectorProperty(
        name="Frequency Weights", size=LEVELS, min=0.0, max=1.0,
        description="How much each scale contributes to the normal. Low levels "
                    "give sharp surface bumps, high levels give the broad slope "
                    "the surface leans along",
        default=PRESET_NORMAL_WEIGHT["DEFAULT"], update=_redraw,
    )
    blur_spread: FloatProperty(
        name="Blur Scale",
        description="Stretches or squeezes every frequency level at once, "
                    "changing how large the features the normal picks up are",
        default=1.0, min=0.1, max=5.0, update=_redraw,
    )
    final_contrast: FloatProperty(
        name="Final Contrast",
        description="Steepens the whole normal. Raise it for a harsher, more "
                    "pronounced surface; 0 flattens it completely",
        default=5.0, min=0.0, max=10.0, update=_redraw,
    )

    # --- sekil tanima (fragNormal) ---
    shape_recognition: FloatProperty(
        name="Shape Recognition",
        description="Reads broader shapes from the height map instead of only "
                    "neighbouring-pixel slope. Gives bricks and stones real "
                    "volume instead of just edge outlines. 0 disables it",
        default=0.0, min=0.0, max=1.0, update=_redraw,
    )
    shape_bias: FloatProperty(
        name="Shape Bias",
        description="Shifts what counts as raised vs recessed. 0.5 is neutral",
        default=0.5, min=0.0, max=1.0, update=_redraw,
    )
    light_rotation: FloatProperty(
        name="Light Rotation",
        description="Direction the shape is lit from, in radians",
        default=0.0, min=-3.14159, max=3.14159, subtype="ANGLE", update=_redraw,
    )
    slope_blur: IntProperty(
        name="Slope Blur",
        description="How wide a shape counts as a shape. Low = small details, "
                    "high = large forms",
        default=50, min=5, max=100, update=_redraw,
    )
    use_diffuse: BoolProperty(
        name="Read Shapes From Diffuse",
        description="Take the shapes from the source diffuse instead of the "
                    "slope source. This is Materialize's own default",
        default=True, update=_redraw,
    )

    # --- acisallik (fragCombineNormal) ---
    angularity: FloatProperty(
        name="Angularity",
        description="Locks slopes to a fixed steepness for a faceted, hard-edged "
                    "surface. 0 disables it",
        default=0.0, min=0.0, max=1.0, update=_redraw,
    )
    angular_intensity: FloatProperty(
        name="Angular Intensity",
        description="How steep that locked angle is",
        default=0.5, min=0.0, max=1.0, update=_redraw,
    )

    flip_y: BoolProperty(
        name="Flip Y (DirectX)",
        description="Off: OpenGL / Blender / GTA. On: DirectX / Unity",
        default=False, update=_redraw,
    )
    flip_x: BoolProperty(
        name="Flip X",
        description="Mirror the horizontal direction of the normal. Rarely "
                    "needed -- only if lighting reads reversed left to right",
        default=False, update=_redraw,
    )

    def as_dict(self):
        return {
            "source": self.source,
            "strength": self.strength,
            "blur_weight": list(self.blur_weight),
            "blur_spread": self.blur_spread,
            "final_contrast": self.final_contrast,
            "shape_recognition": self.shape_recognition,
            "shape_bias": self.shape_bias,
            "light_rotation": self.light_rotation,
            "slope_blur": self.slope_blur,
            "use_diffuse": self.use_diffuse,
            "angularity": self.angularity,
            "angular_intensity": self.angular_intensity,
            "flip_y": self.flip_y,
            "flip_x": self.flip_x,
        }


# --------------------------------------------------------------- specular

class VMAT_SpecularSettings(PropertyGroup):
    diffuse_contrast: FloatProperty(
        name="Diffuse Contrast",
        description="Contrast applied to the source image before anything else. "
                    "Raise it to separate shiny and matte areas more sharply",
        default=1.0, min=0.0, max=3.0, update=_redraw,
    )
    diffuse_bias: FloatProperty(
        name="Diffuse Bias",
        description="Brightens or darkens the source before processing, moving "
                    "the whole surface toward shinier or duller",
        default=0.0, min=-0.5, max=0.5, update=_redraw,
    )
    blur_size: IntProperty(
        name="Blur Size", description="Radius used to estimate ambient lighting",
        default=30, min=1, max=100, update=_redraw,
    )
    blur_contrast: FloatProperty(
        name="Blur Contrast",
        description="Contrast of the blurred reference the surface is compared "
                    "against. Changes how aggressively fine detail is pulled out",
        default=1.0, min=-5.0, max=5.0, update=_redraw,
    )
    # Bunlar shader'da KUVVET degil ESIK: smoothstep(threshold, ...) seklinde
    # maxLum uzerinde calisiyorlar, dolayisiyla anlamli aralik 0..1.
    light_mask_pow: FloatProperty(
        name="Highlight Threshold",
        description="Pixels brighter than this count as a highlight and get "
                    "flattened toward the blur by Remove Light",
        default=0.75, min=0.0, max=1.0, update=_redraw,
    )
    light_pow: FloatProperty(
        name="Remove Light", description="How strongly highlights are flattened",
        default=0.0, min=0.0, max=1.0, update=_redraw,
    )
    dark_mask_pow: FloatProperty(
        name="Shadow Threshold",
        description="Pixels darker than this count as a shadow and get "
                    "flattened toward the blur by Remove Shadow",
        default=0.25, min=0.0, max=1.0, update=_redraw,
    )
    dark_pow: FloatProperty(
        name="Remove Shadow", description="How strongly shadows are flattened",
        default=0.0, min=0.0, max=1.0, update=_redraw,
    )
    final_contrast: FloatProperty(
        name="Final Contrast",
        description="Separates shiny from matte. Raise it for a surface that "
                    "reflects unevenly, lower it for a uniform finish",
        default=1.0, min=0.0, max=5.0, update=_redraw,
    )
    final_bias: FloatProperty(
        name="Final Bias",
        description="Makes the whole surface more or less reflective at once",
        default=0.0, min=-0.5, max=0.5, update=_redraw,
    )
    color_lerp: FloatProperty(
        name="Keep Color", description="0 = grey specular, 1 = specular tinted by the diffuse",
        default=0.0, min=0.0, max=1.0, update=_redraw,
    )
    # --- GTA kanal paketlemesi ---
    # Olculen gercek GTA dokularindaki hedefler (casino_details_03_s):
    #   R ort 0.584 std 0.136 | G ort 0.797 std 0.027 | B ort 0.923 std 0.013
    channel_mode: EnumProperty(
        name="Channels",
        description="How the three channels of the specular texture are used",
        items=(
            ("GRAYSCALE", "Grayscale",
             "One value copied to R, G and B. 39% of the GTA textures measured "
             "do this, including most simple surfaces"),
            ("PACKED", "Packed (GTA)",
             "R = specular intensity, G = falloff, B = fresnel -- the packing "
             "GTA shaders read through specMapIntMask"),
        ),
        default="GRAYSCALE", update=_redraw,
    )
    intensity_invert: BoolProperty(
        name="Invert Intensity",
        description="Flip the red channel, so areas that were shiny become matte",
        default=False, update=_redraw,
    )

    falloff_base: FloatProperty(
        name="Falloff Level", description="Mean value of the green channel",
        default=0.80, min=0.0, max=1.0, update=_redraw,
    )
    falloff_amount: FloatProperty(
        name="Falloff Variation", description="How much of the specular signal the "
        "green channel carries",
        default=0.45, min=0.0, max=2.0, update=_redraw,
    )
    falloff_blur: IntProperty(
        name="Falloff Softness",
        description="How much the green channel is smoothed. Higher values make "
                    "gloss change gradually across the surface instead of "
                    "following every small mark",
        default=18, min=0, max=100, update=_redraw,
    )
    falloff_invert: BoolProperty(
        name="Invert Falloff",
        description="Flip the green channel, swapping tight highlights for broad ones",
        default=False, update=_redraw,
    )

    fresnel_base: FloatProperty(
        name="Fresnel Level", description="Mean value of the blue channel",
        default=0.92, min=0.0, max=1.0, update=_redraw,
    )
    fresnel_amount: FloatProperty(
        name="Fresnel Variation",
        description="How much the blue channel varies across the surface. Real "
                    "GTA textures keep this very low -- fresnel is nearly uniform",
        default=0.22, min=0.0, max=2.0, update=_redraw,
    )
    fresnel_blur: IntProperty(
        name="Fresnel Softness",
        description="How much the blue channel is smoothed. Usually the highest "
                    "of the three, since fresnel should not follow surface detail",
        default=45, min=0, max=100, update=_redraw,
    )
    fresnel_invert: BoolProperty(
        name="Invert Fresnel",
        description="Some GTA textures store blue as the exact inverse of red "
                    "(measured in CV_Interior_s.dds)",
        default=False, update=_redraw,
    )

    saturation: FloatProperty(
        name="Saturation",
        description="Colour richness of the specular. Only has an effect while "
                    "Keep Color is above 0 -- a fully grey map has no saturation "
                    "to change",
        default=1.0, min=0.0, max=2.0, update=_redraw,
    )
    invert: BoolProperty(
        name="Invert",
        description="Flip the map, so shiny areas become matte and vice versa",
        default=False, update=_redraw,
    )

    def as_dict(self):
        return {
            "diffuse_contrast": self.diffuse_contrast,
            "diffuse_bias": self.diffuse_bias,
            "blur_size": self.blur_size,
            "blur_contrast": self.blur_contrast,
            "light_mask_pow": self.light_mask_pow,
            "light_pow": self.light_pow,
            "dark_mask_pow": self.dark_mask_pow,
            "dark_pow": self.dark_pow,
            "final_contrast": self.final_contrast,
            "final_bias": self.final_bias,
            "color_lerp": self.color_lerp,
            "saturation": self.saturation,
            "invert": self.invert,
            "channel_mode": self.channel_mode,
            "intensity_invert": self.intensity_invert,
            "falloff_base": self.falloff_base,
            "falloff_amount": self.falloff_amount,
            "falloff_blur": self.falloff_blur,
            "falloff_invert": self.falloff_invert,
            "fresnel_base": self.fresnel_base,
            "fresnel_amount": self.fresnel_amount,
            "fresnel_blur": self.fresnel_blur,
            "fresnel_invert": self.fresnel_invert,
        }


# --------------------------------------------------------------- kok

class VMAT_Props(PropertyGroup):
    source_image: PointerProperty(
        type=bpy.types.Image, name="Diffuse",
        description="Source diffuse / albedo image. Selecting a new one clears "
                    "the previous maps and regenerates from scratch",
        update=_source_changed,
    )

    height: PointerProperty(type=VMAT_HeightSettings)
    normal: PointerProperty(type=VMAT_NormalSettings)
    specular: PointerProperty(type=VMAT_SpecularSettings)

    # uretilen datablock'lar
    height_image: PointerProperty(
        type=bpy.types.Image, name="Height Map",
        description="The generated height map. Replaced every time you generate")
    normal_image: PointerProperty(
        type=bpy.types.Image, name="Normal Map",
        description="The generated normal map. Replaced every time you generate")
    specular_image: PointerProperty(
        type=bpy.types.Image, name="Specular Map",
        description="The generated specular map. Replaced every time you generate")

    ui_mode: EnumProperty(
        name="Mode",
        description="How many controls the panel shows",
        items=(
            ("SIMPLE", "Simple",
             "Just the handful of settings that change the result most. "
             "Everything else keeps working in the background"),
            ("ADVANCED", "Advanced",
             "Every control, including the frequency equalizers, shape "
             "recognition and per-channel packing"),
        ),
        default="SIMPLE",
    )

    tab: EnumProperty(
        name="Tab",
        description="Which map you are setting up",
        items=(
            ("HEIGHT", "Height", "Bumps and dents -- how far in or out each part "
             "of the surface sits", "IPO_EASE_IN_OUT", 0),
            ("NORMAL", "Normal", "Surface direction -- makes flat geometry catch "
             "light as if it had relief", "NORMALS_FACE", 1),
            ("SPECULAR", "Specular", "Shininess -- which parts of the surface "
             "reflect light and how much", "SHADING_RENDERED", 2),
        ),
        default="HEIGHT",
    )

    material_mode: EnumProperty(
        name="Material Type",
        description="Which kind of material Create / Update Material builds",
        update=lambda self, context: sollumz_link.invalidate_cache(),
        items=(
            ("PRINCIPLED", "Principled BSDF",
             "Standard Blender PBR material: normal into Normal Map, "
             "specular into Roughness, height into Displacement"),
            ("SOLLUMZ", "Sollumz Shader",
             "GTA V shader built by Sollumz. Maps go into DiffuseSampler, "
             "BumpSampler and SpecSampler"),
        ),
        default="PRINCIPLED",
    )
    sollumz_shader: EnumProperty(
        name="Shader",
        description="Sollumz shader to build. Only shaders that carry Diffuse, "
                    "Bump and Spec samplers are listed",
        items=lambda self, context: sollumz_link.compatible_shaders(),
    )

    tileable: BoolProperty(
        name="Tileable Edges",
        description="Wrap edges to the opposite side during blur and derivative "
                    "passes. Keep this on for seamless textures",
        default=True, update=_redraw,
    )
    auto_update: BoolProperty(
        name="Auto Update",
        description="Rebuild the maps as soon as you change a setting. On large "
                    "textures drop Processing Size to Half or Quarter so this "
                    "stays responsive",
        default=True,
    )
    preview_size: EnumProperty(
        name="Processing Size",
        description="Resolution the maps are built at. Drop it while you are "
                    "still adjusting settings, then switch back to Full for the "
                    "final result. The look holds steady as long as the result "
                    "stays around 512 px or larger -- below that fine detail "
                    "genuinely starts to disappear",
        items=(
            ("1", "Full", "The source image's own resolution"),
            ("2", "Half", "Half the width and height -- about four times faster"),
            ("4", "Quarter", "Quarter the width and height -- fastest. On a small "
             "source this can drop below 512 px and lose fine detail"),
        ),
        default="1",
    )

    is_running: BoolProperty(default=False, options={"HIDDEN"})

    # --- export ---
    export_dir: StringProperty(
        name="Directory",
        description="Folder the maps are written to. '//' means next to the "
                    "saved .blend file",
        subtype="DIR_PATH", default="//",
    )
    export_basename: StringProperty(
        name="Base Name", description="Falls back to the source image name when left empty",
        default="",
    )
    export_format: EnumProperty(
        name="Format",
        description="File type the maps are saved as",
        items=(
            ("PNG", "PNG", "Lossless, 8 or 16 bit"),
            ("JPEG", "JPG / JPEG", "Lossy, 8 bit"),
            ("TARGA", "TGA", "Lossless, 8 bit"),
            ("OPEN_EXR", "EXR", "32 bit float"),
        ),
        default="PNG",
    )
    export_depth: EnumProperty(
        name="Bit Depth",
        description="Precision of the saved file. Height maps benefit from 16 "
                    "bit, since 8 bit can show visible steps on smooth gradients",
        items=(
            ("8", "8 bit", "Smaller files. Fine for normal and specular maps, "
             "can band on smooth height gradients"),
            ("16", "16 bit", "Twice the file size, no visible banding. The safer "
             "choice for height maps"),
        ),
        default="16",
    )
    export_colorspace: EnumProperty(
        name="Written As",
        description="How the map values are stored in the file. PNG and TGA carry "
                    "no colour space information, so this decides how the file "
                    "will be read back",
        items=(
            ("DATA", "Raw data",
             "Byte values are the map values exactly. Correct for game engines "
             "and Sollumz. When re-importing, set the image to Non-Color -- "
             "otherwise it will look wrong"),
            ("SRGB", "sRGB encoded",
             "Values are sRGB-encoded so the file opens correctly in ordinary "
             "image viewers and in Blender's default PNG import. Do not use for "
             "textures a game engine reads as raw data"),
        ),
        default="DATA",
    )
    export_quality: IntProperty(
        name="Quality",
        description="JPEG compression quality. Below about 90 the compression "
                    "starts showing up as blocky artefacts in the map",
        default=90, min=1, max=100,
    )
    export_height: BoolProperty(
        name="Height", description="Include the height map in the export", default=True)
    export_normal: BoolProperty(
        name="Normal", description="Include the normal map in the export", default=True)
    export_specular: BoolProperty(
        name="Specular", description="Include the specular map in the export", default=True)


_CLASSES = (
    VMAT_HeightSample,
    VMAT_HeightSettings,
    VMAT_NormalSettings,
    VMAT_SpecularSettings,
    VMAT_Props,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.vmat = PointerProperty(type=VMAT_Props)


def unregister():
    del bpy.types.Scene.vmat
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
