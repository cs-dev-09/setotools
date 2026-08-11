# Smooth Edge

**Geometry → Smooth Edge**

The opposite intent to [Edge Wear](edge-wear.md), from the same strip: a
**normal map** laid along a hard edge so it catches light like a rounded one,
without spending a single extra triangle on an actual bevel.

This is the cheap way to soften an edge in a game asset. A real bevel costs
geometry on every instance; a normal-mapped strip costs one decal and reads
correctly from any normal viewing distance.

## Making one

1. Select the object, enter **Edit Mode**, edge select, pick the edges.
2. Press **Create Smooth Edge**.

The tool panel has nothing else in it, on purpose. It builds the strip that the
**Geometry** section above it describes, and puts a normal map on it instead of
a damage texture — drawing that shape again here is exactly the duplication
that was reported.

## Selected Edge

Same rows as [Edge Wear](edge-wear.md#selected-strip): Width, Surface Offset,
Merge Distance, Flip Direction, the two fades, Position and Bevel. All live.

The one thing worth setting differently is **Width**: the strip has to be
narrow enough to read as the highlight along an edge rather than as a band
painted near it.

## Smooth Edge and Bevel together

Both do the same job by different means, and they are not exclusive:

- **Bevel Mesh** rounds the source corner for real, with a modifier
- **Smooth Edge** fakes the rounding with a normal map

Use the strip alone where the silhouette does not matter — a wall corner seen
face-on. Add a small real bevel where the edge is against the sky or the camera
gets close, since no normal map fixes a silhouette.

## What it builds

- the same strip Edge Wear builds
- `UVMap 0` and `Color 1`
- a `seto_smoothedge` material on `decal_normal_only.sps`
- filed into the `smooth_edge` collection, or the source's Drawable collection
