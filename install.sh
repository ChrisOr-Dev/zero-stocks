#!/bin/sh
# Register Stocks with APPLaunch. Copy this folder to ~/zero-stocks on the
# CardputerZero, then run:  sudo sh ~/zero-stocks/install.sh
# The launcher entry is a small wrapper owned by pi; the app itself stays in
# ~/zero-stocks, so later updates need no sudo.
set -eu
cd "$(dirname "$0")"
L=/usr/share/APPLaunch
APP_DIR=$(pwd)
printf '#!/bin/sh\nexec /usr/bin/python3 %s/zero_stocks.py "$@"\n' "$APP_DIR" > "$L/bin/zero-stocks"
chown pi:pi "$L/bin/zero-stocks"
chmod 755 "$L/bin/zero-stocks"
install -m 644 zero-stocks.desktop "$L/applications/zero-stocks.desktop"
python3 zero_stocks.py --make-icon "$L/share/images/zero-stocks.png"
chmod 644 "$L/share/images/zero-stocks.png"
echo "Installed. Restart the launcher as pi: systemctl --user restart APPLaunch"
