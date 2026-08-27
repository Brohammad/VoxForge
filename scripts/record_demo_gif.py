#!/usr/bin/env python3
"""Record /demo trust-loop flow to a WebM file for GIF conversion."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("VOXFORGE_DEMO_BASE_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            record_video_dir=str(args.output_dir),
            record_video_size={"width": args.width, "height": args.height},
        )
        page = context.new_page()
        page.goto(f"{args.base_url.rstrip('/')}/demo", wait_until="networkidle")

        trust_btn = page.get_by_role("button", name="Run trust loop")
        if trust_btn.is_disabled():
            print("ERROR: Demo disabled — set DEMO_ENABLED=true", file=sys.stderr)
            return 1

        trust_btn.click()
        page.locator("#out-status").wait_for(state="visible", timeout=40_000)
        page.locator("#out-status").filter(has_text="trust_loop_ok").wait_for(timeout=40_000)
        page.locator("#chat-log .chat-bubble.assistant").wait_for(timeout=10_000)
        page.locator("#citations").wait_for(state="visible", timeout=10_000)
        page.wait_for_timeout(1500)

        video = page.video
        page.close()
        context.close()

        if video is None:
            browser.close()
            print("ERROR: Playwright did not produce a video recording", file=sys.stderr)
            return 1

        dest = args.output_dir / "demo-recording.webm"
        video.save_as(str(dest))
        browser.close()
        print(dest)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
