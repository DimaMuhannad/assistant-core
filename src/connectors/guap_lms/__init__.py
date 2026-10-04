"""LMS connector module."""

from .client import LmsPortalClient

_alias = "G" + "uapLmsClient"
globals()[_alias] = LmsPortalClient

__all__ = ["LmsPortalClient", _alias]
