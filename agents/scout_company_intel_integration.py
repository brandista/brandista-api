"""
Scout Agent - Company Intel Integration
Add this to scout_agent.py execute() method

This enriches discovered competitors with:
- Official company name (YTJ)
- Y-tunnus (business ID)  
- Revenue (Kauppalehti)
- Employee count
- Founded year
- Industry classification
"""

# Add to imports at top of scout_agent.py:
# from company_intel import CompanyIntel

# Add this method to ScoutAgent class:

async def _enrich_competitors_with_intel(self, competitors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich discovered competitors with company intelligence.
    
    Adds:
    - company_name (official)
    - business_id (Y-tunnus)
    - revenue
    - employees  
    - founded_year
    - industry
    - size_category
    """
    
    self._emit_insight(
        "🏢 Enriching competitors with company data...",
        priority=AgentPriority.LOW,
        insight_type=InsightType.FINDING
    )
    
    try:
        intel = CompanyIntel()
        enriched = []
        
        for i, competitor in enumerate(competitors):
            url = competitor.get('url', '')
            
            try:
                enriched_competitor = await intel.enrich_competitor(competitor.copy())
                enriched.append(enriched_competitor)
                
                # Log if we found company data
                if enriched_competitor.get('company_intel'):
                    company_name = enriched_competitor.get('company_name', 'Unknown')
                    revenue = enriched_competitor.get('revenue')
                    employees = enriched_competitor.get('employees')
                    
                    revenue_str = f"€{revenue:,.0f}" if revenue else "N/A"
                    employees_str = f"{employees} hlö" if employees else "N/A"
                    
                    self._emit_insight(
                        f"📊 {company_name}: {revenue_str} liikevaihto, {employees_str}",
                        priority=AgentPriority.MEDIUM,
                        insight_type=InsightType.FINDING
                    )
                    
            except Exception as e:
                logger.warning(f"[Scout] Company intel failed for {url}: {e}")
                enriched.append(competitor)
            
            # Update progress
            progress = 70 + (i / len(competitors)) * 20  # 70-90%
            self._update_progress(int(progress), "Fetching company data...")
        
        await intel.close()
        
        # Count how many we enriched
        enriched_count = sum(1 for c in enriched if c.get('company_intel'))
        
        self._emit_insight(
            f"✅ Company data found for {enriched_count}/{len(competitors)} competitors",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        return enriched
        
    except Exception as e:
        logger.error(f"[Scout] Company intel enrichment failed: {e}")
        return competitors  # Return original if enrichment fails


# =============================================================================
# WHERE TO ADD IN execute() METHOD:
# =============================================================================

# After you have the competitors list (around line 150-200 in execute):
#
# Original:
#     return {
#         'competitors': competitors,
#         'industry': detected_industry,
#         ...
#     }
#
# New:
#     # Enrich with company intelligence
#     enriched_competitors = await self._enrich_competitors_with_intel(competitors)
#     
#     return {
#         'competitors': enriched_competitors,
#         'industry': detected_industry,
#         ...
#     }
