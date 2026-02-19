"""
TrendOrchestrator - LangGraph 状态图编排引擎

工作流:
  START -> scraping -> categorizing -> summarizing -> quality_checking
                                                          |
                                            +---------+---+---------+
                                       (需要视频)              (不需要)
                                            |                    |
                                      video_generating      publishing
                                            |                    |
                                            +--> publishing      |
                                                     |           |
                                                     +--> completed -> END
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from trend_agent.agents.base import BaseAgent
from trend_agent.agents.scraper_agent import ScraperAgent
from trend_agent.agents.categorizer_agent import CategorizerAgent
from trend_agent.agents.summarizer_agent import SummarizerAgent
from trend_agent.agents.quality_agent import QualityAgent
from trend_agent.models.message import AgentMessage
from trend_agent.models.state_machine import WorkflowState
from trend_agent.observability import metrics as obs
from trend_agent.services.llm_client import LLMServiceClient
from trend_agent.services.content_store import ContentRepository
from trend_agent.services.parse_service import ParseService

logger = logging.getLogger(__name__)

# Optional LangGraph
try:
    from langgraph.graph import StateGraph, START, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.info("LangGraph not available, using sequential fallback")


class PipelineState(TypedDict, total=False):
    pipeline_id: str
    trace_id: str
    sources: List[str]
    categories_filter: List[str]
    target_platforms: List[str]
    generate_video: bool
    video_provider: str
    max_items: int
    query: str
    capture_mode: str
    start_time: str
    end_time: str
    sort_strategy: str
    trigger_type: str

    raw_items: List[Dict]
    categorized_items: List[Dict]
    drafts: List[Dict]
    quality_results: List[Dict]
    video_results: List[Dict]
    publish_results: List[Dict]

    timing: Dict[str, float]
    state_history: List[str]
    current_state: str
    error: str


class TrendOrchestrator:
    """LangGraph 状态图编排引擎 + 顺序执行回退"""

    def __init__(self):
        self._llm = LLMServiceClient()
        self._content_store = ContentRepository()
        self._scraper_agent = ScraperAgent(self._llm, content_store=self._content_store)
        self._parse_service = ParseService(self._content_store, self._llm)
        self._categorizer_agent = CategorizerAgent(self._llm)
        self._summarizer_agent = SummarizerAgent(self._llm)
        self._quality_agent = QualityAgent(self._llm)
        self._video_agent: Optional[BaseAgent] = None
        self._publisher_agent: Optional[BaseAgent] = None
        self._graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

    async def startup(self):
        """Initialize all sub-agents."""
        await self._content_store.init_db()
        await self._scraper_agent.startup()
        await self._quality_agent.startup()
        # Lazy import video and publisher agents
        try:
            from trend_agent.agents.video_agent import VideoAgent
            self._video_agent = VideoAgent(self._llm)
            await self._video_agent.startup()
        except ImportError:
            logger.info("VideoAgent not available")
        try:
            from trend_agent.agents.publisher_agent import PublisherAgent
            self._publisher_agent = PublisherAgent()
            await self._publisher_agent.startup()
        except ImportError:
            logger.info("PublisherAgent not available")

    async def shutdown(self):
        await self._scraper_agent.shutdown()
        if self._video_agent:
            await self._video_agent.shutdown()
        if self._publisher_agent:
            await self._publisher_agent.shutdown()
        await self._llm.close()
        await self._content_store.close()

    def _build_graph(self):
        """Build LangGraph state graph."""
        builder = StateGraph(PipelineState)

        builder.add_node("scraping", self._node_scraping)
        builder.add_node("categorizing", self._node_categorizing)
        builder.add_node("summarizing", self._node_summarizing)
        builder.add_node("quality_checking", self._node_quality_checking)
        builder.add_node("video_generating", self._node_video_generating)
        builder.add_node("publishing", self._node_publishing)
        builder.add_node("completed", self._node_completed)

        builder.add_edge(START, "scraping")
        builder.add_edge("scraping", "categorizing")
        builder.add_edge("categorizing", "summarizing")
        builder.add_edge("summarizing", "quality_checking")
        builder.add_conditional_edges(
            "quality_checking",
            self._route_after_quality,
            {"video_generating": "video_generating", "publishing": "publishing"},
        )
        builder.add_edge("video_generating", "publishing")
        builder.add_edge("publishing", "completed")
        builder.add_edge("completed", END)

        return builder.compile()

    def _route_after_quality(self, state: PipelineState) -> str:
        if state.get("generate_video") and self._video_agent:
            return "video_generating"
        return "publishing"

    # --- Graph Nodes ---

    async def _node_scraping(self, state: PipelineState) -> Dict:
        start = time.perf_counter()
        msg = AgentMessage(payload={
            "sources": state.get("sources", []),
            "query": state.get("query"),
            "limit": state.get("max_items", 50),
            "capture_mode": state.get("capture_mode", "hybrid"),
            "start_time": state.get("start_time"),
            "end_time": state.get("end_time"),
            "sort_strategy": state.get("sort_strategy", "hybrid"),
        }, trace_id=state.get("trace_id", ""))
        result = await self._scraper_agent(msg)
        items = result.payload.get("items", [])

        # Persist sources to DB
        for item in items:
            enriched_raw = item.get("raw_data", {}) or {}
            enriched_raw["_normalized"] = {
                "normalized_text": item.get("normalized_text", ""),
                "hashtags": item.get("hashtags", []),
                "mentions": item.get("mentions", []),
                "external_urls": item.get("external_urls", []),
                "media_assets": item.get("media_assets", []),
                "multimodal": item.get("multimodal", {}),
                "normalized_heat_score": item.get("normalized_heat_score", 0.0),
                "heat_breakdown": item.get("heat_breakdown", {}),
                "published_at": item.get("published_at", ""),
                "platform_metrics": item.get("platform_metrics", {}),
            }
            source_row_id = await self._content_store.upsert_source({
                "source_platform": item.get("source_platform"),
                "source_channel": item.get("source_channel") or item.get("source_platform", ""),
                "source_type": item.get("source_type") or "post",
                "source_id": item.get("source_id"),
                "source_url": item.get("source_url", ""),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "author": item.get("author", ""),
                "author_id": item.get("author_id", ""),
                "language": item.get("language", "zh"),
                "engagement_score": item.get("engagement_score", 0),
                "normalized_heat_score": item.get("normalized_heat_score", 0.0),
                "heat_breakdown": item.get("heat_breakdown", {}),
                "capture_mode": state.get("capture_mode", "hybrid"),
                "sort_strategy": state.get("sort_strategy", "hybrid"),
                "published_at": item.get("published_at", ""),
                "source_updated_at": item.get("published_at", ""),
                "normalized_text": item.get("normalized_text", ""),
                "hashtags": item.get("hashtags", []),
                "mentions": item.get("mentions", []),
                "external_urls": item.get("external_urls", []),
                "media_urls": item.get("media_urls", []),
                "media_assets": item.get("media_assets", []),
                "multimodal": item.get("multimodal", {}),
                "platform_metrics": item.get("platform_metrics", {}),
                "pipeline_run_id": state.get("pipeline_id", ""),
                "raw_data": enriched_raw,
                "scraped_at": item.get("scraped_at", ""),
                "content_hash": item.get("content_hash", ""),
            })
            try:
                await self._parse_service.parse_source_by_row_id(source_row_id)
            except Exception as e:
                logger.warning("parse stage failed for source_row_id=%s: %s", source_row_id, e)

        return {
            "raw_items": items,
            "current_state": WorkflowState.SCRAPING.value,
            "state_history": state.get("state_history", []) + [WorkflowState.SCRAPING.value],
            "timing": {**state.get("timing", {}), "scraping_ms": (time.perf_counter() - start) * 1000},
        }

    async def _node_categorizing(self, state: PipelineState) -> Dict:
        start = time.perf_counter()
        items = state.get("raw_items", [])
        msg = AgentMessage(payload={"items": items}, trace_id=state.get("trace_id", ""))
        result = await self._categorizer_agent(msg)
        categorized = result.payload.get("items", [])

        # Filter by categories if specified
        cat_filter = state.get("categories_filter", [])
        if cat_filter:
            categorized = [i for i in categorized if i.get("category") in cat_filter]

        # Persist categorization
        for item in categorized:
            await self._content_store.save_categorized({
                "source_id": item.get("item_id", ""),
                "category": item.get("category", "其他"),
                "subcategory": item.get("subcategory", ""),
                "confidence": item.get("confidence", 0),
                "tags": item.get("tags", []),
            })

        return {
            "categorized_items": categorized,
            "current_state": WorkflowState.CATEGORIZING.value,
            "state_history": state.get("state_history", []) + [WorkflowState.CATEGORIZING.value],
            "timing": {**state.get("timing", {}), "categorizing_ms": (time.perf_counter() - start) * 1000},
        }

    async def _node_summarizing(self, state: PipelineState) -> Dict:
        start = time.perf_counter()
        items = state.get("categorized_items", [])
        platforms = state.get("target_platforms", ["wechat"])
        msg = AgentMessage(
            payload={"items": items, "target_platforms": platforms},
            trace_id=state.get("trace_id", ""),
        )
        result = await self._summarizer_agent(msg)
        drafts = result.payload.get("drafts", [])

        # Persist drafts
        for draft in drafts:
            await self._content_store.save_draft({
                "source_id": draft.get("source_item_id", ""),
                "target_platform": draft.get("target_platform", ""),
                "title": draft.get("title", ""),
                "body": draft.get("body", ""),
                "summary": draft.get("summary", ""),
                "hashtags": draft.get("hashtags", []),
                "media_urls": draft.get("media_urls", []),
                "language": draft.get("language", "zh"),
                "status": "summarized",
            })

        return {
            "drafts": drafts,
            "current_state": WorkflowState.SUMMARIZING.value,
            "state_history": state.get("state_history", []) + [WorkflowState.SUMMARIZING.value],
            "timing": {**state.get("timing", {}), "summarizing_ms": (time.perf_counter() - start) * 1000},
        }

    async def _node_quality_checking(self, state: PipelineState) -> Dict:
        start = time.perf_counter()
        drafts = state.get("drafts", [])
        msg = AgentMessage(payload={"drafts": drafts}, trace_id=state.get("trace_id", ""))
        result = await self._quality_agent(msg)

        return {
            "drafts": result.payload.get("drafts", []),
            "quality_results": result.payload.get("quality_results", []),
            "current_state": WorkflowState.QUALITY_CHECKING.value,
            "state_history": state.get("state_history", []) + [WorkflowState.QUALITY_CHECKING.value],
            "timing": {**state.get("timing", {}), "quality_ms": (time.perf_counter() - start) * 1000},
        }

    async def _node_video_generating(self, state: PipelineState) -> Dict:
        start = time.perf_counter()
        drafts = state.get("drafts", [])
        video_results = []

        if self._video_agent:
            passed_drafts = [d for d in drafts if d.get("quality_passed")]
            for draft in passed_drafts[:5]:  # Limit video generation
                msg = AgentMessage(
                    payload={
                        "draft": draft,
                        "provider": state.get("video_provider", ""),
                    },
                    trace_id=state.get("trace_id", ""),
                )
                result = await self._video_agent(msg)
                if not result.has_error:
                    video_results.append(result.payload)
                    # Update draft with video URL
                    draft["video_url"] = result.payload.get("video_url", "")
                    draft["video_provider"] = result.payload.get("provider", "")

        return {
            "video_results": video_results,
            "drafts": drafts,
            "current_state": WorkflowState.VIDEO_GENERATING.value,
            "state_history": state.get("state_history", []) + [WorkflowState.VIDEO_GENERATING.value],
            "timing": {**state.get("timing", {}), "video_ms": (time.perf_counter() - start) * 1000},
        }

    async def _node_publishing(self, state: PipelineState) -> Dict:
        start = time.perf_counter()
        drafts = state.get("drafts", [])
        publish_results = []

        passed_drafts = [d for d in drafts if d.get("quality_passed")]

        if self._publisher_agent and passed_drafts:
            msg = AgentMessage(
                payload={"drafts": passed_drafts},
                trace_id=state.get("trace_id", ""),
            )
            result = await self._publisher_agent(msg)
            publish_results = result.payload.get("publish_results", [])

            # Persist publish records
            for pr in publish_results:
                await self._content_store.save_publish_record({
                    "draft_id": pr.get("draft_id", ""),
                    "platform": pr.get("platform", ""),
                    "platform_post_id": pr.get("platform_post_id", ""),
                    "platform_url": pr.get("platform_url", ""),
                    "status": "success" if pr.get("success") else "failed",
                    "error_message": pr.get("error", ""),
                })

        return {
            "publish_results": publish_results,
            "current_state": WorkflowState.PUBLISHING.value,
            "state_history": state.get("state_history", []) + [WorkflowState.PUBLISHING.value],
            "timing": {**state.get("timing", {}), "publishing_ms": (time.perf_counter() - start) * 1000},
        }

    async def _node_completed(self, state: PipelineState) -> Dict:
        return {
            "current_state": WorkflowState.COMPLETED.value,
            "state_history": state.get("state_history", []) + [WorkflowState.COMPLETED.value],
        }

    # --- Public API ---

    async def run_pipeline(
        self,
        sources: List[str],
        categories_filter: List[str] = None,
        target_platforms: List[str] = None,
        generate_video: bool = False,
        video_provider: str = "",
        max_items: int = 50,
        query: str = "",
        capture_mode: str = "hybrid",
        start_time: str = "",
        end_time: str = "",
        sort_strategy: str = "hybrid",
        trigger_type: str = "manual",
    ) -> str:
        """Run the full pipeline. Returns pipeline_run_id."""
        pipeline_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        initial_state: PipelineState = {
            "pipeline_id": pipeline_id,
            "trace_id": trace_id,
            "sources": sources,
            "categories_filter": categories_filter or [],
            "target_platforms": target_platforms or ["wechat"],
            "generate_video": generate_video,
            "video_provider": video_provider,
            "max_items": max_items,
            "query": query,
            "capture_mode": capture_mode,
            "start_time": start_time,
            "end_time": end_time,
            "sort_strategy": sort_strategy,
            "trigger_type": trigger_type,
            "raw_items": [],
            "categorized_items": [],
            "drafts": [],
            "quality_results": [],
            "video_results": [],
            "publish_results": [],
            "timing": {},
            "state_history": [],
            "current_state": WorkflowState.INIT.value,
            "error": "",
        }

        # Create pipeline run record
        await self._content_store.create_pipeline_run({
            "id": pipeline_id,
            "trigger_type": trigger_type,
            "config": {
                "sources": sources,
                "categories_filter": categories_filter or [],
                "target_platforms": target_platforms or ["wechat"],
                "generate_video": generate_video,
                "max_items": max_items,
                "query": query,
                "capture_mode": capture_mode,
                "start_time": start_time,
                "end_time": end_time,
                "sort_strategy": sort_strategy,
            },
            "status": "running",
        })

        pipeline_start = time.perf_counter()

        try:
            if self._graph:
                # LangGraph execution
                final_state = await self._graph.ainvoke(initial_state)
            else:
                # Sequential fallback
                final_state = await self._run_sequential(initial_state)

            elapsed = time.perf_counter() - pipeline_start
            obs.record_pipeline(trigger_type, "completed", elapsed)

            # Update pipeline run
            drafts = final_state.get("drafts", [])
            published = final_state.get("publish_results", [])
            await self._content_store.update_pipeline_run(pipeline_id, {
                "status": "completed",
                "items_scraped": len(final_state.get("raw_items", [])),
                "items_published": sum(1 for p in published if p.get("success")),
                "items_rejected": sum(1 for d in drafts if not d.get("quality_passed")),
                "completed_at": datetime.now(timezone.utc),
                "state_history": final_state.get("state_history", []),
                "timing": final_state.get("timing", {}),
            })

        except Exception as e:
            logger.error("Pipeline failed: %s", e, exc_info=True)
            elapsed = time.perf_counter() - pipeline_start
            obs.record_pipeline(trigger_type, "failed", elapsed)
            await self._content_store.update_pipeline_run(pipeline_id, {
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc),
            })

        return pipeline_id

    async def _run_sequential(self, state: PipelineState) -> PipelineState:
        """Sequential fallback when LangGraph is not available."""
        state = {**state, **(await self._node_scraping(state))}
        state = {**state, **(await self._node_categorizing(state))}
        state = {**state, **(await self._node_summarizing(state))}
        state = {**state, **(await self._node_quality_checking(state))}

        if state.get("generate_video") and self._video_agent:
            state = {**state, **(await self._node_video_generating(state))}

        if self._publisher_agent:
            state = {**state, **(await self._node_publishing(state))}

        state = {**state, **(await self._node_completed(state))}
        return state

    def info(self) -> Dict:
        return {
            "langgraph_available": LANGGRAPH_AVAILABLE,
            "graph_compiled": self._graph is not None,
            "scrapers": list(self._scraper_agent._scrapers.keys()) if self._scraper_agent._initialized else [],
            "video_agent": self._video_agent is not None,
            "publisher_agent": self._publisher_agent is not None,
        }


# Singleton
_orchestrator: Optional[TrendOrchestrator] = None


def get_orchestrator() -> TrendOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TrendOrchestrator()
    return _orchestrator
