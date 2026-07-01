#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/linaro/edgeinfer-rk3588-board"
SERVICE_NAME="edgeinfer-serving.service"
SERVICE_SRC="${PROJECT_DIR}/deploy/systemd/${SERVICE_NAME}"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"

echo "=== EdgeInfer Serving Service Installer ==="

if [ ! -d "${PROJECT_DIR}" ]; then
  echo "ERROR: project directory not found: ${PROJECT_DIR}" >&2
  exit 1
fi

if [ ! -f "${SERVICE_SRC}" ]; then
  echo "ERROR: service file not found: ${SERVICE_SRC}" >&2
  exit 1
fi

if [ ! -x "${PROJECT_DIR}/.venv-serving/bin/python" ]; then
  echo "ERROR: serving virtualenv python not found: ${PROJECT_DIR}/.venv-serving/bin/python" >&2
  exit 1
fi

if [ ! -f "${PROJECT_DIR}/server/main.py" ]; then
  echo "ERROR: server/main.py not found" >&2
  exit 1
fi

echo
echo "=== Disable legacy demo services ==="
sudo systemctl disable --now qwen-web-chat.service 2>/dev/null || true
sudo systemctl disable --now yolov5-web.service 2>/dev/null || true

echo
echo "=== Install ${SERVICE_NAME} ==="
sudo install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo
echo "=== Installed ==="
systemctl is-enabled "${SERVICE_NAME}" || true

echo
echo "Use these commands on board:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo "  sudo systemctl stop ${SERVICE_NAME}"
echo "  systemctl status ${SERVICE_NAME} --no-pager"
echo "  journalctl -u ${SERVICE_NAME} -f"
