#!/usr/bin/env bash
# Usage: sidebyside.sh <before.mp4> <after.mp4> "<before label>" "<after label>" <out.mp4>
# Labelled side-by-side video; the shorter side holds its last frame until the longer one ends.
set -euo pipefail
before="$1"; after="$2"; label_b="$3"; label_a="$4"; out="$5"
W=540; H=64
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# Homebrew's ffmpeg has no drawtext filter, so the labels are drawn with AppKit.
osascript -l JavaScript "$(dirname "$0")/label.js" "$label_b" "$tmp/b.png" $W $H
osascript -l JavaScript "$(dirname "$0")/label.js" "$label_a" "$tmp/a.png" $W $H

dur() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }
db="$(dur "$before")"; da="$(dur "$after")"
pad_b="$(awk -v a="$da" -v b="$db" 'BEGIN{d=a-b; print (d>0?d:0)}')"
pad_a="$(awk -v a="$da" -v b="$db" 'BEGIN{d=b-a; print (d>0?d:0)}')"

side() { # input-index label-index pad-seconds out-label
  echo "[$1:v]fps=30,scale=$W:-2,setsar=1,tpad=stop_mode=clone:stop_duration=$3,pad=$W:ih+$H:0:$H:color=0x1a1a1a[p$1];[p$1][$2:v]overlay=0:0[$4]"
}

ffmpeg -v error -y -i "$before" -i "$after" -i "$tmp/b.png" -i "$tmp/a.png" \
  -filter_complex "$(side 0 2 "$pad_b" L);$(side 1 3 "$pad_a" R);[L][R]hstack=inputs=2[v]" \
  -map "[v]" -c:v libx264 -preset veryfast -crf 28 -pix_fmt yuv420p -movflags +faststart -an "$out"
echo "$out"
