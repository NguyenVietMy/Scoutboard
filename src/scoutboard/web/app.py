"""FastAPI app for the local Scoutboard UI (MVP.md §Local Web UI).

Server-rendered, thin, no build step. Prioritizes the cluster inbox, evidence
review, brief generation, digest review, and minimal source config.
"""

from __future__ import annotations

from pathlib import Path

import markdown as md
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from scoutboard.briefs.digest import generate_digest
from scoutboard.briefs.evidence import gather_cluster_evidence
from scoutboard.briefs.generator import generate_brief
from scoutboard.config import get_settings
from scoutboard.db import get_session, init_db
from scoutboard.models import ClusterState, Source
from scoutboard.web import service

_BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE / "templates"))


def create_app() -> FastAPI:
    init_db()  # ensure schema exists when served standalone
    app = FastAPI(title="Scoutboard")
    app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def inbox(
        request: Request,
        source: str | None = None,
        intent: str | None = None,
        state: str | None = None,
        tool: str | None = None,
        tag: str | None = None,
        min_count: int = 1,
        within_days: int | None = None,
        has_brief: str | None = None,
        sort: str = "recent",
    ):
        filters = service.Filters(
            source=source or None,
            intent=intent or None,
            state=state or None,
            tool=tool or None,
            tag=tag or None,
            min_count=min_count,
            within_days=within_days or None,
            has_brief=has_brief or None,
            sort=sort,
        )
        with get_session() as session:
            # Build the unfiltered set once for facet lists, then filter.
            all_rows = service.list_clusters(session, service.Filters())
            rows = service.list_clusters(session, filters)
        return templates.TemplateResponse(
            request,
            "clusters.html",
            {
                "rows": rows,
                "filters": filters,
                "sorts": service.SORTS,
                "sources": service.all_sources(all_rows),
                "intents": service.all_intents(all_rows),
                "tags": service.all_tags(all_rows),
                "states": [s.value for s in ClusterState],
                "has_ai": get_settings().has_ai,
            },
        )

    @app.get("/clusters/{cluster_id}", response_class=HTMLResponse)
    def cluster_detail(request: Request, cluster_id: int):
        with get_session() as session:
            pack = gather_cluster_evidence(session, cluster_id)
            brief = service.latest_brief(session, cluster_id)
            brief_html = md.markdown(brief.markdown) if brief else None
        if pack is None:
            return HTMLResponse("Cluster not found", status_code=404)
        return templates.TemplateResponse(
            request,
            "cluster_detail.html",
            {
                "pack": pack,
                "cluster": pack.cluster,
                "brief_html": brief_html,
                "states": [s.value for s in ClusterState],
                "has_ai": get_settings().has_ai,
            },
        )

    @app.post("/clusters/{cluster_id}/brief")
    def make_brief(cluster_id: int, rules_only: str | None = Form(None)):
        use_ai = not (rules_only or not get_settings().has_ai)
        with get_session() as session:
            generate_brief(session, cluster_id, use_ai=use_ai)
        return RedirectResponse(f"/clusters/{cluster_id}", status_code=303)

    @app.post("/clusters/{cluster_id}/state")
    def set_state(cluster_id: int, state: str = Form(...)):
        from scoutboard.models import Cluster

        with get_session() as session:
            cluster = session.get(Cluster, cluster_id)
            if cluster and state in {s.value for s in ClusterState}:
                cluster.state = state
                session.add(cluster)
                session.commit()
        return RedirectResponse(f"/clusters/{cluster_id}", status_code=303)

    @app.get("/digest", response_class=HTMLResponse)
    def digest_view(request: Request, days: int = 7):
        with get_session() as session:
            markdown_text = generate_digest(session, days=days)
        return templates.TemplateResponse(
            request,
            "digest.html",
            {"digest_html": md.markdown(markdown_text), "days": days},
        )

    @app.get("/sources", response_class=HTMLResponse)
    def sources_view(request: Request):
        with get_session() as session:
            sources = session.exec(select(Source)).all()
        return templates.TemplateResponse(request, "sources.html", {"sources": sources})

    @app.post("/sources")
    def add_source(
        kind: str = Form(...),
        feed: str = Form("story"),
        repo: str = Form(""),
        url: str = Form(""),
        limit: int = Form(50),
    ):
        kind = kind.lower()
        if kind == "hn":
            config = {"feed": feed, "limit": limit}
        elif kind == "rss" and url:
            config = {"url": url, "limit": limit}
        elif kind == "github" and repo:
            config = {"repo": repo, "limit": limit}
        else:
            return RedirectResponse("/sources", status_code=303)
        with get_session() as session:
            session.add(Source(kind=kind, config=config))
            session.commit()
        return RedirectResponse("/sources", status_code=303)

    return app


app = create_app()
