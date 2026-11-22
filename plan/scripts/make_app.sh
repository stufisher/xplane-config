#!/bin/bash
# Build Plan.app in the current directory, a macOS launcher that activates a conda env
# and starts plan-ui.
# Run on the Mac from a shell where conda works:
#   make_app.sh [-e conda_env] [-i icon.png] [-s WIDTHxHEIGHT] [-- plan-ui args...]
# e.g. make_app.sh -e plan -- --xplane-dir "~/X-Plane 12"
# The default icon is Font Awesome Free's plane-departure (CC BY 4.0, fontawesome.com)
set -euo pipefail

ENV_NAME=plan
ICON_PNG="$(cd "$(dirname "$0")/.." && pwd)/assets/icon/plan.png"
# Window size, matching plan-ui's own default
SIZE=956x652
while getopts "e:i:s:" opt; do
    case $opt in
        e) ENV_NAME=$OPTARG ;;
        i) ICON_PNG=$OPTARG ;;
        s) SIZE=$OPTARG ;;
        *) sed -n '2,6p' "$0"; exit 1 ;;
    esac
done
shift $((OPTIND - 1))
[[ "${1:-}" == "--" ]] && shift
[[ "$SIZE" =~ ^[0-9]+x[0-9]+$ ]] || { echo "-s wants WIDTHxHEIGHT, got $SIZE"; exit 1; }

APP="$PWD/Plan.app"
if [[ -e "$APP" ]]; then
    echo "$APP already exists; remove it first to rebuild"
    exit 1
fi

# Finder starts apps without the login shell, so the conda location is fixed at build time
CONDA_BASE=$(conda info --base) || { echo "conda not found on PATH"; exit 1; }
ENV_PREFIX="$CONDA_BASE/envs/$ENV_NAME"
[[ -x "$ENV_PREFIX/bin/plan-ui" ]] || {
    echo "No plan-ui in $ENV_PREFIX; pip install -e plan in that env first"
    exit 1
}

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

ARGS=$(printf '%q ' --window-size "$SIZE" "$@")
cat >"$APP/Contents/MacOS/Plan" <<EOF
#!/bin/bash
# Starts plan-ui, or just reopens its window when it is already running
URL=http://localhost:8080
if curl -s -o /dev/null "\$URL"; then
    # A fresh profile has no saved window bounds, so Chrome honours --window-size
    exec open -na "Google Chrome" --args --app="\$URL" \\
        --user-data-dir="\$(mktemp -d /tmp/chrome-kiosk-XXXXXX)" \\
        --no-first-run --no-default-browser-check --window-size=${SIZE/x/,}
fi
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
exec plan-ui $ARGS>>"\$HOME/Library/Logs/plan-ui.log" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/Plan"

ICON_KEY=
if [[ -n "$ICON_PNG" ]]; then
    ICONSET=$(mktemp -d)/Plan.iconset
    mkdir -p "$ICONSET"
    for size in 16 32 128 256 512; do
        sips -z $size $size "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
        sips -z $((size * 2)) $((size * 2)) "$ICON_PNG" \
            --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Plan.icns"
    ICON_KEY="<key>CFBundleIconFile</key><string>Plan</string>"
fi

cat >"$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Plan</string>
    <key>CFBundleIdentifier</key><string>local.plan-ui</string>
    <key>CFBundleExecutable</key><string>Plan</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    $ICON_KEY
</dict>
</plist>
EOF

echo "Built $APP (conda env $ENV_NAME, log ~/Library/Logs/plan-ui.log)"
