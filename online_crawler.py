from datetime import datetime, timedelta

from config import load_body_keywords, load_exclude_keywords
from database import Database
from naver_api import NaverNewsApiClient
from rss_crawler import RssCrawler


def default_online_window(now: datetime | None = None):
    end_dt = now or datetime.now()
    start_dt = end_dt - timedelta(hours=4)
    return start_dt, end_dt


def online_run_key(start_dt: datetime, end_dt: datetime) -> str:
    return f"online:{start_dt:%Y%m%d%H%M}:{end_dt:%Y%m%d%H%M}"


def crawl_online_candidates(
    db: Database | None = None,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
    exclude_keywords: list[str] | None = None,
) -> dict:
    db = db or Database()
    if start_dt is None or end_dt is None:
        start_dt, end_dt = default_online_window()
    run_key = online_run_key(start_dt, end_dt)
    if db.crawl_run_completed(run_key):
        return {
            "rss": {"total": 0, "inserted": 0, "errors": []},
            "api": {"total": 0, "inserted": 0, "failures": []},
            "total": 0,
            "inserted": 0,
            "errors": [],
            "start_dt": start_dt,
            "end_dt": end_dt,
            "skipped": True,
        }

    db.start_crawl_run(run_key)
    try:
        rss_result = RssCrawler(db).crawl_all()
        api = NaverNewsApiClient(db)
        if api.available():
            api_result = api.collect_fallback_outlets(
                load_body_keywords(),
                start_dt,
                end_dt,
                exclude_keywords=exclude_keywords if exclude_keywords is not None else load_exclude_keywords(),
            )
        else:
            api_result = {"total": 0, "inserted": 0, "failures": ["네이버 API 키가 없습니다."]}
    except Exception as exc:
        db.finish_crawl_run(run_key, "failed", error=str(exc))
        raise

    errors = list(rss_result.get("errors", []))
    errors.extend(api_result.get("failures", []))
    result = {
        "rss": rss_result,
        "api": api_result,
        "total": rss_result.get("total", 0) + api_result.get("total", 0),
        "inserted": (
            rss_result.get("inserted", 0)
            + api_result.get("inserted", 0)
        ),
        "errors": errors,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "skipped": False,
    }
    db.finish_crawl_run(
        run_key,
        "completed" if not errors else "failed",
        total=result["total"],
        inserted=result["inserted"],
        error="\n".join(errors) if errors else None,
    )
    return result
