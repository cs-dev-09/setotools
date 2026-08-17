# SPDX-License-Identifier: GPL-3.0-or-later
"""
ui.py -- 3D Viewport > N-Panel > "Materialize".

Panel 3D Viewport'ta duruyor: kullanici N'e bastiginda normal calisma
ekraninda elinin altinda olsun. Uretilen haritalari gormek icin acik bir
Image Editor varsa oraya basilir (bkz. VMAT_OT_show_map).

Not: kod yorumlari Turkce, kullaniciya gorunen her metin Ingilizce.
"""

import bpy
from bpy.types import Panel

from . import imageops as iops
from . import sollumz_link
from .properties import LEVEL_LABELS, LEVEL_HINTS
from ..shared import groups
from ..shared import panel_layout as pl


def _wrap(text, width=38):
    """N-panel dar oldugu icin uzun aciklamalari elle sariyoruz;
    UILayout.label kendisi sarmiyor, tasan kismi kirpiyor."""
    words = text.split()
    lines, cur = [], ""
    for word in words:
        candidate = f"{cur} {word}".strip()
        if len(candidate) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    return lines


def _fmt_radius(sigma):
    """Seviyenin etkin yaricapini okunur bicimde yaz."""
    if sigma < 0.5:
        return "1 px"
    if sigma < 10.0:
        return f"{sigma:.1f} px"
    return f"{sigma:.0f} px"


def _presets(layout, label, bank, names):
    """Materialize'daki preset butonlarinin karsiligi."""
    row = layout.row(align=True)
    tag = row.row()
    tag.scale_x = 0.9
    tag.label(text=label)
    for name in names:
        op = row.operator("vmat.preset", text=name.title())
        op.bank = bank
        op.preset = name


def _blur_box(layout, settings, show_contrast, image):
    box = layout.box()
    header = box.row(align=True)
    header.label(text="Frequency Equalizer", icon="MOD_SMOOTH")
    header.prop(settings, "blur_spread", text="Scale")

    # Etkin yaricaplar kaynak goruntunun boyutuna gore degisir; kullanicinin
    # asil merak ettigi "bu seviye kac pikselı kapsiyor" sorusu.
    sigmas = iops.cumulative_sigmas(image.size[0], image.size[1], settings.blur_spread)

    grid = box.column(align=True)
    head = grid.row(align=True)
    name_h = head.row(); name_h.scale_x = 2.0
    name_h.label(text="Scale")
    rad_h = head.row(); rad_h.scale_x = 0.9
    rad_h.alignment = "RIGHT"
    rad_h.label(text="Radius")
    head.label(text="Weight")
    if show_contrast:
        head.label(text="Contrast")

    for i, label in enumerate(LEVEL_LABELS):
        row = grid.row(align=True)

        name = row.row()
        name.scale_x = 2.0
        name.label(text=label)

        rad = row.row()
        rad.scale_x = 0.9
        rad.alignment = "RIGHT"
        rad.active = False
        rad.label(text=_fmt_radius(sigmas[i]))

        row.prop(settings, "blur_weight", index=i, text="")
        if show_contrast:
            row.prop(settings, "blur_contrast", index=i, text="")

    box.separator()
    if show_contrast:
        _presets(box, "Weight", "HEIGHT_WEIGHT", ("DEFAULT", "DETAILS", "DISPLACE"))
        _presets(box, "Contrast", "HEIGHT_CONTRAST", ("DEFAULT", "CRACKS", "FUNKY"))
    else:
        _presets(box, "Preset", "NORMAL_WEIGHT", ("DEFAULT", "SMOOTH", "CRISP", "MIDS"))


def _sample_box(layout, sample, title):
    box = layout.box()
    row = box.row(align=True)
    row.prop(sample, "use", text="")
    row.label(text=title)
    if not sample.use:
        return
    col = box.column(align=True)
    col.prop(sample, "color")
    col.prop(sample, "height")
    col.separator()
    col.prop(sample, "hue_weight")
    col.prop(sample, "sat_weight")
    col.prop(sample, "lum_weight")
    col.separator()
    col.prop(sample, "mask_low")
    col.prop(sample, "mask_high")
    col.separator()
    col.prop(sample, "spread")
    sub = col.row(align=True)
    sub.enabled = sample.spread > 0.0
    sub.prop(sample, "spread_boost")
    col.separator()
    col.prop(sample, "isolate")


class _MaterializeChildPanel(pl.PlainChildPanel):
    """This tool's own child-panel base.

    Not `ToolChildPanel`: that one hides itself when Sollumz is missing, which
    is right for every tool that builds a Sollumz material and wrong for this
    one. Generating a normal map from a diffuse image is numpy and nothing
    else - the machine without a working Sollumz is exactly the one that may
    still want it. See `shared/panel_layout.PlainChildPanel`.
    """


class SETO_PT_material_maker_panel(Panel):
    bl_label = "Material Maker"
    bl_idname = "SETO_PT_material_maker_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    bl_parent_id = groups.MATERIALS
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    # No Sollumz warning here, deliberately, for the same reason the Analysis
    # tools have none: turning a diffuse image into height, normal and
    # specular maps is numpy and nothing else.

    def draw(self, context):
        layout = self.layout
        props = context.scene.vmat

        col = layout.column(align=True)
        col.template_ID(props, "source_image", open="image.open")

        if props.source_image is None:
            layout.label(text="Pick a diffuse image to start", icon="INFO")
            return

        w, h = props.source_image.size
        info = layout.row()
        info.alignment = "RIGHT"
        info.label(text=f"{w} x {h} px")

        col = layout.column(align=True)
        col.prop(props, "tileable")
        col.prop(props, "preview_size")
        col.prop(props, "auto_update")

        # Otomatik guncelleme + buyuk doku + tam cozunurluk = her slider
        # hareketinde saniyeler suren bir donma. Once soyleyelim.
        divisor = max(int(props.preview_size), 1)
        processed = max(w, h) // divisor
        if props.auto_update and processed > 2048:
            warn = layout.column(align=True)
            warn.scale_y = 0.85
            warn.label(text=f"Rebuilding at {processed} px on every change",
                       icon="INFO")
            for line in _wrap("Set Processing Size to Half or Quarter while you "
                              "adjust, then back to Full."):
                warn.label(text=line)

        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.4
        op = row.operator("vmat.generate", text="Generate All", icon="SHADERFX")
        op.target = "ALL"
        row.operator("vmat.reset", text="", icon="LOOP_BACK")

        layout.separator()
        layout.prop(props, "ui_mode", expand=True)
        layout.prop(props, "tab", expand=True)


class SETO_PT_material_maker_settings_panel(_MaterializeChildPanel, Panel):
    bl_label = "Settings"
    bl_idname = "SETO_PT_material_maker_settings_panel"
    bl_parent_id = "SETO_PT_material_maker_panel"
    bl_order = pl.FIRST_CHILD

    @classmethod
    def poll(cls, context):
        return context.scene.vmat.source_image is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.vmat
        layout.use_property_split = True
        layout.use_property_decorate = False

        if props.tab == "HEIGHT":
            self._draw_height(layout, props)
        elif props.tab == "NORMAL":
            self._draw_normal(layout, props)
        else:
            self._draw_specular(layout, props)

        layout.use_property_split = False
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.3
        op = row.operator("vmat.generate", text=f"Generate {props.tab.title()}", icon="FILE_REFRESH")
        op.target = props.tab
        op2 = row.operator("vmat.show_map", text="", icon="IMAGE")
        op2.which = props.tab

    # -------------------------------------------------------- height
    def _draw_height(self, layout, props):
        s = props.height
        simple = props.ui_mode == "SIMPLE"

        if simple:
            layout.use_property_split = False
            _presets(layout, "Look", "HEIGHT_WEIGHT", ("DEFAULT", "DETAILS", "DISPLACE"))
            layout.use_property_split = True
            col = layout.column(align=True)
            col.prop(s, "final_contrast")
            col.prop(s, "final_bias")
            col = layout.column(align=True)
            col.prop(s, "normalize")
            col.prop(s, "invert")
            return

        layout.prop(s, "pre_contrast")

        layout.use_property_split = False
        _blur_box(layout, s, True, props.source_image)
        layout.use_property_split = True

        col = layout.column(align=True)
        col.prop(s, "final_contrast")
        col.prop(s, "final_bias")
        col.prop(s, "final_gain")

        col = layout.column(align=True)
        col.prop(s, "normalize")
        col.prop(s, "invert")

        layout.use_property_split = False
        box = layout.box()
        box.label(text="Color Samples", icon="EYEDROPPER")
        box.label(text="Pull areas close to the picked color", icon="BLANK1")
        box.label(text="to a fixed height (e.g. brick mortar).", icon="BLANK1")
        _sample_box(box, s.sample1, "Sample 1")
        _sample_box(box, s.sample2, "Sample 2")
        if s.sample1.use or s.sample2.use:
            box.prop(s, "sample_blend")
            if s.normalize:
                # Normalize yuzdelik gerdirmesi ornegin genlik degisimini
                # buyuk olcude geri aliyor -- kullanici "hicbir sey olmadi"
                # sanmasin.
                warn = box.column(align=True)
                warn.scale_y = 0.85
                warn.label(text="Normalize Range is flattening this", icon="INFO")
                for line in _wrap("Turn Normalize Range off to see the sample's "
                                  "full depth change."):
                    warn.label(text=line)

    # -------------------------------------------------------- normal
    def _draw_normal(self, layout, props):
        s = props.normal
        simple = props.ui_mode == "SIMPLE"

        layout.use_property_split = False
        row = layout.row(align=True)
        row.prop(s, "source", expand=True)
        layout.use_property_split = True

        if s.source == "HEIGHT" and props.height_image is None:
            layout.label(text="Generate Height first", icon="ERROR")

        if simple:
            layout.prop(s, "strength")
            layout.use_property_split = False
            _presets(layout, "Look", "NORMAL_WEIGHT",
                     ("DEFAULT", "SMOOTH", "CRISP", "MIDS"))
            layout.use_property_split = True
            layout.prop(s, "final_contrast")
            layout.prop(s, "flip_y")
            return

        layout.prop(s, "strength")

        layout.use_property_split = False
        _blur_box(layout, s, False, props.source_image)
        layout.use_property_split = True

        layout.prop(s, "final_contrast")

        # --- sekil tanima ---
        layout.use_property_split = False
        box = layout.box()
        head = box.row(align=True)
        head.label(text="Shape Recognition", icon="MOD_BEVEL")
        head.prop(s, "shape_recognition", text="")

        if s.shape_recognition > 0.0:
            body = box.column(align=True)
            body.use_property_split = True
            body.prop(s, "slope_blur")
            body.prop(s, "shape_bias")
            body.prop(s, "light_rotation")
            body.use_property_split = False
            # Egim zaten diffuse'tan geliyorsa sekil kaynagini diffuse yapmak
            # bir sey degistirmez -- olu kontrol gostermeyelim.
            sub = body.row(align=True)
            sub.enabled = s.source != "DIFFUSE"
            sub.prop(s, "use_diffuse")
        else:
            hint = box.column(align=True)
            hint.scale_y = 0.8
            hint.active = False
            for line in _wrap("Reads broader shapes from the height instead of "
                              "only pixel-to-pixel slope. Raise it to give "
                              "bricks and stones real volume."):
                hint.label(text=line)

        # --- acisallik ---
        box = layout.box()
        head = box.row(align=True)
        head.label(text="Angularity", icon="MESH_ICOSPHERE")
        head.prop(s, "angularity", text="")
        if s.angularity > 0.0:
            sub = box.column(align=True)
            sub.use_property_split = True
            sub.prop(s, "angular_intensity")
        else:
            hint = box.column(align=True)
            hint.scale_y = 0.8
            hint.active = False
            for line in _wrap("Locks slopes to one steepness for a faceted, "
                              "hard-edged look."):
                hint.label(text=line)

        col = layout.column(align=True)
        col.prop(s, "flip_y")
        col.prop(s, "flip_x")

    # ------------------------------------------------------ specular
    def _draw_specular(self, layout, props):
        s = props.specular
        simple = props.ui_mode == "SIMPLE"

        if simple:
            col = layout.column(align=True)
            col.prop(s, "blur_size")
            col.prop(s, "final_contrast")
            col.prop(s, "final_bias")
            layout.use_property_split = False
            layout.separator()
            box = layout.box()
            box.label(text="Channel Packing", icon="COLOR")
            box.prop(s, "channel_mode", text="")
            return

        col = layout.column(align=True)
        col.prop(s, "diffuse_contrast")
        col.prop(s, "diffuse_bias")

        layout.separator()
        col = layout.column(align=True)
        col.prop(s, "blur_size")
        col.prop(s, "blur_contrast")

        layout.separator()
        col = layout.column(align=True)
        col.prop(s, "light_mask_pow")
        col.prop(s, "light_pow")
        col.prop(s, "dark_mask_pow")
        col.prop(s, "dark_pow")

        layout.separator()
        col = layout.column(align=True)
        col.prop(s, "final_contrast")
        col.prop(s, "final_bias")

        # --- kanal paketleme ---
        layout.use_property_split = False
        layout.separator()
        box = layout.box()
        box.label(text="Channel Packing", icon="COLOR")
        box.prop(s, "channel_mode", text="")

        if s.channel_mode == "PACKED":
            hint = box.column(align=True)
            hint.scale_y = 0.8
            hint.active = False
            for line in _wrap("R = intensity, G = falloff, B = fresnel. "
                              "The shader picks a channel with specMapIntMask."):
                hint.label(text=line)

            sub = box.box()
            sub.label(text="R  Intensity", icon="COLOR_RED")
            sub.prop(s, "intensity_invert")

            sub = box.box()
            sub.label(text="G  Falloff", icon="COLOR_GREEN")
            c = sub.column(align=True)
            c.use_property_split = True
            c.prop(s, "falloff_base")
            c.prop(s, "falloff_amount")
            c.prop(s, "falloff_blur")
            sub.prop(s, "falloff_invert")

            sub = box.box()
            sub.label(text="B  Fresnel", icon="COLOR_BLUE")
            c = sub.column(align=True)
            c.use_property_split = True
            c.prop(s, "fresnel_base")
            c.prop(s, "fresnel_amount")
            c.prop(s, "fresnel_blur")
            sub.prop(s, "fresnel_invert")

        layout.use_property_split = True
        layout.separator()
        col = layout.column(align=True)
        # Paketli kipte cikti zaten uc ayri kanal; renk karistirma ve
        # doygunluk o kanallari bozar, o yuzden kapatiyoruz.
        # Paketli kipte bunlarin hicbiri uygulanmaz (her kanalin kendi
        # invert'i var), o yuzden olu kontrol gostermiyoruz.
        col.enabled = s.channel_mode == "GRAYSCALE"
        col.prop(s, "color_lerp")
        sat = col.row(align=True)
        # Keep Color 0 iken specular tamamen gri olur; doygunlugun
        # matematiksel olarak hicbir etkisi kalmaz.
        sat.enabled = s.color_lerp > 0.0
        sat.prop(s, "saturation")
        col.prop(s, "invert")


class SETO_PT_material_maker_scale_guide_panel(_MaterializeChildPanel, Panel):
    """Her blur seviyesinin ne ise yaradigini uzun uzun anlatan katlanabilir
    rehber. Ana gridde satirlar dar oldugu icin aciklamalar buraya alindi."""

    bl_label = "What the levels do"
    bl_idname = "SETO_PT_material_maker_scale_guide_panel"
    bl_parent_id = "SETO_PT_material_maker_settings_panel"
    bl_order = pl.FIRST_CHILD
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        props = context.scene.vmat
        # Frekans merdiveni yalnizca Advanced'te gorunuyor; rehberi de
        # orada gosteriyoruz.
        return (props.source_image is not None
                and props.ui_mode == "ADVANCED"
                and props.tab in {"HEIGHT", "NORMAL"})

    def draw(self, context):
        layout = self.layout
        props = context.scene.vmat
        settings = props.height if props.tab == "HEIGHT" else props.normal
        image = props.source_image
        if image is None:
            # poll() already says no, and Blender honours it - but a draw() that
            # only works because something else refused to call it is one poll
            # edit away from a traceback on every mouse move, and tests/panels.py
            # drives every draw() regardless of poll for exactly that reason.
            return

        sigmas = iops.cumulative_sigmas(image.size[0], image.size[1], settings.blur_spread)

        intro = layout.column(align=True)
        intro.scale_y = 0.85
        for line in _wrap("Luminance is blurred over and over; each level is a "
                          "wider blur than the one above. The weights decide how "
                          "much of each scale ends up in the result."):
            intro.label(text=line)

        for i, (label, hint) in enumerate(zip(LEVEL_LABELS, LEVEL_HINTS)):
            box = layout.box()
            head = box.row(align=True)
            head.label(text=label, icon="DOT" if i else "RADIOBUT_ON")
            rad = head.row()
            rad.alignment = "RIGHT"
            rad.active = False
            rad.label(text=_fmt_radius(sigmas[i]))

            body = box.column(align=True)
            body.scale_y = 0.85
            body.active = False
            for line in _wrap(hint):
                body.label(text=line)

        note = layout.column(align=True)
        note.scale_y = 0.85
        note.active = False
        for line in _wrap("Radii are shown for this image's resolution and scale "
                          "back automatically, so a texture looks the same at "
                          "512 or 4K."):
            note.label(text=line)


class SETO_PT_material_maker_output_panel(_MaterializeChildPanel, Panel):
    bl_label = "Output"
    bl_idname = "SETO_PT_material_maker_output_panel"
    bl_parent_id = "SETO_PT_material_maker_panel"
    bl_order = pl.FIRST_CHILD + 1

    @classmethod
    def poll(cls, context):
        return context.scene.vmat.source_image is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.vmat

        box = layout.box()
        box.label(text="Generated Maps", icon="OUTLINER_OB_IMAGE")
        for which, label, image in (
            ("HEIGHT", "Height", props.height_image),
            ("NORMAL", "Normal", props.normal_image),
            ("SPECULAR", "Specular", props.specular_image),
        ):
            row = box.row(align=True)
            if image is None:
                row.enabled = False
                row.label(text=f"{label}: not generated", icon="DOT")
            else:
                row.label(text=image.name, icon="IMAGE_DATA")
                row.operator("vmat.show_map", text="", icon="HIDE_OFF").which = which

        layout.separator()

        box = layout.box()
        box.label(text="Material", icon="MATERIAL")
        box.prop(props, "material_mode", text="")

        if props.material_mode == "SOLLUMZ":
            if sollumz_link.is_available():
                box.prop(props, "sollumz_shader", text="")

                shader_file = props.sollumz_shader or sollumz_link.DEFAULT_SHADER
                present = sollumz_link.shader_samplers(shader_file)
                sources = {
                    "diffuse": props.source_image,
                    "normal": props.normal_image,
                    "specular": props.specular_image,
                    "height": props.height_image,
                }

                info = box.column(align=True)
                for sampler, key, _ in sollumz_link.SAMPLER_MAP:
                    # Bu shader'da olmayan sampler'i hic gosterme
                    if sampler not in present:
                        continue
                    image = sources[key]
                    row = info.row(align=True)
                    row.active = image is not None
                    row.label(
                        text=f"{sampler}",
                        icon="CHECKMARK" if image is not None else "BLANK1",
                    )
                    name = row.row()
                    name.alignment = "RIGHT"
                    name.label(text=image.name if image is not None else "not generated")
            else:
                warn = box.column(align=True)
                warn.scale_y = 0.85
                warn.label(text="Sollumz not found", icon="ERROR")
                for line in _wrap("Install and enable Sollumz, or switch back "
                                  "to Principled BSDF."):
                    warn.label(text=line)

        row = box.row()
        row.scale_y = 1.2
        row.enabled = props.material_mode != "SOLLUMZ" or sollumz_link.is_available()
        row.operator("vmat.to_material", icon="NODE_MATERIAL")


class SETO_PT_material_maker_export_panel(_MaterializeChildPanel, Panel):
    bl_label = "Export"
    bl_idname = "SETO_PT_material_maker_export_panel"
    bl_parent_id = "SETO_PT_material_maker_panel"
    bl_order = pl.FIRST_CHILD + 2
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene.vmat.source_image is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.vmat

        row = layout.row(align=True)
        row.prop(props, "export_height", toggle=True)
        row.prop(props, "export_normal", toggle=True)
        row.prop(props, "export_specular", toggle=True)

        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(props, "export_dir")
        layout.prop(props, "export_basename")
        layout.prop(props, "export_format")

        if props.ui_mode == "ADVANCED":
            if props.export_format == "PNG":
                layout.prop(props, "export_depth")
            elif props.export_format == "JPEG":
                layout.prop(props, "export_quality")

        if props.export_format != "OPEN_EXR":
            layout.prop(props, "export_colorspace")
            layout.use_property_split = False
            hint = layout.column(align=True)
            hint.scale_y = 0.8
            hint.active = False
            msg = ("Byte values are the map values. Set the image to Non-Color "
                   "when re-importing, or it will look wrong."
                   if props.export_colorspace == "DATA" else
                   "File opens correctly in image viewers, but a game engine "
                   "reading it as raw data will get the wrong values.")
            for line in _wrap(msg):
                hint.label(text=line)
            layout.use_property_split = True

        layout.use_property_split = False
        layout.separator()
        row = layout.row()
        row.scale_y = 1.3
        row.operator("vmat.export", text="Export Images", icon="EXPORT")


_CLASSES = (
    SETO_PT_material_maker_panel,
    SETO_PT_material_maker_settings_panel,
    SETO_PT_material_maker_scale_guide_panel,
    SETO_PT_material_maker_output_panel,
    SETO_PT_material_maker_export_panel,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
