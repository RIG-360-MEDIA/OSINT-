"""Central registry of dossier adapters.

Importing this module is enough to register all adapters. Worker iterates
`ADAPTERS` and dispatches `asyncio.gather` over those whose `supported_types`
match the requested target type.
"""

from __future__ import annotations

from backend.adapters.base import AdapterSpec
from backend.adapters.gdelt import SPEC as GDELT_SPEC
from backend.adapters.holehe_lite import SPEC as HOLEHE_LITE_SPEC
from backend.adapters.hudsonrock import SPEC as HUDSONROCK_SPEC
from backend.adapters.opencorporates import SPEC as OPENCORP_SPEC
from backend.adapters.opensanctions import SPEC as OPENSANCTIONS_SPEC
from backend.adapters.searxng import SPEC as SEARXNG_SPEC
from backend.adapters.wayback import SPEC as WAYBACK_SPEC
from backend.adapters.whatsmyname import SPEC as WMN_SPEC
from backend.adapters.wikidata import SPEC as WIKIDATA_SPEC
from backend.adapters.xposedornot import SPEC as XPOSEDORNOT_SPEC

ADAPTERS: tuple[AdapterSpec, ...] = (
    SEARXNG_SPEC,
    WIKIDATA_SPEC,
    XPOSEDORNOT_SPEC,
    WMN_SPEC,
    HUDSONROCK_SPEC,
    OPENSANCTIONS_SPEC,
    GDELT_SPEC,
    WAYBACK_SPEC,
    OPENCORP_SPEC,
    HOLEHE_LITE_SPEC,
)


def adapters_for(target_type: str, allow_sensitive: bool = False) -> tuple[AdapterSpec, ...]:
    return tuple(
        a for a in ADAPTERS
        if target_type in a.supported_types
        and (allow_sensitive or not a.sensitive)
    )
