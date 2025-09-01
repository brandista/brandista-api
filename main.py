@app.post("/api/v1/generate-pdf-base64")
async def generate_pdf_base64(analysis_data: Dict[str, Any]):
    """
    Generoi PDF-raportti base64-muodossa kielituella (fi/en)
    """
    try:
        # Get language from request, default to Finnish
        language = analysis_data.get('language', 'fi')
        
        # Translations
        translations = {
            'fi': {
                'title': 'Kilpailija-analyysi',
                'basic_info': 'Perustiedot',
                'company': 'Yritys',
                'website': 'Verkkosivusto',
                'industry': 'Toimiala',
                'analysis_date': 'Analyysipäivä',
                'not_known': 'Ei tiedossa',
                'not_defined': 'Ei määritelty',
                'summary': 'Yhteenveto',
                'swot_analysis': 'SWOT-analyysi',
                'strengths': 'Vahvuudet',
                'weaknesses': 'Heikkoudet',
                'opportunities': 'Mahdollisuudet',
                'threats': 'Uhat',
                'digital_footprint': 'Digitaalinen jalanjälki',
                'score': 'Arvio',
                'active_channels': 'Aktiiviset kanavat',
                'content_strategy': 'Sisältöstrategia',
                'recommendations': 'Toimenpidesuositukset',
                'action': 'Toimenpide',
                'priority': 'Prioriteetti',
                'timeline': 'Aikataulu',
                'differentiation': 'Erottautumiskeinot',
                'quick_wins': 'Nopeat voitot',
                'high': 'korkea',
                'medium': 'keskitaso',
                'low': 'matala'
            },
            'en': {
                'title': 'Competitor Analysis',
                'basic_info': 'Basic Information',
                'company': 'Company',
                'website': 'Website',
                'industry': 'Industry',
                'analysis_date': 'Analysis Date',
                'not_known': 'Not known',
                'not_defined': 'Not defined',
                'summary': 'Summary',
                'swot_analysis': 'SWOT Analysis',
                'strengths': 'Strengths',
                'weaknesses': 'Weaknesses',
                'opportunities': 'Opportunities',
                'threats': 'Threats',
                'digital_footprint': 'Digital Footprint',
                'score': 'Score',
                'active_channels': 'Active Channels',
                'content_strategy': 'Content Strategy',
                'recommendations': 'Recommendations',
                'action': 'Action',
                'priority': 'Priority',
                'timeline': 'Timeline',
                'differentiation': 'Differentiation Methods',
                'quick_wins': 'Quick Wins',
                'high': 'high',
                'medium': 'medium',
                'low': 'low'
            }
        }
        
        # Get translations for current language
        t = translations.get(language, translations['fi'])
        
        # Luo BytesIO buffer PDFää varten
        buffer = BytesIO()
        
        # Luo PDF dokumentti
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Hae tyylit
        styles = getSampleStyleSheet()
        
        # Luo custom tyylit
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        )
        
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=13,
            textColor=colors.HexColor('#475569'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#334155'),
            alignment=TA_JUSTIFY,
            spaceAfter=8
        )
        
        # Story - PDF sisältö
        story = []
        
        # Otsikko
        company_name = analysis_data.get('company_name', 'Unknown')
        story.append(Paragraph(f"{t['title']}: {company_name}", title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 20))
        
        # Perustiedot
        story.append(Paragraph(t['basic_info'], heading_style))
        
        basic_info = analysis_data.get('basic_analysis', {})
        basic_data = [
            [f"{t['company']}:", company_name],
            [f"{t['website']}:", analysis_data.get('url', basic_info.get('website', t['not_known']))],
            [f"{t['industry']}:", basic_info.get('industry', t['not_defined'])],
            [f"{t['analysis_date']}:", analysis_data.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))]
        ]
        
        basic_table = Table(basic_data, colWidths=[5*cm, 12*cm])
        basic_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#475569')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#334155')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(basic_table)
        story.append(Spacer(1, 20))
        
        # AI-analyysi
        ai_analysis = analysis_data.get('ai_analysis', {})
        
        if ai_analysis:
            # Yhteenveto / Summary
            summary_key = 'yhteenveto' if language == 'fi' else 'summary'
            if ai_analysis.get('yhteenveto') or ai_analysis.get('summary'):
                story.append(Paragraph(t['summary'], heading_style))
                summary_text = ai_analysis.get('yhteenveto', ai_analysis.get('summary', ''))
                story.append(Paragraph(summary_text, normal_style))
                story.append(Spacer(1, 20))
            
            # SWOT-analyysi
            story.append(Paragraph(t['swot_analysis'], heading_style))
            
            # Vahvuudet / Strengths
            strengths_key = 'vahvuudet' if language == 'fi' else 'strengths'
            if ai_analysis.get('vahvuudet') or ai_analysis.get('strengths'):
                story.append(Paragraph(t['strengths'], subheading_style))
                strengths = ai_analysis.get('vahvuudet', ai_analysis.get('strengths', []))
                for strength in strengths:
                    story.append(Paragraph(f"• {strength}", normal_style))
                story.append(Spacer(1, 10))
            
            # Heikkoudet / Weaknesses
            weaknesses_key = 'heikkoudet' if language == 'fi' else 'weaknesses'
            if ai_analysis.get('heikkoudet') or ai_analysis.get('weaknesses'):
                story.append(Paragraph(t['weaknesses'], subheading_style))
                weaknesses = ai_analysis.get('heikkoudet', ai_analysis.get('weaknesses', []))
                for weakness in weaknesses:
                    story.append(Paragraph(f"• {weakness}", normal_style))
                story.append(Spacer(1, 10))
            
            # Mahdollisuudet / Opportunities
            opportunities_key = 'mahdollisuudet' if language == 'fi' else 'opportunities'
            if ai_analysis.get('mahdollisuudet') or ai_analysis.get('opportunities'):
                story.append(Paragraph(t['opportunities'], subheading_style))
                opportunities = ai_analysis.get('mahdollisuudet', ai_analysis.get('opportunities', []))
                for opportunity in opportunities:
                    story.append(Paragraph(f"• {opportunity}", normal_style))
                story.append(Spacer(1, 10))
            
            # Uhat / Threats
            threats_key = 'uhat' if language == 'fi' else 'threats'
            if ai_analysis.get('uhat') or ai_analysis.get('threats'):
                story.append(Paragraph(t['threats'], subheading_style))
                threats = ai_analysis.get('uhat', ai_analysis.get('threats', []))
                for threat in threats:
                    story.append(Paragraph(f"• {threat}", normal_style))
                story.append(Spacer(1, 20))
            
            # Digitaalinen jalanjälki / Digital Footprint
            digi_key = 'digitaalinen_jalanjalki' if language == 'fi' else 'digital_footprint'
            if ai_analysis.get('digitaalinen_jalanjalki') or ai_analysis.get('digital_footprint'):
                story.append(Paragraph(t['digital_footprint'], heading_style))
                digi = ai_analysis.get('digitaalinen_jalanjalki', ai_analysis.get('digital_footprint', {}))
                
                if digi.get('arvio') or digi.get('score'):
                    score = digi.get('arvio', digi.get('score', 0))
                    story.append(Paragraph(f"<b>{t['score']}:</b> {score}/10", normal_style))
                
                if digi.get('sosiaalinen_media') or digi.get('social_media'):
                    story.append(Paragraph(f"<b>{t['active_channels']}:</b>", normal_style))
                    channels = digi.get('sosiaalinen_media', digi.get('social_media', []))
                    for channel in channels:
                        story.append(Paragraph(f"• {channel}", normal_style))
                
                if digi.get('sisaltostrategia') or digi.get('content_strategy'):
                    strategy = digi.get('sisaltostrategia', digi.get('content_strategy', ''))
                    story.append(Paragraph(f"<b>{t['content_strategy']}:</b> {strategy}", normal_style))
                
                story.append(Spacer(1, 20))
            
            # Toimenpidesuositukset / Recommendations
            recs_key = 'toimenpidesuositukset' if language == 'fi' else 'recommendations'
            if ai_analysis.get('toimenpidesuositukset') or ai_analysis.get('recommendations'):
                story.append(PageBreak())  # Uusi sivu toimenpiteille
                story.append(Paragraph(t['recommendations'], heading_style))
                
                recommendations = ai_analysis.get('toimenpidesuositukset', ai_analysis.get('recommendations', []))
                for idx, rec in enumerate(recommendations, 1):
                    # Handle both dict and string formats
                    if isinstance(rec, dict):
                        title = rec.get('otsikko', rec.get('title', f"{t['action']} {idx}"))
                        story.append(Paragraph(f"{idx}. {title}", subheading_style))
                        
                        if rec.get('kuvaus') or rec.get('description'):
                            desc = rec.get('kuvaus', rec.get('description', ''))
                            story.append(Paragraph(desc, normal_style))
                        
                        details = []
                        if rec.get('prioriteetti') or rec.get('priority'):
                            priority = rec.get('prioriteetti', rec.get('priority', ''))
                            # Map priority colors
                            if priority in ['korkea', 'high']:
                                color = '#dc2626'
                                priority_text = t['high']
                            elif priority in ['keskitaso', 'medium']:
                                color = '#f59e0b'
                                priority_text = t['medium']
                            else:
                                color = '#10b981'
                                priority_text = t['low']
                            details.append(f"<font color='{color}'><b>{t['priority']}:</b> {priority_text}</font>")
                        
                        if rec.get('aikataulu') or rec.get('timeline'):
                            timeline = rec.get('aikataulu', rec.get('timeline', ''))
                            details.append(f"<b>{t['timeline']}:</b> {timeline}")
                        
                        if details:
                            story.append(Paragraph(" | ".join(details), normal_style))
                    else:
                        # If recommendation is a string
                        story.append(Paragraph(f"{idx}. {rec}", normal_style))
                    
                    story.append(Spacer(1, 15))
            
            # Erottautumiskeinot / Differentiation
            diff_key = 'erottautumiskeinot' if language == 'fi' else 'differentiation'
            if ai_analysis.get('erottautumiskeinot') or ai_analysis.get('differentiation'):
                story.append(Paragraph(t['differentiation'], heading_style))
                methods = ai_analysis.get('erottautumiskeinot', ai_analysis.get('differentiation', []))
                for method in methods:
                    story.append(Paragraph(f"• {method}", normal_style))
                story.append(Spacer(1, 20))
            
            # Quick Wins
            if ai_analysis.get('quick_wins'):
                story.append(Paragraph(t['quick_wins'], heading_style))
                for win in ai_analysis.get('quick_wins', []):
                    story.append(Paragraph(f"✓ {win}", normal_style))
        
        # Generoi PDF
        doc.build(story)
        
        # Muunna base64:ksi
        buffer.seek(0)
        pdf_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        
        # Generate filename with language suffix
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        lang_suffix = 'en' if language == 'en' else 'fi'
        safe_company_name = company_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        filename = f"competitor_analysis_{safe_company_name}_{timestamp}_{lang_suffix}.pdf"
        
        return {
            "success": True,
            "pdf_base64": pdf_base64,
            "filename": filename
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
