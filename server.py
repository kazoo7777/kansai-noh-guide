#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PCおよび同じWi-Fi内のiPhoneから能公演まとめサイトを閲覧するための簡易Webサーバー。
起動すると、PC用URLとiPhone用アクセスURLを表示します。
"""

import http.server
import os
import socket
import socketserver
from pathlib import Path

PORT = 8000
ROOT_DIR = Path(__file__).resolve().parent


def get_local_ip() -> str:
    """同じWi-Fi（LAN）内で使われているローカルIPアドレスを取得します。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """キャッシュを抑えて更新データをすぐ反映するHTTPハンドラ。"""

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()


def main():
    os.chdir(ROOT_DIR)
    local_ip = get_local_ip()

    with socketserver.TCPServer(("0.0.0.0", PORT), QuietHandler) as httpd:
        print("=" * 56)
        print("  関西・全国 能楽公演ガイド サーバーを起動しました")
        print("=" * 56)
        print(f"  PCで開く     : http://localhost:{PORT}/")
        print(f"  iPhoneで開く : http://{local_ip}:{PORT}/")
        print("  （※iPhoneはPCと同じWi-Fiに接続してください）")
        print("  終了するときは Ctrl + C を押してください。")
        print("=" * 56)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nサーバーを終了しました。")


if __name__ == "__main__":
    main()
