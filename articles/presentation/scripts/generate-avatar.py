"""GitHub アバターを取得して円形透過 PNG に変換する。

iPad などの一部 PDF ビューアは CSS の `border-radius: 50%` クリップを正しく
再現できず、矩形の背景が見えてしまうことがある。Marp スライドに埋め込む際は
画像自体を円形にマスクした透過 PNG として配置することで、ビューア差異を回避する。

Usage:
    python generate-avatar.py <github_user_id> <output_path> [--size N]

例:
    python generate-avatar.py 16248836 avatar.png
    python generate-avatar.py 16248836 avatar.png --size 400
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from io import BytesIO

from PIL import Image, ImageDraw, UnidentifiedImageError

HTTP_TIMEOUT_SECONDS = 10
MIN_AVATAR_SIZE = 1
MAX_AVATAR_SIZE = 2048


def fetch_avatar(user_id: int, request_size: int) -> Image.Image:
    url = f"https://avatars.githubusercontent.com/u/{user_id}?v=4&size={request_size}"
    req = urllib.request.Request(url, headers={"User-Agent": "article-writer/generate-avatar"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        data = response.read()
    try:
        return Image.open(BytesIO(data)).convert("RGBA")
    except UnidentifiedImageError as exc:
        raise SystemExit(
            f"error: 取得したデータが画像として読み込めませんでした。"
            f"ユーザー ID ({user_id}) が存在するか確認してください: {exc}"
        ) from exc


def crop_center_square(img: Image.Image) -> Image.Image:
    size = min(img.size)
    left = (img.width - size) // 2
    top = (img.height - size) // 2
    return img.crop((left, top, left + size, top + size))


def apply_circle_mask(img: Image.Image) -> Image.Image:
    size = img.size[0]
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id", type=int, help="GitHub の数値ユーザー ID")
    parser.add_argument("output", help="出力 PNG のパス")
    parser.add_argument(
        "--size",
        type=int,
        default=480,
        help=f"取得する画像のピクセルサイズ（{MIN_AVATAR_SIZE}〜{MAX_AVATAR_SIZE}、デフォルト: 480）",
    )
    args = parser.parse_args()

    if not (MIN_AVATAR_SIZE <= args.size <= MAX_AVATAR_SIZE):
        parser.error(
            f"--size は {MIN_AVATAR_SIZE}〜{MAX_AVATAR_SIZE} の範囲で指定してください（指定値: {args.size}）"
        )

    img = fetch_avatar(args.user_id, args.size)
    img = crop_center_square(img)
    img = apply_circle_mask(img)
    img.save(args.output)
    print(f"saved {args.output} ({img.size[0]}x{img.size[1]})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
