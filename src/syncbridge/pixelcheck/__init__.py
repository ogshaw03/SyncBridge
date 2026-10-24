"""Pixel accuracy checks for Pixel Mapping (B Lite, docs/PIXEL_MAPPING.md).

Independent of the sync (no server, no Maya / AE): PNG reading and writing, the test BG with
markers at known source pixel positions, and finding those markers in a rendered image.
Standard library only, so it runs in mayapy, in .venv and on a PC without numpy.
"""
