#!/bin/sh
set -eu

runtime_dir="${GROK_REGISTER_RUNTIME_DIR:-/data/app}"
mkdir -p "${runtime_dir}"

# The upstream writes config, pending records, browser state, and account outputs
# next to its entrypoint. Copying the complete pinned source into the mounted
# runtime preserves that upstream contract without baking secrets into the image.
cp -a /opt/grok-register/. "${runtime_dir}"/
chmod 0700 "${runtime_dir}"
cd "${runtime_dir}"

# --- GUI/Display bridge (Issue #166) ---
# Start Xvfb on :99 if GROK_REGISTER_GUI_ENABLED is set and no display is already running.
if [ "${GROK_REGISTER_GUI_ENABLED:-0}" = "1" ]; then
    if ! pgrep -x Xvfb > /dev/null 2>&1; then
        Xvfb :99 -screen 0 1280x800x24 -ac +extension GLX +render -noreset &
        # Give Xvfb a moment to initialize before dependent processes start
        sleep 1
    fi
    # x11vnc: loopback-only, no password (Nginx auth handles access control)
    if ! pgrep -x x11vnc > /dev/null 2>&1; then
        x11vnc -display :99 -forever -nopw -shared -rfbport 5900 -localhost &
    fi
    # websockify: bridges VNC to WebSocket for noVNC; loopback-only on NOVNC_PORT
    novnc_port="${GROK_REGISTER_NOVNC_PORT:-6080}"
    if ! pgrep -f "websockify" > /dev/null 2>&1; then
        websockify --web /usr/share/novnc --wrap-mode=ignore \
            0.0.0.0:"${novnc_port}" localhost:5900 &
    fi
fi

exec "$@"
