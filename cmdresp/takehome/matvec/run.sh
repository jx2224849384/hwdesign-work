#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matvec_mpl}"
export WAVEFLOW_VITIS_PATH="${WAVEFLOW_VITIS_PATH:-/eda/xilinx}"
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-2100@pyke.poly.edu}"
exec /home/xj2475/hwdesign/.venv/bin/python matvec_build.py "$@"
