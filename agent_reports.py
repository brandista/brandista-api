"""
Growth Engine 2.0 - AI Report Generator
Generoi yksilöllisiä, tilanteeseen räätälöityjä raportteja
Jokainen raportti on uniikki - AI analysoi tilanteen ja kirjoittaa narratiivin
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Depends, Header

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["AI Reports"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ReportRequest(BaseModel):
    """Raporttipyyntö"""
    report_type: str = Field(
        default="executive",
        description="'executive' = täysi raportti, 'guardian' = uhka-analyysi, 'prospector' = mahdollisuudet, 'quick' = tiivistelmä"
    )
    email: str = Field(..., description="Vastaanottajan sähköposti")
    analysis_data: Dict[str, Any] = Field(..., description="Analyysin tulokset (WebSocket response data)")
    language: str = Field(default="fi")
    user_name: Optional[str] = Field(default=None, description="Vastaanottajan nimi")
    company_name: Optional[str] = Field(default=None, description="Yrityksen nimi")


class ReportResponse(BaseModel):
    success: bool
    message: str
    report_type: str
    email: str


# ============================================================================
# AI REPORT PROMPTS
# ============================================================================

REPORT_SYSTEM_PROMPT = """Olet Growth Engine -alustan raporttigeneroija. Kirjoitat tyylikkäitä, 
ammattimaisia ja YKSILÖLLISIÄ raportteja perustuen kilpailuanalyysidataan.

TÄRKEÄÄ:
- Jokainen raportti on UNIIKKI - älä käytä geneerisiä fraaseja
- Analysoi data ja tunnista mikä on TÄLLE yritykselle tärkeintä
- Kirjoita narratiivi, älä vain listaa dataa
- Ole konkreettinen - mainitse eurot, prosentit, kilpailijoiden nimet
- Anna actionable insights - mitä pitää tehdä ja miksi

SÄVY:
- Ammattimainen mutta helposti lähestyttävä
- Konsultin ääni - kuin henkilökohtainen neuvonantaja
- Positiivinen mutta rehellinen riskeistä

RAKENNE (HTML):
1. Executive Summary - 2-3 lausetta tilanteesta
2. Avainluvut - visuaalisesti
3. Tärkein havainto - mikä on kriittisin asia
4. Suositukset - priorisoituna
5. Seuraavat askeleet - konkreettiset toimenpiteet

Palauta VAIN HTML-sisältö (ei <html>, <head>, <body> tageja - vain sisältö).
Käytä annettua CSS-luokkia tyylittelyyn."""

EXECUTIVE_PROMPT = """Kirjoita EXECUTIVE REPORT tästä kilpailuanalyysistä.

YRITYKSEN TILANNE:
- URL: {url}
- Pistemäärä: {score}/100
- Sijoitus: #{ranking} / {total} kilpailijaa
- Liikevaihto riskissä: €{revenue_at_risk:,.0f}
- Markkina-asema: {position}

UHAT ({threat_count} kpl):
{threats_summary}

MAHDOLLISUUDET ({opportunity_count} kpl):
{opportunities_summary}

TOIMINTASUUNNITELMA:
{action_plan_summary}

AGENTIN AVAINLÖYDÖKSET:
{agent_insights}

---

Kirjoita räätälöity executive report. Tunnista mikä on TÄLLE yritykselle kriittisintä:
- Jos revenue at risk on korkea (>€30K) → painota uhkia ja suojautumista
- Jos kilpailijat ovat selvästi edellä → painota catch-up strategiaa  
- Jos on paljon helppoja mahdollisuuksia → painota quick winejä
- Jos yritys johtaa → painota aseman puolustamista

Käytä näitä CSS-luokkia:
- .executive-summary (intro-teksti)
- .key-metrics (avainluvut grid)
- .metric-card, .metric-value, .metric-label
- .critical-finding (tärkein havainto, punainen/oranssi border)
- .opportunity-finding (mahdollisuus, vihreä border)
- .recommendation-list (suositukset)
- .next-steps (seuraavat askeleet)
- .agent-quote (agentin sitaatti)

Pituus: ~400-600 sanaa. Kieli: {language}."""

GUARDIAN_PROMPT = """Kirjoita UHKA-ANALYYSI (Guardian Report) tästä datasta.

TILANNE:
- Yritys: {url}
- Pistemäärä: {score}/100 (kilpailijoiden ka: {avg_score})
- Liikevaihto riskissä: €{revenue_at_risk:,.0f}
- RASM Score: {rasm_score}/100

KILPAILIJAUHAT:
{threats_detail}

HAAVOITTUVUUDET:
{vulnerabilities}

---

Kirjoita uhka-analyysi kuin olisit yrityksen turvallisuusjohtaja:
- Priorisoi uhat vakavuuden mukaan
- Laske euromääräiset vaikutukset
- Anna konkreettiset suojautumistoimenpiteet
- Ole rehellinen mutta älä pelottele turhaan

Käytä CSS-luokkia: .threat-card, .threat-critical, .threat-high, .threat-medium, .protection-plan
Kieli: {language}."""

PROSPECTOR_PROMPT = """Kirjoita MAHDOLLISUUSRAPORTTI (Prospector Report) tästä datasta.

TILANNE:
- Yritys: {url}
- Nykyinen pistemäärä: {score}/100
- Potentiaalinen parannus: +{projected_improvement} pistettä

MARKKINAAUKOT:
{opportunities_detail}

KILPAILUEDUT:
{advantages}

QUICK WINS:
{quick_wins}

---

Kirjoita mahdollisuusraportti kuin olisit kasvukonsultti:
- Priorisoi ROI:n mukaan (helppo + suuri vaikutus ensin)
- Laske potentiaaliset euromääräiset hyödyt
- Anna konkreettiset toteutusohjeet
- Ole innostava mutta realistinen

Käytä CSS-luokkia: .opportunity-card, .roi-high, .roi-medium, .quick-win, .growth-roadmap
Kieli: {language}."""


# ============================================================================
# HTML EMAIL TEMPLATE
# ============================================================================

EMAIL_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
            color: #1a1a2e;
            background: #f0f2f5;
        }}
        
        .email-container {{
            max-width: 680px;
            margin: 0 auto;
            background: white;
        }}
        
        /* Header */
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 48px 40px;
            text-align: center;
        }}
        
        .logo {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 24px;
        }}
        
        .header h1 {{
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 8px;
        }}
        
        .header .subtitle {{
            font-size: 15px;
            opacity: 0.9;
        }}
        
        .header .date {{
            font-size: 13px;
            opacity: 0.7;
            margin-top: 16px;
        }}
        
        /* Key Metrics */
        .key-metrics {{
            display: flex;
            background: #1a1a2e;
            color: white;
        }}
        
        .metric-card {{
            flex: 1;
            padding: 24px;
            text-align: center;
            border-right: 1px solid rgba(255,255,255,0.1);
        }}
        
        .metric-card:last-child {{
            border-right: none;
        }}
        
        .metric-value {{
            font-size: 36px;
            font-weight: 700;
            color: #667eea;
        }}
        
        .metric-value.positive {{ color: #48bb78; }}
        .metric-value.negative {{ color: #f56565; }}
        .metric-value.neutral {{ color: #ecc94b; }}
        
        .metric-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.7;
            margin-top: 4px;
        }}
        
        /* Content */
        .content {{
            padding: 40px;
        }}
        
        .executive-summary {{
            font-size: 17px;
            color: #2d3748;
            line-height: 1.8;
            margin-bottom: 32px;
            padding: 24px;
            background: #f8fafc;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        
        /* Findings */
        .critical-finding {{
            background: #fff5f5;
            border-left: 4px solid #f56565;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        
        .critical-finding h3 {{
            color: #c53030;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        
        .opportunity-finding {{
            background: #f0fff4;
            border-left: 4px solid #48bb78;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        
        .opportunity-finding h3 {{
            color: #276749;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        
        /* Section headers */
        .section-header {{
            display: flex;
            align-items: center;
            margin: 32px 0 16px 0;
            padding-bottom: 12px;
            border-bottom: 2px solid #e2e8f0;
        }}
        
        .section-icon {{
            font-size: 24px;
            margin-right: 12px;
        }}
        
        .section-title {{
            font-size: 18px;
            font-weight: 600;
            color: #1a1a2e;
        }}
        
        /* Threat/Opportunity cards */
        .threat-card, .opportunity-card {{
            background: white;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        
        .threat-card {{ border-left: 4px solid #f56565; }}
        .threat-card.critical {{ border-left-color: #c53030; background: #fff5f5; }}
        .threat-card.high {{ border-left-color: #ed8936; }}
        .threat-card.medium {{ border-left-color: #ecc94b; }}
        
        .opportunity-card {{ border-left: 4px solid #48bb78; }}
        .opportunity-card.high-roi {{ background: #f0fff4; }}
        
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        
        .card-title {{
            font-weight: 600;
            color: #1a1a2e;
        }}
        
        .card-badge {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 12px;
            font-weight: 600;
        }}
        
        .badge-critical {{ background: #fed7d7; color: #c53030; }}
        .badge-high {{ background: #feebc8; color: #c05621; }}
        .badge-medium {{ background: #fefcbf; color: #975a16; }}
        .badge-opportunity {{ background: #c6f6d5; color: #276749; }}
        
        .card-content {{
            font-size: 14px;
            color: #4a5568;
        }}
        
        /* Recommendations */
        .recommendation-list {{
            list-style: none;
        }}
        
        .recommendation-item {{
            display: flex;
            align-items: flex-start;
            padding: 16px;
            background: #f8fafc;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        
        .recommendation-number {{
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            margin-right: 16px;
            flex-shrink: 0;
        }}
        
        .recommendation-content h4 {{
            font-size: 15px;
            font-weight: 600;
            color: #1a1a2e;
            margin-bottom: 4px;
        }}
        
        .recommendation-content p {{
            font-size: 14px;
            color: #4a5568;
        }}
        
        /* Next Steps */
        .next-steps {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            border-radius: 8px;
            margin-top: 32px;
        }}
        
        .next-steps h3 {{
            font-size: 16px;
            margin-bottom: 16px;
        }}
        
        .next-steps ul {{
            list-style: none;
        }}
        
        .next-steps li {{
            padding: 8px 0;
            padding-left: 24px;
            position: relative;
        }}
        
        .next-steps li:before {{
            content: "→";
            position: absolute;
            left: 0;
        }}
        
        /* Agent Quote */
        .agent-quote {{
            display: flex;
            align-items: flex-start;
            background: #f8fafc;
            padding: 20px;
            border-radius: 8px;
            margin: 24px 0;
        }}
        
        .agent-avatar {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea, #764ba2);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            margin-right: 16px;
            flex-shrink: 0;
        }}
        
        .agent-text {{
            flex: 1;
        }}
        
        .agent-name {{
            font-weight: 600;
            color: #1a1a2e;
            font-size: 14px;
        }}
        
        .agent-message {{
            color: #4a5568;
            font-style: italic;
            margin-top: 4px;
        }}
        
        /* Quick Win */
        .quick-win {{
            background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        
        .quick-win h4 {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.9;
            margin-bottom: 8px;
        }}
        
        .quick-win p {{
            font-size: 16px;
            font-weight: 500;
        }}
        
        /* CTA */
        .cta-section {{
            text-align: center;
            padding: 32px;
            background: #f8fafc;
        }}
        
        .cta-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 14px 32px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 15px;
        }}
        
        /* Footer */
        .footer {{
            background: #1a1a2e;
            color: white;
            padding: 32px;
            text-align: center;
        }}
        
        .footer-logo {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        
        .footer-text {{
            font-size: 12px;
            opacity: 0.6;
        }}
        
        /* Responsive */
        @media (max-width: 600px) {{
            .key-metrics {{
                flex-direction: column;
            }}
            .metric-card {{
                border-right: none;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .header, .content {{
                padding: 24px;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <!-- Header -->
        <div class="header">
            <div class="logo"><img src="https://brandista.eu/brandista-logo.png" alt="Brandista Growth Engine" style="height: 48px; margin-bottom: 16px;" /></div>
            <h1>{title}</h1>
            <div class="subtitle">{url}</div>
            <div class="date">{date}</div>
        </div>
        
        <!-- Key Metrics -->
        <div class="key-metrics">
            <div class="metric-card">
                <div class="metric-value">{score}</div>
                <div class="metric-label">{score_label}</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">#{ranking}/{total}</div>
                <div class="metric-label">{ranking_label}</div>
            </div>
            <div class="metric-card">
                <div class="metric-value negative">€{revenue_at_risk}</div>
                <div class="metric-label">{risk_label}</div>
            </div>
        </div>
        
        <!-- AI Generated Content -->
        <div class="content">
            {ai_content}
        </div>
        
        <!-- CTA -->
        <div class="cta-section">
            <a href="https://brandista.eu/growthengine" class="cta-button">{cta_text}</a>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <div class="footer-logo">Brandista Growth Engine</div>
            <div class="footer-text">© {year} Brandista. {footer_text}</div>
        </div>
    </div>
</body>
</html>
'''


# ============================================================================
# AI REPORT GENERATION
# ============================================================================

async def generate_ai_report_content(
    report_type: str,
    analysis_data: Dict[str, Any],
    language: str = "fi"
) -> str:
    """Generoi AI:lla yksilöllinen raporttisisältö"""
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        
        # Extract and format data
        url = analysis_data.get('url', 'N/A')
        score = analysis_data.get('your_score', 0)
        ranking = analysis_data.get('your_ranking', 1)
        total = analysis_data.get('total_competitors', 1)
        revenue_at_risk = analysis_data.get('revenue_at_risk', 0)
        position = analysis_data.get('position_quadrant', 'challenger')
        threats = analysis_data.get('competitor_threats', [])
        opportunities = analysis_data.get('market_gaps', [])
        action_plan = analysis_data.get('action_plan', {})
        rasm_score = analysis_data.get('rasm_score', 0)
        benchmark = analysis_data.get('benchmark', {})
        advantages = analysis_data.get('your_advantages', [])
        projected_improvement = analysis_data.get('projected_improvement', 0)
        
        # Format threats summary
        threats_summary = ""
        for i, t in enumerate(threats[:5], 1):
            company = t.get('company', t.get('domain', 'Unknown'))
            level = t.get('threat_level', 'medium')
            t_score = t.get('score', 0)
            threats_summary += f"{i}. {company} - {level} uhka, score {t_score}/100\n"
        
        if not threats_summary:
            threats_summary = "Ei merkittäviä uhkia tunnistettu."
        
        # Format opportunities summary
        opportunities_summary = ""
        for i, o in enumerate(opportunities[:5], 1):
            gap = o.get('gap', o.get('title', 'Unknown'))
            value = o.get('potential_value', 0)
            difficulty = o.get('difficulty', 'medium')
            opportunities_summary += f"{i}. {gap} - potentiaali €{value:,.0f}, {difficulty}\n"
        
        if not opportunities_summary:
            opportunities_summary = "Analysoidaan mahdollisuuksia..."
        
        # Format action plan summary
        action_plan_summary = ""
        if action_plan:
            this_week = action_plan.get('this_week', {})
            if this_week:
                action_plan_summary += f"Tällä viikolla: {this_week.get('action', 'N/A')}\n"
            
            total_actions = action_plan.get('total_actions', 0)
            action_plan_summary += f"Yhteensä {total_actions} toimenpidettä 90 päivän suunnitelmassa.\n"
            action_plan_summary += f"Odotettu parannus: +{projected_improvement} pistettä"
        
        # Agent insights (if available)
        agent_insights = ""
        agent_results = analysis_data.get('agent_results', {})
        
        if agent_results.get('strategist', {}).get('data', {}).get('recommendations'):
            recs = agent_results['strategist']['data']['recommendations'][:2]
            for rec in recs:
                if isinstance(rec, dict):
                    agent_insights += f"- {rec.get('title', rec.get('recommendation', ''))}\n"
        
        # Choose prompt based on report type
        if report_type == "guardian":
            prompt = GUARDIAN_PROMPT.format(
                url=url,
                score=score,
                avg_score=benchmark.get('avg', 50),
                revenue_at_risk=revenue_at_risk,
                rasm_score=rasm_score,
                threats_detail=threats_summary,
                vulnerabilities="Analysoidaan haavoittuvuuksia...",
                language="suomeksi" if language == "fi" else "in English"
            )
        elif report_type == "prospector":
            prompt = PROSPECTOR_PROMPT.format(
                url=url,
                score=score,
                projected_improvement=projected_improvement,
                opportunities_detail=opportunities_summary,
                advantages=", ".join(advantages[:3]) if advantages else "Analysoidaan...",
                quick_wins=action_plan.get('this_week', {}).get('action', 'N/A'),
                language="suomeksi" if language == "fi" else "in English"
            )
        else:  # executive (default)
            prompt = EXECUTIVE_PROMPT.format(
                url=url,
                score=score,
                ranking=ranking,
                total=total,
                revenue_at_risk=revenue_at_risk,
                position=position,
                threat_count=len(threats),
                threats_summary=threats_summary,
                opportunity_count=len(opportunities),
                opportunities_summary=opportunities_summary,
                action_plan_summary=action_plan_summary,
                agent_insights=agent_insights or "Agentit analysoivat tilannetta...",
                language="suomeksi" if language == "fi" else "in English"
            )
        
        # Call OpenAI
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        ai_content = response.choices[0].message.content
        
        # Clean up any markdown code blocks
        if ai_content.startswith("```html"):
            ai_content = ai_content[7:]
        if ai_content.startswith("```"):
            ai_content = ai_content[3:]
        if ai_content.endswith("```"):
            ai_content = ai_content[:-3]
        
        return ai_content.strip()
        
    except Exception as e:
        logger.error(f"[Reports] AI generation failed: {e}", exc_info=True)
        # Fallback to basic content
        return f"""
        <div class="executive-summary">
            <p>Analyysi yritykselle {analysis_data.get('url', 'N/A')} on valmis.</p>
            <p>Pistemäärä: {analysis_data.get('your_score', 0)}/100</p>
            <p>Kirjaudu dashboardiin nähdäksesi täydet tulokset.</p>
        </div>
        """


async def send_report_email(
    to_email: str,
    report_type: str,
    analysis_data: Dict[str, Any],
    ai_content: str,
    language: str = "fi",
    user_name: Optional[str] = None
) -> bool:
    """Lähetä raportti sähköpostiin SendGridillä"""
    
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Email, To, Content
        
        api_key = os.getenv("SENDGRID_API_KEY")
        if not api_key:
            logger.error("[Reports] SENDGRID_API_KEY not set")
            return False
        
        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        
        # Translations
        t = {
            'fi': {
                'executive_title': 'Executive Report',
                'guardian_title': 'Uhka-analyysi',
                'prospector_title': 'Mahdollisuusraportti',
                'score_label': 'Pistemäärä',
                'ranking_label': 'Sijoitus',
                'risk_label': 'Riskissä',
                'cta': 'Avaa Dashboard',
                'footer': 'Kaikki oikeudet pidätetään.',
                'subject_prefix': 'Growth Engine Raportti'
            },
            'en': {
                'executive_title': 'Executive Report',
                'guardian_title': 'Threat Analysis',
                'prospector_title': 'Opportunity Report',
                'score_label': 'Score',
                'ranking_label': 'Ranking',
                'risk_label': 'At Risk',
                'cta': 'Open Dashboard',
                'footer': 'All rights reserved.',
                'subject_prefix': 'Growth Engine Report'
            }
        }[language]
        
        # Report titles
        titles = {
            'executive': t['executive_title'],
            'guardian': t['guardian_title'],
            'prospector': t['prospector_title']
        }
        
        title = titles.get(report_type, t['executive_title'])
        url = analysis_data.get('url', 'N/A')
        
        # Format the full HTML
        html_content = EMAIL_TEMPLATE.format(
            title=title,
            url=url,
            date=datetime.now().strftime("%d.%m.%Y %H:%M"),
            score=analysis_data.get('your_score', 0),
            score_label=t['score_label'],
            ranking=analysis_data.get('your_ranking', 1),
            total=analysis_data.get('total_competitors', 1),
            ranking_label=t['ranking_label'],
            revenue_at_risk=f"{analysis_data.get('revenue_at_risk', 0):,.0f}",
            risk_label=t['risk_label'],
            ai_content=ai_content,
            cta_text=t['cta'],
            year=datetime.now().year,
            footer_text=t['footer']
        )
        
        # Create email
        from_email = Email(
            os.getenv("EMAIL_FROM", "tuukka@brandista.eu"),
            os.getenv("EMAIL_FROM_NAME", "Growth Engine")
        )
        
        subject = f"{t['subject_prefix']}: {url}"
        if user_name:
            subject = f"{user_name}, {subject}"
        
        message = Mail(
            from_email=from_email,
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_content)
        )
        
        # Send
        response = sg.send(message)
        
        if response.status_code in [200, 201, 202]:
            logger.info(f"[Reports] Email sent to {to_email}")
            return True
        else:
            logger.error(f"[Reports] SendGrid error: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"[Reports] Email send failed: {e}", exc_info=True)
        return False


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/generate", response_model=ReportResponse)
async def generate_and_send_report(request: ReportRequest):
    """
    Generoi AI-pohjainen raportti ja lähetä sähköpostiin.
    
    Report types:
    - executive: Täysi executive report
    - guardian: Uhka-analyysi (Gustav)
    - prospector: Mahdollisuusraportti (Petra)
    """
    
    logger.info(f"[Reports] Generating {request.report_type} report for {request.email}")
    
    try:
        # Generate AI content
        ai_content = await generate_ai_report_content(
            report_type=request.report_type,
            analysis_data=request.analysis_data,
            language=request.language
        )
        
        # Send email
        success = await send_report_email(
            to_email=request.email,
            report_type=request.report_type,
            analysis_data=request.analysis_data,
            ai_content=ai_content,
            language=request.language,
            user_name=request.user_name
        )
        
        if success:
            return ReportResponse(
                success=True,
                message=f"Raportti lähetetty osoitteeseen {request.email}" if request.language == "fi" else f"Report sent to {request.email}",
                report_type=request.report_type,
                email=request.email
            )
        else:
            raise HTTPException(500, "Failed to send email")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Reports] Generation failed: {e}", exc_info=True)
        raise HTTPException(500, f"Report generation failed: {str(e)}")


@router.get("/types")
async def get_report_types():
    """Palauta saatavilla olevat raporttityypit"""
    return {
        "types": [
            {
                "id": "executive",
                "name": "Executive Report",
                "name_fi": "Executive-raportti",
                "description": "Full analysis with threats, opportunities, and action plan",
                "description_fi": "Täysi analyysi uhkineen, mahdollisuuksineen ja toimintasuunnitelmineen",
                "icon": "📊"
            },
            {
                "id": "guardian",
                "name": "Threat Analysis",
                "name_fi": "Uhka-analyysi",
                "description": "Detailed competitor threats and protection strategies",
                "description_fi": "Yksityiskohtainen kilpailijauhka-analyysi ja suojautumisstrategiat",
                "icon": "🛡️"
            },
            {
                "id": "prospector",
                "name": "Opportunity Report",
                "name_fi": "Mahdollisuusraportti",
                "description": "Market gaps, quick wins, and growth opportunities",
                "description_fi": "Markkinaaukot, quick winit ja kasvumahdollisuudet",
                "icon": "💎"
            }
        ]
    }


# ============================================================================
# REGISTER ROUTES
# ============================================================================

def register_report_routes(app):
    """Register report routes"""
    app.include_router(router)
    logger.info("✅ AI Report Generator routes registered: /api/v1/reports/*")
