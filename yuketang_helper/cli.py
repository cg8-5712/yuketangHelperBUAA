"""Interactive command line entry point."""

import argparse
from pathlib import Path

from .logging import DEBUG, debug, log
from .platform.auth import extract_specific_cookies, getCookies, getUniversityId
from .platform.client import PlatformClient, PlatformError
from .platform.courses import CourseAPI
from .ui import ask_text, choose
from .workflows.homework import homeworkHelper
from .workflows.video import VideoTaskError, videoHelper


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def build_headers(cookies, university_id):
    csrftoken, sessionid = extract_specific_cookies(cookies)
    if not csrftoken or not sessionid:
        raise ValueError("Cookie 缺少 csrftoken 或 sessionid，请重新登录")
    return {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Cookie": f"csrftoken={csrftoken}; sessionid={sessionid}; university_id={university_id}; platform_id=3",
        "x-csrftoken": csrftoken,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "university-id": university_id,
        "xtbz": "cloud",
    }


def main():
    parser = argparse.ArgumentParser(description="雨课堂助手")
    parser.add_argument("--debug", action="store_true", help="打印心跳、响应和媒体信息")
    args = parser.parse_args()
    DEBUG = args.debug
    domain = ask_text("雨课堂域名", "aibuaa.yuketang.cn")
    filename = ask_text("Cookie 文件名（不含 .txt）", "cookies")
    from .config import PROJECT_ROOT
    cookie_path = Path(filename + ".txt")
    if not cookie_path.is_absolute():
        cookie_path = PROJECT_ROOT / cookie_path
    use_cached = choose(
        "登录方式", ["扫码登录", "读取已有 Cookie 文件"],
        default=1 if cookie_path.is_file() else 0,
    ) == 1
    university_id = str(getUniversityId(domain))
    cookies = getCookies(
        domain, use_cached=use_cached, filename=filename, university_id=university_id
    )
    headers = build_headers(cookies, university_id)
    client = PlatformClient(domain, university_id, headers)
    try:
        session = client.get_json("/edu_admin/check_user_session/")
        user_id = str((session.get("data") or session)["user_id"])
    except (PlatformError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("获取 user_id 失败，请检查登录状态和网络") from exc

    courses = CourseAPI(client).list()
    if not courses:
        log("没有可用课程")
        return
    try:
        info = client.get_json("/edu_admin/get_user_basic_info/")
        log(f"欢迎您，{info['data']['user_info']['name']}")
    except (PlatformError, KeyError, TypeError):
        log("获取用户信息失败，继续选择课程", level="Warning")

    if DEBUG:
        debug("university_id =", university_id)
        debug("user_id =", user_id)
    course_index = choose("选择课程", ["全部课程"] + [course.course_name for course in courses])
    selected = courses if course_index == 0 else [courses[course_index - 1]]
    do_homework = choose("作业", ["跳过", "使用 AI 答题"]) == 1
    homework = None
    if do_homework:
        api_choice = choose("AI 接口", ["Chat Completions", "Responses"])
        homework = homeworkHelper(
            domain, cookies, user_id, university_id, headers,
            api_mode="responses" if api_choice == 1 else "chat_completions",
            client=client,
        )

    video = videoHelper(domain, cookies, user_id, university_id, 12, headers, client=client, debug=args.debug)
    all_complete = True
    for course in selected:
        videos = video.get_videos_ids(course.course_name, course.classroom_id, course.course_sign)
        try:
            complete = video.multiple_watch_video(
                videos, course.course_id, user_id, course.classroom_id, course.sku_id,
                course_name=course.course_name,
            )
        except VideoTaskError as exc:
            log(f"{course.course_name} 视频任务已停止：{exc}", level="Error")
            raise SystemExit(1) from None
        all_complete = all_complete and complete
    if homework is not None:
        for course in selected:
            complete = homework.do_homework(
                course.classroom_id, course.course_sign, course.course_name
            )
            all_complete = all_complete and complete
    log("全部任务完成" if all_complete else "任务结束，部分内容未完成",
        level="Info" if all_complete else "Warning")


if __name__ == "__main__":
    main()
