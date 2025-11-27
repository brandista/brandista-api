"""
Growth Engine 2.0 - Agent Translations
Natural, fluent translations for all agent messages
"""

from typing import Dict

AGENT_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ========================================
    # SCOUT AGENT
    # ========================================
    "scout.identified_company": {
        "fi": "Tunnistin yrityksen: {company}",
        "en": "Got it — analyzing {company}"
    },
    "scout.website_fetch_failed": {
        "fi": "Sivuston haku epäonnistui, jatkan silti",
        "en": "Couldn't fetch the site, but I'll work with what I have"
    },
    "scout.industry": {
        "fi": "Toimiala: {industry}",
        "en": "Industry detected: {industry}"
    },
    "scout.validating_competitors": {
        "fi": "Validoin {count}/{total} kilpailijaa",
        "en": "Checked {count} of {total} competitors"
    },
    "scout.starting_search": {
        "fi": "Aloitan kilpailijoiden etsinnän...",
        "en": "Hunting for your competitors..."
    },
    "scout.found_competitors": {
        "fi": "Löysin {count} relevanttia kilpailijaa! Paras osuma: {top} (relevanssi {score}%)",
        "en": "Found {count} solid competitors! Top match: {top} ({score}% relevance)"
    },
    "scout.no_competitors": {
        "fi": "En löytänyt vahvoja kilpailijoita - toimiala voi olla niche",
        "en": "No obvious competitors found — you might be in a niche market"
    },
    "scout.search_failed": {
        "fi": "Kilpailijoiden haku epäonnistui: {error}",
        "en": "Competitor search hit a snag: {error}"
    },
    
    # ========================================
    # ANALYST AGENT
    # ========================================
    "analyst.starting": {
        "fi": "Aloitan digitaalisen kypsyyden analyysin...",
        "en": "Diving into the digital maturity analysis..."
    },
    "analyst.score": {
        "fi": "Digitaalinen kypsyyspistemäärä: {score}/100",
        "en": "Digital maturity score: {score} out of 100"
    },
    "analyst.mobile_ok": {
        "fi": "✅ Sivusto on mobiilioptimioitu",
        "en": "✅ Mobile experience looks solid"
    },
    "analyst.mobile_bad": {
        "fi": "⚠️ Mobiilioptimointi puutteellinen",
        "en": "⚠️ Mobile experience needs work"
    },
    "analyst.analysis_failed": {
        "fi": "Kohdesivuston analyysi epäonnistui: {error}",
        "en": "Hit a wall analyzing the target site: {error}"
    },
    "analyst.no_competitors": {
        "fi": "Ei kilpailijoita analysoitavaksi",
        "en": "No competitors to benchmark against"
    },
    "analyst.analyzing_competitors": {
        "fi": "Analysoin {count} kilpailijaa...",
        "en": "Analyzing {count} competitors..."
    },
    "analyst.competitor_stronger": {
        "fi": "🔴 {name}: {score}/100 (vahvempi kuin sinä +{diff})",
        "en": "🔴 {name}: {score}/100 — ahead of you by {diff} points"
    },
    "analyst.competitor_weaker": {
        "fi": "🟢 {name}: {score}/100 (heikompi kuin sinä {diff})",
        "en": "🟢 {name}: {score}/100 — you're beating them by {diff} points"
    },
    "analyst.competitor_equal": {
        "fi": "🟡 {name}: {score}/100 (tasavahva)",
        "en": "🟡 {name}: {score}/100 — neck and neck"
    },
    "analyst.competitor_failed": {
        "fi": "Kilpailijan {idx} analyysi epäonnistui",
        "en": "Couldn't analyze competitor #{idx}"
    },
    "analyst.benchmark_ahead": {
        "fi": "📊 Sijoitut {position}. sijalle {total} analysoitavasta (keskiarvo {avg}, sinä {score})",
        "en": "📊 You rank #{position} out of {total} — above the {avg} average with {score}"
    },
    "analyst.benchmark_behind": {
        "fi": "📊 Sijoitut {position}. sijalle - kehitettävää löytyy (keskiarvo {avg}, sinä {score})",
        "en": "📊 Ranking #{position} — room to climb (average: {avg}, you: {score})"
    },
    
    # ========================================
    # GUARDIAN AGENT
    # ========================================
    "guardian.no_data": {
        "fi": "Ei analyysidataa - Guardian ei voi toimia",
        "en": "Missing analysis data — can't run the risk assessment"
    },
    "guardian.starting_rasm": {
        "fi": "Aloitan Revenue Attack Surface Mapping™...",
        "en": "Running Revenue Attack Surface Mapping™..."
    },
    "guardian.risk_critical": {
        "fi": "🚨 KRIITTINEN: Tunnistin €{amount}/vuosi liikevaihtoriskin!",
        "en": "🚨 CRITICAL: Found €{amount}/year at risk!"
    },
    "guardian.risk_high": {
        "fi": "⚠️ HUOMIO: €{amount}/vuosi liikevaihtoriski",
        "en": "⚠️ HEADS UP: €{amount}/year revenue exposure"
    },
    "guardian.risk_medium": {
        "fi": "💰 Arvioitu liikevaihtoriski: €{amount}/vuosi",
        "en": "💰 Estimated revenue at risk: €{amount}/year"
    },
    "guardian.threat_critical": {
        "fi": "🔴 {category}: {title}",
        "en": "🔴 {category}: {title}"
    },
    "guardian.threat_high": {
        "fi": "🟠 {category}: {title}",
        "en": "🟠 {category}: {title}"
    },
    "guardian.priority_action": {
        "fi": "🎯 Prioriteetti #{idx}: {title} (ROI: {roi})",
        "en": "🎯 Priority #{idx}: {title} (ROI: {roi})"
    },
    "guardian.complete": {
        "fi": "🛡️ RASM valmis: {count} uhkaa tunnistettu, turvallisuuspistemäärä {score}/100",
        "en": "🛡️ RASM done: {count} threats flagged, security score {score}/100"
    },
    
    # Guardian threat titles
    "guardian.threat.seo": {
        "fi": "Heikko hakukonenäkyvyys",
        "en": "Weak search visibility"
    },
    "guardian.threat.mobile": {
        "fi": "Puutteellinen mobiilioptimointi",
        "en": "Mobile experience gaps"
    },
    "guardian.threat.ssl": {
        "fi": "SSL-sertifikaatti puuttuu",
        "en": "Missing SSL certificate"
    },
    "guardian.threat.performance": {
        "fi": "Hidas sivusto",
        "en": "Slow page speed"
    },
    "guardian.threat.competitive": {
        "fi": "Jäät kilpailijoista jälkeen",
        "en": "Competitors pulling ahead"
    },
    "guardian.threat.content": {
        "fi": "Heikko sisällön laatu",
        "en": "Content quality issues"
    },
    
    # ========================================
    # PROSPECTOR AGENT
    # ========================================
    "prospector.no_data": {
        "fi": "Ei analyysidataa saatavilla",
        "en": "No analysis data to work with"
    },
    "prospector.starting": {
        "fi": "Aloitan mahdollisuuksien kartoituksen...",
        "en": "Scouting for growth opportunities..."
    },
    "prospector.found_gap": {
        "fi": "💎 Löysin markkinaaukon: {title}",
        "en": "💎 Spotted a market gap: {title}"
    },
    "prospector.more_gaps": {
        "fi": "...ja {count} muuta mahdollisuutta",
        "en": "...plus {count} more opportunities"
    },
    "prospector.quick_win": {
        "fi": "⚡ Quick Win #{idx}: {title} ({effort} effort)",
        "en": "⚡ Quick Win #{idx}: {title} ({effort} effort)"
    },
    "prospector.advantage": {
        "fi": "🏆 Kilpailuetusi: {title}",
        "en": "🏆 Your edge: {title}"
    },
    "prospector.swot_complete": {
        "fi": "📊 SWOT: {strengths} vahvuutta, {opportunities} mahdollisuutta tunnistettu",
        "en": "📊 SWOT done: {strengths} strengths, {opportunities} opportunities mapped"
    },
    "prospector.complete": {
        "fi": "💎 Prospector valmis: {total} kasvumahdollisuutta, joista {high_impact} korkean vaikutuksen",
        "en": "💎 Found {total} growth plays — {high_impact} are high-impact"
    },
    
    # ========================================
    # STRATEGIST AGENT
    # ========================================
    "strategist.starting": {
        "fi": "Syntetisoin tiimin löydökset strategiaksi...",
        "en": "Pulling it all together into a strategy..."
    },
    "strategist.overall_score": {
        "fi": "🎯 Kokonaispistemäärä: {score}/100 ({level})",
        "en": "🎯 Overall score: {score}/100 — {level}"
    },
    "strategist.position": {
        "fi": "📊 Kilpailuasema: {position}",
        "en": "📊 Competitive position: {position}"
    },
    "strategist.priority": {
        "fi": "🎯 Strateginen prioriteetti #{idx}: {title}",
        "en": "🎯 Strategic priority #{idx}: {title}"
    },
    "strategist.complete": {
        "fi": "🎯 Strategia valmis: {threats} uhkaa, {opportunities} mahdollisuutta, {priorities} priorisoitua toimenpidettä",
        "en": "🎯 Strategy locked: {threats} threats, {opportunities} opportunities, {priorities} prioritized actions"
    },
    
    # Maturity levels
    "strategist.level.advanced": {
        "fi": "Edistyksellinen",
        "en": "Advanced"
    },
    "strategist.level.developed": {
        "fi": "Kehittynyt",
        "en": "Solid"
    },
    "strategist.level.average": {
        "fi": "Keskitaso",
        "en": "Middle of the pack"
    },
    "strategist.level.developing": {
        "fi": "Kehittyvä",
        "en": "Getting there"
    },
    "strategist.level.beginner": {
        "fi": "Aloitteleva",
        "en": "Early stage"
    },
    
    # Position texts
    "strategist.position.leader": {
        "fi": "🏆 Markkinajohtaja",
        "en": "🏆 Market Leader"
    },
    "strategist.position.challenger": {
        "fi": "🥈 Haastaja",
        "en": "🥈 Strong Challenger"
    },
    "strategist.position.middle": {
        "fi": "🎯 Keskikastia",
        "en": "🎯 In the mix"
    },
    "strategist.position.behind": {
        "fi": "⚠️ Jälkijunassa",
        "en": "⚠️ Playing catch-up"
    },
    
    # ========================================
    # PLANNER AGENT
    # ========================================
    "planner.starting": {
        "fi": "Rakennan 90 päivän toimintasuunnitelmaa...",
        "en": "Building your 90-day game plan..."
    },
    "planner.phase": {
        "fi": "📅 {name}: {duration} - {tasks} tehtävää",
        "en": "📅 {name}: {duration} — {tasks} tasks"
    },
    "planner.sprints_created": {
        "fi": "Luotu {count} viikkokohtaista sprinttiä",
        "en": "Mapped out {count} weekly sprints"
    },
    "planner.milestone": {
        "fi": "🏁 Välitavoite: {title} ({date})",
        "en": "🏁 Milestone: {title} ({date})"
    },
    "planner.investment": {
        "fi": "💰 Arvioitu kokonaisinvestointi: €{amount}",
        "en": "💰 Estimated investment: €{amount}"
    },
    "planner.roi": {
        "fi": "📈 Arvioitu ROI: {roi}% (takaisinmaksuaika: {months} kk)",
        "en": "📈 Projected ROI: {roi}% — pays back in {months} months"
    },
    "planner.complete": {
        "fi": "📋 90 päivän suunnitelma valmis! {phases} vaihetta, {milestones} välitavoitetta, {quick_start} aloitustoimenpidettä",
        "en": "📋 90-day plan ready! {phases} phases, {milestones} milestones, {quick_start} quick starts"
    },
    
    # Phase names
    "planner.phase1.fix": {
        "fi": "Vaihe 1: Perustan korjaaminen",
        "en": "Phase 1: Shore up the foundation"
    },
    "planner.phase1.optimize": {
        "fi": "Vaihe 1: Quick wins & perusoptimointi",
        "en": "Phase 1: Quick wins & basics"
    },
    "planner.phase2": {
        "fi": "Vaihe 2: Rakentaminen",
        "en": "Phase 2: Build momentum"
    },
    "planner.phase3": {
        "fi": "Vaihe 3: Skaalaus",
        "en": "Phase 3: Scale up"
    },
    
    # ========================================
    # COMMON / SHARED
    # ========================================
    "common.preparing": {
        "fi": "Valmistellaan...",
        "en": "Getting ready..."
    },
    "common.executing": {
        "fi": "Suoritetaan...",
        "en": "On it..."
    },
    "common.finalizing": {
        "fi": "Viimeistellään...",
        "en": "Wrapping up..."
    },
    "common.complete": {
        "fi": "Valmis!",
        "en": "Done!"
    },
    "common.error": {
        "fi": "Virhe: {error}",
        "en": "Something went wrong: {error}"
    },
    "common.weeks": {
        "fi": "Viikot {start}-{end}",
        "en": "Weeks {start}–{end}"
    },
    
    # Progress messages
    "progress.analyzing_target": {
        "fi": "Analysoimassa kohdeyritystä...",
        "en": "Analyzing the target company..."
    },
    "progress.detecting_industry": {
        "fi": "Tunnistamassa toimialaa...",
        "en": "Figuring out the industry..."
    },
    "progress.validating_competitors": {
        "fi": "Validoimassa annettuja kilpailijoita...",
        "en": "Checking those competitors..."
    },
    "progress.searching_competitors": {
        "fi": "Etsimässä kilpailijoita...",
        "en": "Hunting for competitors..."
    },
    "progress.scoring_competitors": {
        "fi": "Pisteyttämässä kilpailijoita...",
        "en": "Ranking the competition..."
    },
    "progress.analyzing_website": {
        "fi": "Analysoimassa sivustoa...",
        "en": "Deep-diving into the website..."
    },
    "progress.benchmarking": {
        "fi": "Vertailemassa kilpailijoihin...",
        "en": "Benchmarking against competitors..."
    },
    "progress.building_risk_register": {
        "fi": "Rakentamassa riskiprofiilia...",
        "en": "Building the risk profile..."
    },
    "progress.calculating_impact": {
        "fi": "Laskemassa liikevaihtovaikutusta...",
        "en": "Calculating revenue impact..."
    },
    "progress.finding_opportunities": {
        "fi": "Etsimässä mahdollisuuksia...",
        "en": "Spotting opportunities..."
    },
    "progress.running_swot": {
        "fi": "Suorittamassa SWOT-analyysiä...",
        "en": "Running SWOT analysis..."
    },
    "progress.synthesizing": {
        "fi": "Yhdistämässä löydöksiä...",
        "en": "Connecting the dots..."
    },
    "progress.prioritizing": {
        "fi": "Priorisoimassa toimenpiteitä...",
        "en": "Prioritizing actions..."
    },
    "progress.building_roadmap": {
        "fi": "Rakentamassa roadmappia...",
        "en": "Mapping out the roadmap..."
    },
    "progress.calculating_roi": {
        "fi": "Laskemassa ROI-ennustetta...",
        "en": "Crunching the ROI numbers..."
    },
}


def t(key: str, language: str = "fi", **kwargs) -> str:
    """
    Get translation by key.
    
    Args:
        key: Translation key (e.g. "scout.found_competitors")
        language: Language code ("fi" or "en")
        **kwargs: Parameters for the text (e.g. count=5)
        
    Returns:
        Translated text with parameters
        
    Example:
        t("scout.found_competitors", "en", count=5, top="Example.com", score=85)
        # -> "Found 5 solid competitors! Top match: Example.com (85% relevance)"
    """
    translation = AGENT_TRANSLATIONS.get(key, {})
    text = translation.get(language, translation.get("fi", key))
    
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError):
        return text


def get_maturity_level(score: int, language: str = "fi") -> str:
    """Return maturity level text"""
    if score >= 80:
        return t("strategist.level.advanced", language)
    elif score >= 65:
        return t("strategist.level.developed", language)
    elif score >= 50:
        return t("strategist.level.average", language)
    elif score >= 35:
        return t("strategist.level.developing", language)
    else:
        return t("strategist.level.beginner", language)
