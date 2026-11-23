#!/bin/zsh
cd "${0:A:h}" || exit 1
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m sec_agent.dashboard
fi
open dashboard/index.html
