"""pytest ルート設定 — リポジトリルートを sys.path に追加して scripts/ をimport可能にする。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
