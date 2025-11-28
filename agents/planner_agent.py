"""
Growth Engine 2.0 - Planner Agent
📋 "The Project Manager" - 90-päivän roadmap ja ROI
"""

import logging
from typing import Dict, Any, List

from .base_agent import BaseAgent
from .types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)

logger = logging.getLogger(__name__)


PLANNER_TASKS = {
    "defining_phases": {"fi": "Määritetään vaiheita...", "en": "Defining phases..."},
    "creating_sprints": {"fi": "Luodaan viikkosprinttejä...", "en": "Creating weekly sprints..."},
    "setting_milestones": {"fi": "Asetetaan välitavoitteita...", "en": "Setting milestones..."},
    "estimating_resources": {"fi": "Arvioidaan resursseja...", "en": "Estimating resources..."},
    "calculating_roi": {"fi": "Lasketaan ROI-ennustetta...", "en": "Calculating ROI projection..."},
    "creating_quickstart": {"fi": "Luodaan aloitusopasta...", "en": "Creating quick start guide..."},
}

PHASE_NAMES = {
    "phase1_fix": {"fi": "Vaihe 1: Perustan korjaaminen", "en": "Phase 1: Fixing foundations"},
    "phase1_optimize": {"fi": "Vaihe 1: Quick wins", "en": "Phase 1: Quick wins"},
    "phase2": {"fi": "Vaihe 2: Rakentaminen", "en": "Phase 2: Building"},
    "phase3": {"fi": "Vaihe 3: Skaalaus", "en": "Phase 3: Scaling"},
}

MILESTONE_NAMES = {
    "m1": {"fi": "Quick wins toteutettu", "en": "Quick wins implemented"},
    "m2": {"fi": "Perusta kunnossa", "en": "Foundation complete"},
    "m3": {"fi": "Kilpailuetu rakennettu", "en": "Competitive edge built"},
    "m4": {"fi": "90 päivän ohjelma valmis", "en": "90-day program complete"},
}


class PlannerAgent(BaseAgent):
    """
    📋 Planner Agent - Projektimanageri
    """
    
    def __init__(self):
        super().__init__(
            agent_id="planner",
            name="Planner",
            role="Projektimanageri",
            avatar="📋",
            personality="Käytännöllinen ja järjestelmällinen organisoija"
        )
        self.dependencies = ['scout', 'analyst', 'guardian', 'prospector', 'strategist']
    
    def _task(self, key: str) -> str:
        return PLANNER_TASKS.get(key, {}).get(self._language, key)
    
    def _phase(self, key: str) -> str:
        return PHASE_NAMES.get(key, {}).get(self._language, key)
    
    def _milestone(self, key: str) -> str:
        return MILESTONE_NAMES.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        # Store context for use in helper methods
        self._context = context
        
        strategist_results = self.get_dependency_results(context, 'strategist')
        guardian_results = self.get_dependency_results(context, 'guardian')
        prospector_results = self.get_dependency_results(context, 'prospector')
        
        overall_score = strategist_results.get('overall_score', 50) if strategist_results else 50
        priorities = strategist_results.get('strategic_priorities', []) if strategist_results else []
        
        # Debug: Log what we received
        logger.info(f"[Planner] Strategist overall_score: {overall_score}")
        logger.info(f"[Planner] Strategist priorities count: {len(priorities)}")
        if priorities:
            logger.info(f"[Planner] First 3 priorities: {[p.get('title', 'no title') for p in priorities[:3]]}")
        
        self._emit_insight(
            self._t("planner.starting"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        self._update_progress(15, self._task("defining_phases"))
        
        # 1. Määritä vaiheet
        phases = self._define_phases(overall_score, priorities, guardian_results, prospector_results)
        
        for phase in phases:
            task_count = len(phase.get('tasks', []))
            self._emit_insight(
                self._t("planner.phase",
                       name=phase.get('name', ''),
                       duration=phase.get('duration', ''),
                       tasks=task_count),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.ACTION,
                data=phase
            )
        
        self._update_progress(30, self._task("creating_sprints"))
        
        # 2. Luo viikkosprintit
        weekly_sprints = self._create_weekly_sprints(phases)
        
        self._emit_insight(
            self._t("planner.sprints_created", count=len(weekly_sprints)),
            priority=AgentPriority.LOW,
            insight_type=InsightType.FINDING
        )
        
        self._update_progress(45, self._task("setting_milestones"))
        
        # 3. Määritä välitavoitteet
        milestones = self._define_milestones(phases)
        
        for ms in milestones[:2]:
            self._emit_insight(
                self._t("planner.milestone",
                       title=ms.get('title', ''),
                       date=ms.get('target_date', '')),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.ACTION,
                data=ms
            )
        
        self._update_progress(60, self._task("estimating_resources"))
        
        # 4. Arvioi resurssit
        resource_estimate = self._estimate_resources(phases)
        
        total_cost = resource_estimate.get('total_cost', 0)
        self._emit_insight(
            self._t("planner.investment", amount=f"{total_cost:,.0f}"),
            priority=AgentPriority.HIGH,
            insight_type=InsightType.FINDING,
            data=resource_estimate
        )
        
        self._update_progress(75, self._task("calculating_roi"))
        
        # 5. Laske ROI
        roi_projection = self._calculate_roi_projection(
            resource_estimate,
            guardian_results,
            prospector_results
        )
        
        self._emit_insight(
            self._t("planner.roi",
                   roi=roi_projection.get('roi_percentage', 0),
                   months=roi_projection.get('payback_months', 0)),
            priority=AgentPriority.HIGH,
            insight_type=InsightType.FINDING,
            data=roi_projection
        )
        
        self._update_progress(90, self._task("creating_quickstart"))
        
        # 6. Luo quick start guide
        quick_start_guide = self._create_quick_start_guide(prospector_results, priorities)
        
        # Final summary
        self._emit_insight(
            self._t("planner.complete",
                   phases=len(phases),
                   milestones=len(milestones),
                   quick_start=len(quick_start_guide)),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        return {
            'roadmap': {
                'total_duration_days': 90,
                'phases': len(phases),
                'total_tasks': sum(len(p.get('tasks', [])) for p in phases)
            },
            'phases': phases,
            'weekly_sprints': weekly_sprints,
            'milestones': milestones,
            'resource_estimate': resource_estimate,
            'roi_projection': roi_projection,
            'quick_start_guide': quick_start_guide
        }
    
    def _define_phases(
        self,
        overall_score: int,
        priorities: List[Dict[str, Any]],
        guardian_results: Dict[str, Any],
        prospector_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        phases = []
        
        # Get actual analysis data to determine what needs fixing
        analyst_results = self.get_dependency_results(self._context, 'analyst') if hasattr(self, '_context') else {}
        your_analysis = analyst_results.get('your_analysis', {}) if analyst_results else {}
        detailed = your_analysis.get('detailed_analysis', {})
        technical = detailed.get('technical_audit', {})
        seo = detailed.get('seo_basics', {})
        
        # Build defense tasks based on ACTUAL issues (not defaults)
        defense_tasks = []
        
        # Only add SSL task if SSL is actually missing
        has_ssl = technical.get('has_ssl', True)
        if not has_ssl:
            defense_tasks.append({'title': 'Asenna SSL-sertifikaatti', 'category': 'security', 'source': 'defense', 'effort': 'low', 'points': 5})
        
        # Only add meta task if meta is actually weak
        meta_score = seo.get('meta_score', 100)
        if meta_score < 70:
            defense_tasks.append({'title': 'Optimoi meta-kuvaukset', 'category': 'seo', 'source': 'defense', 'effort': 'low', 'points': 3})
        
        # Only add mobile task if mobile optimization is missing
        has_mobile = technical.get('has_mobile_optimization', True)
        if not has_mobile:
            defense_tasks.append({'title': 'Paranna mobiilioptimointi', 'category': 'mobile', 'source': 'defense', 'effort': 'medium', 'points': 5})
        
        # Only add analytics task if analytics is missing
        has_analytics = technical.get('has_analytics', True)
        if not has_analytics:
            defense_tasks.append({'title': 'Lisää analytiikka', 'category': 'technical', 'source': 'defense', 'effort': 'low', 'points': 2})
        
        # Check page speed
        speed_score = technical.get('page_speed_score', 80)
        if speed_score < 50:
            defense_tasks.append({'title': 'Paranna sivuston nopeutta', 'category': 'performance', 'source': 'defense', 'effort': 'medium', 'points': 3})
        
        # Log what we found
        logger.info(f"[Planner] Analyst data: has_ssl={has_ssl}, meta_score={meta_score}, has_mobile={has_mobile}, has_analytics={has_analytics}")
        logger.info(f"[Planner] Generated {len(defense_tasks)} defense tasks based on actual analysis")
        
        # Growth tasks - use Guardian priorities or Prospector opportunities
        growth_tasks = []
        
        if guardian_results:
            priority_actions = guardian_results.get('priority_actions', [])
            for action in priority_actions[:4]:
                growth_tasks.append({
                    'title': action.get('action', action.get('title', '')),
                    'category': action.get('category', 'growth'),
                    'source': 'defense',
                    'effort': action.get('effort', 'medium'),
                    'points': 3
                })
        
        if prospector_results and not growth_tasks:
            opportunities = prospector_results.get('growth_opportunities', [])
            for opp in opportunities[:4]:
                growth_tasks.append({
                    'title': opp.get('title', opp.get('name', '')),
                    'category': opp.get('category', 'growth'),
                    'source': 'growth',
                    'effort': opp.get('effort', 'medium'),
                    'points': opp.get('potential_score_gain', 3)
                })
        
        # Fallback growth tasks only if nothing else
        if not growth_tasks:
            growth_tasks = [
                {'title': 'Luo sisältöstrategia', 'category': 'content', 'source': 'growth', 'effort': 'medium', 'points': 3},
                {'title': 'Rakenna backlink-profiilia', 'category': 'seo', 'source': 'growth', 'effort': 'high', 'points': 5},
                {'title': 'Optimoi konversiot', 'category': 'ux', 'source': 'growth', 'effort': 'medium', 'points': 4},
            ]
        
        # Use real priorities if available
        defense_priorities = [p for p in priorities if p.get('source') == 'defense'] or defense_tasks
        growth_priorities = [p for p in priorities if p.get('source') == 'growth'] or growth_tasks
        medium_priorities = [p for p in priorities if p.get('effort') == 'medium']
        
        if not medium_priorities:
            medium_priorities = defense_priorities[:2] + growth_priorities[:2]
        
        # Phase 1: Days 1-30
        if overall_score < 50:
            phase1_name = self._phase("phase1_fix")
            phase1_goal = {"fi": "Korjaa kriittiset puutteet", "en": "Fix critical gaps"}.get(self._language)
            phase1_tasks = defense_priorities[:4]
        else:
            phase1_name = self._phase("phase1_optimize")
            phase1_goal = {"fi": "Toteuta nopeat voitot", "en": "Implement quick wins"}.get(self._language)
            quick_wins = prospector_results.get('quick_wins', []) if prospector_results else []
            phase1_tasks = quick_wins[:4] if quick_wins else growth_priorities[:4]
        
        phases.append({
            'phase': 1,
            'name': phase1_name,
            'duration': {"fi": "Päivät 1-30", "en": "Days 1-30"}.get(self._language),
            'goal': phase1_goal,
            'tasks': phase1_tasks
        })
        
        # Phase 2: Days 31-60
        phase2_name = self._phase("phase2")
        
        phases.append({
            'phase': 2,
            'name': phase2_name,
            'duration': {"fi": "Päivät 31-60", "en": "Days 31-60"}.get(self._language),
            'goal': {"fi": "Rakenna kilpailuetua", "en": "Build competitive advantage"}.get(self._language),
            'tasks': medium_priorities[:4]
        })
        
        # Phase 3: Days 61-90
        phase3_name = self._phase("phase3")
        
        phases.append({
            'phase': 3,
            'name': phase3_name,
            'duration': {"fi": "Päivät 61-90", "en": "Days 61-90"}.get(self._language),
            'goal': {"fi": "Skaalaa kasvua", "en": "Scale growth"}.get(self._language),
            'tasks': growth_priorities[:4]
        })
        
        return phases
    
    def _create_weekly_sprints(self, phases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sprints = []
        
        for phase in phases:
            phase_num = phase.get('phase', 1)
            tasks = phase.get('tasks', [])
            
            # 4 weeks per phase
            start_week = (phase_num - 1) * 4 + 1
            
            for week_offset in range(4):
                week_num = start_week + week_offset
                
                # Distribute tasks across weeks
                week_tasks = []
                if tasks:
                    task_idx = week_offset % len(tasks)
                    if task_idx < len(tasks):
                        week_tasks.append(tasks[task_idx])
                
                sprints.append({
                    'week': week_num,
                    'phase': phase_num,
                    'tasks': week_tasks,
                    'focus': phase.get('goal', '')
                })
        
        return sprints
    
    def _define_milestones(self, phases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        milestones = [
            {
                'id': 1,
                'title': self._milestone("m1"),
                'week': 2,
                'target_date': {"fi": "Viikko 2", "en": "Week 2"}.get(self._language),
                'phase': 1
            },
            {
                'id': 2,
                'title': self._milestone("m2"),
                'week': 4,
                'target_date': {"fi": "Viikko 4", "en": "Week 4"}.get(self._language),
                'phase': 1
            },
            {
                'id': 3,
                'title': self._milestone("m3"),
                'week': 8,
                'target_date': {"fi": "Viikko 8", "en": "Week 8"}.get(self._language),
                'phase': 2
            },
            {
                'id': 4,
                'title': self._milestone("m4"),
                'week': 12,
                'target_date': {"fi": "Viikko 12", "en": "Week 12"}.get(self._language),
                'phase': 3
            }
        ]
        
        return milestones
    
    def _estimate_resources(self, phases: List[Dict[str, Any]]) -> Dict[str, Any]:
        hourly_rate = 80  # €/hour
        
        effort_hours = {
            'low': 4,
            'medium': 16,
            'high': 40
        }
        
        total_hours = 0
        category_hours = {}
        
        for phase in phases:
            for task in phase.get('tasks', []):
                effort = task.get('effort', 'medium')
                hours = effort_hours.get(effort, 16)
                total_hours += hours
                
                cat = task.get('category', 'other')
                category_hours[cat] = category_hours.get(cat, 0) + hours
        
        total_cost = total_hours * hourly_rate
        
        return {
            'total_hours': total_hours,
            'total_cost': total_cost,
            'hourly_rate': hourly_rate,
            'by_category': category_hours,
            'resource_split': {
                'internal': round(total_cost * 0.6),
                'external': round(total_cost * 0.4)
            }
        }
    
    def _calculate_roi_projection(
        self,
        resource_estimate: Dict[str, Any],
        guardian_results: Dict[str, Any],
        prospector_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        investment = resource_estimate.get('total_cost', 0)
        
        # Risk saved from Guardian
        annual_risk = 0
        if guardian_results:
            revenue_impact = guardian_results.get('revenue_impact', {})
            annual_risk = revenue_impact.get('total_annual_risk', 0)
        
        # Assume we can eliminate 50% of identified risks
        risk_saved = annual_risk * 0.5
        
        # Revenue gain from growth opportunities
        revenue_gain = 0
        potential_score_gain = 0
        if prospector_results:
            opportunities = prospector_results.get('growth_opportunities', [])
            high_impact_opps = len([o for o in opportunities if o.get('impact') == 'high'])
            medium_impact_opps = len([o for o in opportunities if o.get('impact') == 'medium'])
            
            # Estimate €5000/year per high-impact opportunity
            revenue_gain = high_impact_opps * 5000
            
            # Estimate score improvement: high=5pts, medium=3pts, defense fixes=2pts each
            potential_score_gain = (high_impact_opps * 5) + (medium_impact_opps * 3)
            
            # Add points from fixing issues (Guardian)
            if guardian_results:
                priority_actions = guardian_results.get('priority_actions', [])
                potential_score_gain += len(priority_actions) * 2
            
            # Cap at reasonable max
            potential_score_gain = min(potential_score_gain, 35)
        
        total_benefit = risk_saved + revenue_gain
        
        # Calculate ROI
        if investment > 0:
            roi_percentage = round(((total_benefit - investment) / investment) * 100)
        else:
            roi_percentage = 0
        
        # Payback period
        if total_benefit > 0:
            payback_months = round((investment / total_benefit) * 12)
        else:
            payback_months = 0
        
        return {
            'investment': investment,
            'risk_saved': round(risk_saved),
            'revenue_gain': round(revenue_gain),
            'total_annual_benefit': round(total_benefit),
            'roi_percentage': roi_percentage,
            'payback_months': min(payback_months, 36),  # Cap at 36 months
            'potential_score_gain': potential_score_gain  # NEW!
        }
    
    def _create_quick_start_guide(
        self,
        prospector_results: Dict[str, Any],
        priorities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        quick_start = []
        
        # Get quick wins from prospector
        quick_wins = []
        if prospector_results:
            quick_wins = prospector_results.get('quick_wins', [])
        
        # Get low-effort priorities
        low_effort = [p for p in priorities if p.get('effort') == 'low']
        
        # Combine and take top 3
        all_quick = quick_wins + low_effort
        
        for idx, item in enumerate(all_quick[:3]):
            quick_start.append({
                'step': idx + 1,
                'title': item.get('title', ''),
                'category': item.get('category', ''),
                'why': {"fi": "Nopea vaikutus, vähän työtä", "en": "Quick impact, low effort"}.get(self._language),
                'time_estimate': item.get('timeframe', '1-2 days')
            })
        
        return quick_start
