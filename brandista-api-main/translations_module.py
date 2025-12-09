# ============================================================================
# TRANSLATION MODULE - CENTRALIZED TRANSLATIONS FOR BRANDISTA
# ============================================================================
"""
Centralized translation module for all user-facing texts in Brandista.
Supports English (en) and Finnish (fi).
"""

TRANSLATIONS = {
    'risk_register': {
        'en': {
            'thin_content': "Thin content → weak rankings",
            'thin_content_mitigation': "Pillar/cluster content plan",
            'spa_risk': "SPA client-only rendering → low visibility",
            'spa_mitigation': "SSR/prerender critical routes",
            'weak_security': "Weak security → trust/SEO penalty",
            'security_mitigation': "Install SSL + security headers",
            'poor_mobile': "Poor mobile UX → high bounce rate",
            'mobile_mitigation': "Responsive design + CWV optimization"
        },
        'fi': {
            'thin_content': "Ohut sisältö → heikko ranking",
            'thin_content_mitigation': "Pilari/klusterisuunnitelma",
            'spa_risk': "SPA pelkkä client-renderöinti → heikko näkyvyys",
            'spa_mitigation': "SSR/esirenderöinti kriittisille reiteille",
            'weak_security': "Heikko turvallisuus → luottamus/SEO-rangaistus",
            'security_mitigation': "Asenna SSL + turvallisuusotsikot",
            'poor_mobile': "Heikko mobiilikäyttökokemus → korkea poistumisprosentti",
            'mobile_mitigation': "Responsiivinen suunnittelu + CWV-optimointi"
        }
    },
    'snippet_examples': {
        'en': {
            'title_1': "— fast, modern & reliable",
            'title_2': ": solutions that drive results",
            'title_3': "| Everything you need to grow",
            'desc_1': "{domain} helps you get measurable results. Explore features, stories and pricing — start today.",
            'desc_2': "Modern {domain} with impact. See how teams ship better experiences. Try now.",
            'h1_1': "{domain} that gets the job done.",
            'h1_2': "Build, ship and grow with {domain}.",
            'product_1': "Value prop in 1–2 lines → 2–3 benefits with proof → single CTA.",
            'product_2': "Problem → outcome → proof → CTA. Keep it scannable (40–80 words)."
        },
        'fi': {
            'title_1': "— nopea, moderni & luotettava",
            'title_2': ": ratkaisut jotka tuottavat tuloksia",
            'title_3': "| Kaikki mitä tarvitset kasvuun",
            'desc_1': "{domain} auttaa sinua saavuttamaan mitattavia tuloksia. Tutustu ominaisuuksiin, tarinoihin ja hinnoitteluun — aloita tänään.",
            'desc_2': "Moderni {domain} vaikuttavuudella. Katso miten tiimit toimittavat parempia kokemuksia. Kokeile nyt.",
            'h1_1': "{domain} joka hoitaa homman.",
            'h1_2': "Rakenna, toimita ja kasva {domain}:n kanssa.",
            'product_1': "Arvolupaus 1–2 rivillä → 2–3 hyötyä todisteineen → yksi CTA.",
            'product_2': "Ongelma → lopputulos → todiste → CTA. Pidä selkeänä (40–80 sanaa)."
        }
    },
    'creative_boldness': {
        'en': {
            'classification': {
                'radical': 'Radical',
                'bold': 'Bold',
                'safe': 'Safe',
                'timid': 'Timid'
            },
            'competitive_position': {
                'radical': 'Market disruptor - setting new creative standards',
                'bold': 'Creative leader - ahead of market norms',
                'safe': 'Following best practices - room for differentiation',
                'timid': 'Playing it safe - significant creative opportunity'
            },
            'observations': {
                'content_depth': 'Your content depth significantly exceeds competitors',
                'high_engagement': 'High engagement through interactive elements',
                'modern_design': 'Modern design language sets you apart',
                'competitive_moat': 'Overall digital maturity creates competitive moat',
                'default': 'Opportunity to differentiate through creative approaches'
            },
            'opportunities': {
                'visual': 'Enhance visual design with modern, bold aesthetics',
                'narrative': 'Strengthen narrative with deeper, more engaging content',
                'interactive': 'Add interactive elements to boost engagement',
                'social': 'Amplify social media presence for brand boldness',
                'content_depth': 'Expand content depth (currently {current} words vs avg {avg})'
            },
            'strategic_rec': {
                'radical': 'Maintain creative leadership while exploring even bolder experimental approaches',
                'bold': 'Push boundaries further to achieve radical differentiation',
                'safe': 'Inject more creative risk-taking to stand out from competitors',
                'timid': 'Break from conservative patterns - embrace bold, distinctive creative choices'
            },
            'visual_factors': {
                'rich_structure': 'Rich content structure ({current} headings vs avg {avg})',
                'good_structure': 'Good content structure ({current} headings)',
                'basic_structure': 'Basic structure ({current} headings)',
                'high_interactivity': 'High interactivity (engaging user experience)',
                'moderate_interactivity': 'Moderate interactivity',
                'limited_interactivity': 'Limited interactivity',
                'strong_social': 'Strong social media presence',
                'moderate_social': 'Moderate social presence',
                'minimal_social': 'Minimal social presence',
                'modern_design': 'Modern, cutting-edge design',
                'contemporary_design': 'Contemporary design',
                'traditional_design': 'Traditional design approach'
            },
            'narrative_factors': {
                'comprehensive': 'Comprehensive content ({current} words vs avg {avg})',
                'above_average': 'Above-average content depth ({current} words)',
                'standard': 'Standard content depth ({current} words)',
                'excellent_quality': 'Excellent content quality',
                'good_quality': 'Good content quality',
                'basic_quality': 'Basic content quality',
                'strong_seo': 'Strong SEO narrative',
                'decent_seo': 'Decent SEO presence',
                'weak_seo': 'Weak SEO narrative',
                'clear_positioning': 'Clear competitive positioning',
                'slight_edge': 'Slight competitive edge',
                'following_market': 'Following market standards'
            },
            'visual_score_label': 'Visual score: {score}/100. ',
            'narrative_score_label': 'Narrative score: {score}/100. '
        },
        'fi': {
            'classification': {
                'radical': 'Radikaali',
                'bold': 'Rohkea',
                'safe': 'Turvallinen',
                'timid': 'Arka'
            },
            'competitive_position': {
                'radical': 'Markkinoiden mullistaja - asettaa uusia luovia standardeja',
                'bold': 'Luova johtaja - markkinanormeja edellä',
                'safe': 'Seuraa parhaita käytäntöjä - tilaa erottautumiselle',
                'timid': 'Pelaa varman päälle - merkittävä luova mahdollisuus'
            },
            'observations': {
                'content_depth': 'Sisältösi syvyys ylittää merkittävästi kilpailijat',
                'high_engagement': 'Korkea sitoutuminen vuorovaikutteisten elementtien kautta',
                'modern_design': 'Moderni designkieli erottaa sinut joukosta',
                'competitive_moat': 'Yleinen digitaalinen kypsyys luo kilpailuetua',
                'default': 'Mahdollisuus erottautua luovien lähestymistapojen kautta'
            },
            'opportunities': {
                'visual': 'Paranna visuaalista suunnittelua modernilla, rohkealla estetiikalla',
                'narrative': 'Vahvista kerrontaa syvemmällä, sitouttavammalla sisällöllä',
                'interactive': 'Lisää vuorovaikutteisia elementtejä sitoutumisen kasvattamiseksi',
                'social': 'Vahvista sosiaalisen median läsnäoloa brändin rohkeudelle',
                'content_depth': 'Laajenna sisällön syvyyttä (nyt {current} sanaa vs keskiarvo {avg})'
            },
            'strategic_rec': {
                'radical': 'Säilytä luova johtajuus samalla kun tutkit vielä rohkeampia kokeellisia lähestymistapoja',
                'bold': 'Työnnä rajoja pidemmälle radikaalin erottautumisen saavuttamiseksi',
                'safe': 'Lisää luovaa riskinottoa erottuaksesi kilpailijoista',
                'timid': 'Murra konservatiivisista malleista - omaksu rohkeita, erottuvia luovia valintoja'
            },
            'visual_factors': {
                'rich_structure': 'Rikas sisältörakenne ({current} otsikkoa vs keskiarvo {avg})',
                'good_structure': 'Hyvä sisältörakenne ({current} otsikkoa)',
                'basic_structure': 'Perusrakenne ({current} otsikkoa)',
                'high_interactivity': 'Korkea vuorovaikutteisuus (sitouttava käyttökokemus)',
                'moderate_interactivity': 'Kohtalainen vuorovaikutteisuus',
                'limited_interactivity': 'Rajallinen vuorovaikutteisuus',
                'strong_social': 'Vahva sosiaalisen median läsnäolo',
                'moderate_social': 'Kohtalainen sosiaalinen läsnäolo',
                'minimal_social': 'Minimaalinen sosiaalinen läsnäolo',
                'modern_design': 'Moderni, huippuluokan muotoilu',
                'contemporary_design': 'Nykyaikainen muotoilu',
                'traditional_design': 'Perinteinen muotoilulähestymistapa'
            },
            'narrative_factors': {
                'comprehensive': 'Kattava sisältö ({current} sanaa vs keskiarvo {avg})',
                'above_average': 'Keskiarvoa parempi sisällön syvyys ({current} sanaa)',
                'standard': 'Tavanomainen sisällön syvyys ({current} sanaa)',
                'excellent_quality': 'Erinomainen sisällön laatu',
                'good_quality': 'Hyvä sisällön laatu',
                'basic_quality': 'Perussisällön laatu',
                'strong_seo': 'Vahva SEO-kerronta',
                'decent_seo': 'Kohtuullinen SEO-läsnäolo',
                'weak_seo': 'Heikko SEO-kerronta',
                'clear_positioning': 'Selkeä kilpailuasemointi',
                'slight_edge': 'Pieni kilpailuetu',
                'following_market': 'Seuraa markkinastandardeja'
            },
            'visual_score_label': 'Visuaalinen pisteet: {score}/100. ',
            'narrative_score_label': 'Narratiivin pisteet: {score}/100. '
        }
    }
}

def t(section: str, key: str, language: str = 'en', **kwargs) -> str:
    """
    Translation helper function.
    
    Args:
        section: Translation section (e.g., 'risk_register', 'creative_boldness')
        key: Translation key (can use dot notation for nested keys, e.g., 'classification.radical')
        language: Language code ('en' or 'fi')
        **kwargs: Variables for string formatting
    
    Returns:
        Translated string
    
    Examples:
        t('risk_register', 'thin_content', 'fi')
        t('creative_boldness', 'classification.radical', 'en')
        t('snippet_examples', 'desc_1', 'fi', domain='Example')
    """
    try:
        # Handle nested keys (e.g., 'classification.radical')
        keys = key.split('.')
        translation = TRANSLATIONS[section][language]
        
        for k in keys:
            translation = translation[k]
        
        # Format with kwargs if provided
        if kwargs:
            return translation.format(**kwargs)
        return translation
    except (KeyError, TypeError) as e:
        # Fallback to English if Finnish translation not found
        if language == 'fi':
            try:
                translation = TRANSLATIONS[section]['en']
                for k in keys:
                    translation = translation[k]
                if kwargs:
                    return translation.format(**kwargs)
                return translation
            except (KeyError, TypeError):
                return f"[Missing: {section}.{key}]"
        return f"[Missing: {section}.{key}]"
