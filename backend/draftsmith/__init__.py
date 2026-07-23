"""draftsmith — Door B (AI-assisted article generation) box-side service.

topic → plan → gather → rank → brief → draft → verify/repair → images → ready
Runs on the box; keeps all draft churn on box rig-postgres; Neon touched only
at publish. See migrations/001_draftsmith.sql and models.py (the contract).
"""

__version__ = "0.0.1"
