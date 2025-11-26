"""
Growth Engine 2.0 - Planner Agent
📋 "The Project Manager" - Creates actionable 90-day plan
Uses: generate_enhanced_90day_plan() from Enhanced_90day_plan.py
"""

import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .types import AnalysisContext, AgentPriority, InsightType

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    📋 Planner Agent - Project Manager
    
    Responsibilities:
    - Generate enhanced 90-day action plan
    - Prioritize actions by impact and effort
    - Create milestones and success metrics
    - Provide quick wins and long-term initiatives
    """
    
    def __init__(self):
        super().__init__(
            agent_id="planner",
            name="Planner",
            role="Project Manager",
            avatar="📋",
            personality="Practical organizer who turns strategy into action"
        )
        self.dependencies = ['analyst', 'strategist']
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Generate comprehensive 90-day action plan"""
        
        # Import the REAL function
        from Enhanced_90day_plan import generate_enhanced_90day_plan
        
        analyst_results = self.get_dependency_results(context, 'analyst')
        strategist_results = self.get_dependency_results(context, 'strategist')
        prospector_results = self.get_dependency_results(context, 'prospector')
        
        if not analyst_results:
            self._emit_insight(
                "⚠️ Missing analysis data — creating basic plan",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            return {'plan': None, 'quick_start': []}
        
        your_analysis = analyst_results.get('your_analysis', {})
        competitor_analyses = analyst_results.get('competitor_analyses', [])
        your_score = analyst_results.get('your_score', 0)
        
        # Get additional data
        recommendations = strategist_results.get('recommendations', []) if strategist_results else []
        market_gaps = prospector_results.get('market_gaps', []) if prospector_results else []
        
        self._emit_insight(
            "📋 Building your 90-day game plan...",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Calculate competitive gap data
        self._update_progress(15, "Analyzing competitive gap...")
        
        competitor_scores = [c.get('score', 50) for c in competitor_analyses]
        avg_competitor_score = sum(competitor_scores) / len(competitor_scores) if competitor_scores else your_score
        
        competitor_gap_data = {
            'avg_competitor_score': avg_competitor_score,
            'gap': avg_competitor_score - your_score,
            'your_rank': sum(1 for s in competitor_scores if s > your_score) + 1,
            'total_analyzed': len(competitor_scores) + 1,
            'market_gaps': market_gaps[:3]
        }
        
        gap = competitor_gap_data['gap']
        if gap > 15:
            self._emit_insight(
                f"📊 You're {gap:.0f} points behind the competition — plan will focus on catching up",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'gap': gap}
            )
        elif gap < -15:
            self._emit_insight(
                f"🏆 You're {abs(gap):.0f} points ahead — plan will focus on extending your lead",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'gap': gap}
            )
        else:
            self._emit_insight(
                f"🎯 Neck and neck with competitors — plan will focus on differentiation",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        
        # 2. Generate Enhanced 90-Day Plan
        self._update_progress(30, "Generating action plan...")
        
        try:
            basic = your_analysis.get('basic_analysis', {})
            content = your_analysis.get('detailed_analysis', {}).get('content_analysis', {})
            technical = your_analysis.get('detailed_analysis', {}).get('technical_audit', {})
            
            plan = generate_enhanced_90day_plan(
                basic=basic,
                content=content,
                technical=technical,
                language='en',
                competitor_gap=competitor_gap_data
            )
            
            # Convert plan to dict if it's a Pydantic model
            if hasattr(plan, 'dict'):
                plan_dict = plan.dict()
            elif hasattr(plan, 'model_dump'):
                plan_dict = plan.model_dump()
            else:
                plan_dict = plan
            
            # Extract summary
            summary = plan_dict.get('summary', {})
            total_actions = summary.get('total_actions', 0)
            
            self._emit_insight(
                f"✅ 90-day plan ready: {total_actions} actions across 3 phases",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'total_actions': total_actions}
            )
            
        except Exception as e:
            logger.error(f"[Planner] Enhanced plan generation failed: {e}")
            plan_dict = None
            self._emit_insight(
                f"⚠️ Plan generation limited: {str(e)}",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
        
        # 3. Extract Wave Summaries
        self._update_progress(60, "Organizing phases...")
        
        if plan_dict:
            # Wave 1: Foundation (Weeks 1-4)
            wave_1 = plan_dict.get('wave_1', [])
            if wave_1:
                self._emit_insight(
                    f"📦 Phase 1 (Weeks 1-4): {len(wave_1)} foundation actions",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING
                )
                
                # Emit first critical action from wave 1
                for action in wave_1:
                    if action.get('priority') == 'Critical':
                        self._emit_insight(
                            f"🔴 Week 1: {action.get('title', 'Unknown')} — {action.get('time_estimate', 'TBD')}",
                            priority=AgentPriority.HIGH,
                            insight_type=InsightType.RECOMMENDATION,
                            data=action
                        )
                        break
            
            # Wave 2: Content & SEO (Weeks 5-8)
            wave_2 = plan_dict.get('wave_2', [])
            if wave_2:
                self._emit_insight(
                    f"📝 Phase 2 (Weeks 5-8): {len(wave_2)} content & SEO actions",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING
                )
            
            # Wave 3: Scale (Weeks 9-12)
            wave_3 = plan_dict.get('wave_3', [])
            if wave_3:
                self._emit_insight(
                    f"🚀 Phase 3 (Weeks 9-12): {len(wave_3)} scaling actions",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING
                )
        
        # 4. One Thing This Week
        self._update_progress(80, "Identifying quick wins...")
        
        one_thing = None
        if plan_dict:
            one_thing = plan_dict.get('one_thing_this_week')
            if one_thing:
                self._emit_insight(
                    f"⭐ This week's #1 priority: {one_thing}",
                    priority=AgentPriority.CRITICAL,
                    insight_type=InsightType.RECOMMENDATION,
                    data={'one_thing': one_thing}
                )
        
        # 5. Quick Start List
        self._update_progress(90, "Creating quick start list...")
        
        quick_start = self._create_quick_start_list(plan_dict, recommendations)
        
        if quick_start:
            self._emit_insight(
                f"🏃 Quick start: {len(quick_start)} actions you can do today",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'quick_start_count': len(quick_start)}
            )
            
            # Emit first quick start item
            for item in quick_start[:1]:
                self._emit_insight(
                    f"💡 Start now: {item.get('title', 'Unknown')} ({item.get('time_estimate', 'Quick')})",
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.RECOMMENDATION,
                    data=item
                )
        
        # 6. ROI Projection
        self._update_progress(95, "Calculating ROI projection...")
        
        roi_projection = self._calculate_roi_projection(plan_dict, your_score, competitor_gap_data)
        
        if roi_projection.get('potential_score_gain', 0) > 0:
            self._emit_insight(
                f"📈 Projected impact: +{roi_projection['potential_score_gain']:.0f} points in 90 days",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.METRIC,
                data=roi_projection
            )
        
        self._emit_insight(
            "✅ Your 90-day action plan is ready — time to execute!",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        return {
            'plan': plan_dict,
            'one_thing_this_week': one_thing,
            'quick_start': quick_start,
            'competitor_gap': competitor_gap_data,
            'roi_projection': roi_projection,
            'phase_summary': {
                'wave_1_count': len(plan_dict.get('wave_1', [])) if plan_dict else 0,
                'wave_2_count': len(plan_dict.get('wave_2', [])) if plan_dict else 0,
                'wave_3_count': len(plan_dict.get('wave_3', [])) if plan_dict else 0
            }
        }
    
    def _create_quick_start_list(
        self, 
        plan: Optional[Dict[str, Any]], 
        recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create list of quick-start actions (low effort, high impact)"""
        
        quick_start = []
        
        # From plan wave 1 - get low-effort items
        if plan:
            for action in plan.get('wave_1', []):
                effort = action.get('effort', action.get('time_estimate', ''))
                
                # Check if low effort
                if any(term in str(effort).lower() for term in ['hour', 'quick', 'easy', 'low', '1-2', '2-4']):
                    quick_start.append({
                        'title': action.get('title', 'Unknown'),
                        'description': action.get('description', ''),
                        'time_estimate': action.get('time_estimate', 'Quick'),
                        'owner': action.get('owner', 'Team'),
                        'source': 'plan'
                    })
        
        # From recommendations
        for rec in recommendations[:5]:
            if rec.get('effort', 'medium') == 'low':
                quick_start.append({
                    'title': rec.get('title', rec.get('recommendation', 'Unknown')),
                    'description': rec.get('description', ''),
                    'time_estimate': 'Quick',
                    'owner': 'Team',
                    'source': 'recommendation'
                })
        
        # Remove duplicates and limit
        seen = set()
        unique = []
        for item in quick_start:
            if item['title'] not in seen:
                seen.add(item['title'])
                unique.append(item)
        
        return unique[:5]
    
    def _calculate_roi_projection(
        self, 
        plan: Optional[Dict[str, Any]], 
        current_score: int,
        competitor_gap: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate projected ROI from executing the plan"""
        
        if not plan:
            return {'potential_score_gain': 0, 'target_score': current_score}
        
        # Estimate score gain based on actions
        wave_1_count = len(plan.get('wave_1', []))
        wave_2_count = len(plan.get('wave_2', []))
        wave_3_count = len(plan.get('wave_3', []))
        
        # Rough estimation: each action can add 1-3 points
        estimated_gain = (wave_1_count * 2) + (wave_2_count * 1.5) + (wave_3_count * 1)
        estimated_gain = min(estimated_gain, 40)  # Cap at 40 points
        
        target_score = min(100, current_score + estimated_gain)
        gap_to_close = competitor_gap.get('gap', 0)
        
        return {
            'current_score': current_score,
            'potential_score_gain': estimated_gain,
            'target_score': target_score,
            'gap_closure': min(estimated_gain, max(0, gap_to_close)),
            'total_actions': wave_1_count + wave_2_count + wave_3_count
        }
