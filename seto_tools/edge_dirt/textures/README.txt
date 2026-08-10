Put your dirt texture in this folder.

The first usable image here is wired into the generated material's
DiffuseSampler automatically, as sRGB (a colour texture, not a normal map) and
not embedded. .dds is preferred, then .png, .tga, .jpg, .jpeg.

A file named edge_dirt.* wins over the others, so you can keep several around
and pin the one you want without deleting anything.

The file NAME matters: Sollumz exports the texture name from it without the
extension, so decal_dirt_01.dds becomes the "decal_dirt_01" reference in the
.ydr - which then has to exist in the asset's TXD.

Leaving this folder empty is not an error. The strip and its material are still
built; the tool just reports that the texture slot was left for you.
