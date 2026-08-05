#!/bin/sh
printf '\033c\033]0;%s\a' Tanu
base_path="$(dirname "$(realpath "$0")")"
"$base_path/testing.x86_64" "$@"
