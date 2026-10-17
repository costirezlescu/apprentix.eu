#!/bin/zsh
# usage: shot.sh page.html width height out.png
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SRC="file://$PWD/$1"; W=$2; H=$3; OUT=$4
if [ "$W" -lt 500 ]; then
  cat > frame.html <<HTML
<!doctype html><html><body style="margin:0;background:#888"><iframe src="$SRC" style="border:0;width:${W}px;height:${H}px;display:block"></iframe></body></html>
HTML
  "$CH" --headless=new --disable-gpu --hide-scrollbars --window-size=500,$H --virtual-time-budget=4000 --screenshot=$OUT "file://$PWD/frame.html" 2>/dev/null
else
  "$CH" --headless=new --disable-gpu --hide-scrollbars --window-size=$W,$H --virtual-time-budget=4000 --screenshot=$OUT "$SRC" 2>/dev/null
fi
