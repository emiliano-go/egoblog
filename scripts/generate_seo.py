#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

import frontmatter
from seoslug import SEOConfig, SEOEntity, URLPolicy, build_seo_payload


def load_config(path: str) -> SEOConfig:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    url_policy_data = data.pop("url_policy", {})
    url_policy = URLPolicy(**url_policy_data)
    return SEOConfig(**data, url_policy=url_policy)


def route_for(md_path: Path, content_dir: Path) -> str:
    rel = md_path.relative_to(content_dir)
    parts = list(rel.parts)
    if parts[-1] in ("_index.md", "index.md"):
        parts.pop()
        route = "/" + "/".join(parts)
    else:
        stem = rel.stem
        parts[-1] = stem
        route = "/" + "/".join(parts)
    return route if route != "/" else "/"


def entity_type_for(md_path: Path) -> str:
    if md_path.name == "_index.md":
        if md_path.parent == md_path.root:
            return "home"
        return "page"
    return "post"


def main() -> None:
    config_path = os.environ.get("SEOSLUG_CONFIG", "seoslug-config.toml")
    config = load_config(config_path)

    content_dir = Path("content")
    data_dir = Path("data/seo")
    data_dir.mkdir(parents=True, exist_ok=True)

    for md_file in sorted(content_dir.rglob("*.md")):
        post = frontmatter.load(md_file)
        meta = post.metadata
        route = route_for(md_file, content_dir)

        entity = SEOEntity(
            entity_type=entity_type_for(md_file),
            slug=meta.get("slug"),
            title=meta.get("title"),
            excerpt=meta.get("description"),
            status="published",
        )

        payload = build_seo_payload(entity, route, config)

        key = str(md_file.relative_to(content_dir)).replace("/", "_").replace(".md", "")
        out_path = data_dir / f"{key}.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"  wrote  {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
