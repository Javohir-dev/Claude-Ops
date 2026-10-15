import config as cfg
from providers import github, gitlab, jira

REVIEW_HOSTS = {"gitlab": gitlab, "github": github}


def review_host():
    return REVIEW_HOSTS.get(cfg.get("review.host") or "gitlab", gitlab)


def tracker():
    chosen = cfg.get("tasks.tracker")
    if chosen:
        return chosen
    return "jira" if cfg.secret("jira.token") else "none"


__all__ = ["github", "gitlab", "jira", "review_host", "tracker"]
