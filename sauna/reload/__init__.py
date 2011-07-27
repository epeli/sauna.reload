# -*- coding: utf-8 -*-
"""sauna.reaload"""

# Enable sauna.reload's Zope patches and deferrend z3c.autoinclude includes by
# adding ``zope-conf-additional = %import sauna.reload`` into your buildout's
# *plone.recipe.zope2instance*-part.
#
# [instance]
# recipe = plone.recipe.zope2instance
# zope-conf-additional = %import sauna.reload

from reload import forkloop

def initialize(context):
    """Initializer called when used as a Zope 2 product."""

import sys

from sauna.reload.monkeypatcher import MonkeyPatchingLoader

# Hook into PEP 302 laoder
__loader__ = MonkeyPatchingLoader(sys.modules[__name__])
