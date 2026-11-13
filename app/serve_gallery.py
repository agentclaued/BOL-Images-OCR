"""Serve the BOL Images homepage locally, with forced image downloads.

Run: python serve_gallery.py
Then open: http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


GALLERY_ROOT = Path(__file__).resolve().parent.parent / "BOL images"


class GalleryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(GALLERY_ROOT), **kwargs)

    def do_GET(self) -> None:
        request = urlparse(self.path)
        if request.path == "/download":
            requested = parse_qs(request.query).get("file", [""])[0]
            target = (GALLERY_ROOT / unquote(requested)).resolve()
            if not target.is_file() or GALLERY_ROOT.resolve() not in target.parents:
                self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(target.name)}")
            self.end_headers()
            with target.open("rb") as image_file:
                self.copyfile(image_file, self.wfile)
            return
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local BOL Images gallery.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    GALLERY_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), GalleryHandler)
    print(f"Open this in your browser: http://127.0.0.1:{args.port}")
    print("Press Ctrl+C to stop the gallery server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
