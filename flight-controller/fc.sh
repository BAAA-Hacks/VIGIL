#!/usr/bin/env bash
# Redstart flight-controller helper: build and flash INAV (REDSTART target).
#
#   ./fc.sh setup    download INAV, apply patches/, link target/ (done automatically by build)
#   ./fc.sh build    set up INAV (first time) and build -> inav/build/inav_7.1.2_REDSTART.hex
#   ./fc.sh flash    flash the built hex over ST-Link (SWD), then reset the board
#                    (SWD_KHZ=200 ./fc.sh flash for a slower SWD clock)
#   ./fc.sh all      build, then flash
#   ./fc.sh clean    remove build output for the REDSTART target
#
# inav/ is not in git. On first use this script downloads the INAV release
# tarball, applies patches/*.patch and links target/REDSTART into the tree.
# Edit our code in target/ and patches/, never inside inav/.
set -euo pipefail

TARGET=REDSTART
INAV_VERSION=7.1.2
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INAV="$ROOT/inav"
BUILD="$INAV/build"
HEX="$BUILD/inav_${INAV_VERSION}_${TARGET}.hex"
STAMP="$INAV/.redstart-setup"

setup() {
    [[ -f "$STAMP" ]] && return
    if [[ -e "$INAV" ]]; then
        echo "inav/ exists but wasn't set up by this script; move it aside and rerun." >&2
        exit 1
    fi
    echo "==> Downloading INAV $INAV_VERSION"
    mkdir -p "$INAV"
    curl -fsSL "https://github.com/iNavFlight/inav/archive/refs/tags/${INAV_VERSION}.tar.gz" \
        | tar -xz -C "$INAV" --strip-components=1
    for p in "$ROOT"/patches/*.patch; do
        echo "==> Applying $(basename "$p")"
        patch -p1 -d "$INAV" --forward < "$p"
    done
    ln -s "../../../../target/$TARGET" "$INAV/src/main/target/$TARGET"
    touch "$STAMP"
}

build() {
    setup
    if [[ ! -f "$BUILD/Makefile" ]]; then
        echo "==> Configuring INAV (first run downloads the ARM toolchain)"
        cmake -S "$ROOT/inav" -B "$BUILD"
    fi
    echo "==> Building $TARGET"
    make -C "$BUILD" -j"$(nproc)" "$TARGET"
    echo "==> Built $HEX"
}

flash() {
    if [[ ! -f "$HEX" ]]; then
        echo "No firmware at $HEX; run ./fc.sh build first." >&2
        exit 1
    fi
    local speed="${SWD_KHZ:-1000}"
    echo "==> Flashing $HEX over ST-Link (SWD ${speed} kHz)"
    if ! openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
        -c "adapter speed $speed" \
        -c "program $HEX verify reset exit"; then
        cat >&2 <<'EOF'

Flash failed. If the ST-Link was found but "unable to connect to the target":
  1. Wiring: ST-Link SWDIO -> Black Pill DIO (PA13), SWCLK -> SCK/CLK (PA14), GND -> GND.
  2. Slower clock:   SWD_KHZ=200 ./fc.sh flash
  3. Boot the ROM bootloader first: hold BOOT0, tap NRST, release BOOT0, then ./fc.sh flash
EOF
        exit 1
    fi
}

case "${1:-}" in
    setup) setup ;;
    build) build ;;
    flash) flash ;;
    all)   build; flash ;;
    clean) make -C "$BUILD" "clean_$TARGET" ;;
    *)     echo "usage: $0 {setup|build|flash|all|clean}" >&2; exit 2 ;;
esac
