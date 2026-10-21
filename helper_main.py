"""CLI by default; local WebUI with --webui."""

import argparse


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="雨课堂助手")
    parser.add_argument("--webui", action="store_true", help="启动本地网页管理界面")
    args = parser.parse_args()
    if args.webui:
        from yuketang_helper.web import run_webui
        run_webui()
    else:
        from yuketang_helper.cli import main
        main()
