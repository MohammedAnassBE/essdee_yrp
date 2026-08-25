"""Essdee-owned finishing workflow services.

Base YRP transactions call into this package only through hooks registered by
``essdee_yrp``.  Keeping the calculations here prevents company-specific
finishing rules from leaking into the reusable stock controllers.
"""
