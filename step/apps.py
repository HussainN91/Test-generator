"""App config for the STEP obligations platform.

STEP is decoupled from `content`, `bank`, `assembly` and `diagnostics` by
design (see the spine spec §9). Nothing here may import from those apps, and
nothing there may import from here, until the Assessments merge in slice 3.
"""

from django.apps import AppConfig


class StepConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "step"
    verbose_name = "STEP Platform"
