#!/bin/zsh
cd -- "$(dirname "$0")" || exit 1
python3 scripts/blog.py publish
read -r "?엔터를 누르면 창을 닫습니다."

