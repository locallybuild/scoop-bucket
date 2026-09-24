"""Read or rewrite bucket/locally.json for the scoop-bucket update workflow."""

import argparse
import json
from pathlib import Path

ARCHES = ("64bit", "arm64")
ARCH_TO_PLATFORM = {"64bit": "windows/amd64", "arm64": "windows/arm64"}
PLATFORMS = tuple(ARCH_TO_PLATFORM[a] for a in ARCHES)


def parse_manifest(content: str) -> dict:
    data = json.loads(content)
    if "version" not in data:
        raise ValueError("version field not found in manifest")
    if "architecture" not in data:
        raise ValueError("architecture field not found in manifest")

    shas: dict = {}
    for arch in ARCHES:
        block = data["architecture"].get(arch)
        if not block or "hash" not in block:
            raise ValueError(f"hash for architecture {arch} not found")
        shas[ARCH_TO_PLATFORM[arch]] = block["hash"]

    return {"version": data["version"], "shas": shas}


def write_manifest(content: str, new_version: str, new_shas: dict) -> str:
    data = json.loads(content)
    autoupdate_archs = data.get("autoupdate", {}).get("architecture", {})

    for arch in ARCHES:
        platform = ARCH_TO_PLATFORM[arch]
        if platform not in new_shas:
            raise ValueError(f"new sha for platform {platform} not provided")
        if arch not in data.get("architecture", {}):
            raise ValueError(f"architecture {arch} not found in manifest")

        template = autoupdate_archs.get(arch, {}).get("url")
        if not template or "$version" not in template:
            raise ValueError(
                f"autoupdate url template with $version for {arch} not found"
            )

        data["architecture"][arch]["url"] = template.replace("$version", new_version)
        data["architecture"][arch]["hash"] = new_shas[platform]

    data["version"] = new_version
    return json.dumps(data, indent=4) + "\n"


def cmd_read(args: argparse.Namespace) -> None:
    content = Path(args.manifest).read_text()
    parsed = parse_manifest(content)
    print(json.dumps(parsed))


def cmd_write(args: argparse.Namespace) -> None:
    path = Path(args.manifest)
    content = path.read_text()
    new_shas = {
        "windows/amd64": args.sha_windows_amd64,
        "windows/arm64": args.sha_windows_arm64,
    }
    new_content = write_manifest(content, args.version, new_shas)
    path.write_text(new_content)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="update_manifest")
    subs = parser.add_subparsers(dest="cmd", required=True)

    read_p = subs.add_parser("read", help="Print current manifest state as JSON")
    read_p.add_argument("manifest", help="Path to bucket/locally.json")
    read_p.set_defaults(func=cmd_read)

    write_p = subs.add_parser("write", help="Rewrite manifest in place")
    write_p.add_argument("manifest", help="Path to bucket/locally.json")
    write_p.add_argument("--version", required=True)
    write_p.add_argument("--sha-windows-amd64", required=True)
    write_p.add_argument("--sha-windows-arm64", required=True)
    write_p.set_defaults(func=cmd_write)

    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    args.func(args)
