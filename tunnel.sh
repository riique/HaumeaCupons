#!/bin/bash
if [ -z "$DASHBOARD_API_KEY" ]; then
  echo "DASHBOARD_API_KEY precisa estar definido antes de expor o dashboard."
  exit 1
fi

cloudflared tunnel --url localhost:8000
