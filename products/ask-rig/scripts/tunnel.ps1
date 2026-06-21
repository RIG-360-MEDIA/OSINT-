# Open a READ-ONLY SSH tunnel to the RIG corpus Postgres.
# Host publishes Postgres at :5433 (-> container 5432). We forward local 15432.
# Leave this running in its own terminal, then set:
#   ASKRIG_DB_URL=postgresql+asyncpg://analytics_user:<pw>@localhost:15432/rig
# (<pw> = the analytics_user password from products/osint/backend/.env)
ssh -i "$env:USERPROFILE\.ssh\rig_hetzner" -N -L 15432:localhost:5433 root@178.105.63.154
