  // Tabs + content
  const renderAnalysisContent = () => {
    if (!analysis) return null;

    const score = getScoreBreakdown();
    const features = getEnhancedFeatureCards();

    const overallScore = analysis.basic_analysis?.digital_maturity_score ?? 0;
    const seoScore = analysis.basic_analysis?.seo_score ?? score.seo;
    const techScore = analysis.basic_analysis?.technical_score ?? score.technical;
    const contentScore = analysis.basic_analysis?.content_score ?? score.content;

    const strengths = getAIField('strengths');
    const weaknesses = getAIField('weaknesses');
    const opportunities = getAIField('opportunities');
    const threats = getAIField('threats');
    const recommendations = getAIField('recommendations');

    const barChartData = [
      { label: 'SEO', value: score.seo, icon: <Search className="w-4 h-4" /> },
      { label: 'Technical', value: score.technical, icon: <Code className="w-4 h-4" /> },
      { label: 'Content', value: score.content, icon: <FileText className="w-4 h-4" /> },
      { label: 'Mobile', value: score.user_experience, icon: <Smartphone className="w-4 h-4" /> },
      { label: 'Security', value: score.security, icon: <Shield className="w-4 h-4" /> },
      { label: 'Performance', value: score.performance, icon: <Rocket className="w-4 h-4" /> },
      { label: 'Social', value: score.social, icon: <Users className="w-4 h-4" /> },
    ];

    const radarChartData = [
      { label: 'SEO', value: score.seo },
      { label: 'Technical', value: score.technical },
      { label: 'Content', value: score.content },
      { label: 'Mobile', value: score.user_experience },
      { label: 'Security', value: score.security },
      { label: 'Performance', value: score.performance },
    ];

    const tabs = {
      overview: {
        title: 'Overview',
        icon: <BarChart3 className="w-4 h-4" />,
        content: (
          <div className="space-y-8">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
              <div className="bg-black/40 border border-green-400/30 rounded-xl p-4 md:p-6 text-center">
                <CircleProgress value={overallScore} label="Overall Score" size={110} />
              </div>
              <div className="bg-black/40 border border-blue-400/30 rounded-xl p-4 md:p-6 text-center">
                <CircleProgress value={seoScore} label="SEO" size={110} />
              </div>
              <div className="bg-black/40 border border-purple-400/30 rounded-xl p-4 md:p-6 text-center">
                <CircleProgress value={techScore} label="Technical" size={110} />
              </div>
              <div className="bg-black/40 border border-orange-400/30 rounded-xl p-4 md:p-6 text-center">
                <CircleProgress value={contentScore} label="Content" size={110} />
              </div>
            </div>

            <div className="p-6 rounded-xl bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-400/30">
              <h4 className="text-xl font-semibold text-white mb-4 flex items-center">
                <Brain className="w-6 h-6 mr-3 text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400" />
                <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  AI Executive Summary
                </span>
              </h4>
              <div className="space-y-3 text-gray-200 leading-relaxed text-[15px]">
                {executiveSummaryLong.split('. ').map((p, idx) => (
                  p.trim().length ? <p key={idx}>{p.trim().replace(/\.$/, '')}.</p> : null
                ))}
              </div>
            </div>

            <div className="p-6 rounded-xl bg-black/40 border border-green-400/30">
              <h4 className="text-lg font-semibold text-white mb-6 flex items-center">
                <PieChart className="w-5 h-5 mr-2 text-green-400" />
                Score Breakdown
              </h4>
              <div className="-mx-2 sm:mx-0">
                <BarChart data={barChartData} height={250} />
              </div>
            </div>

            <div className="p-6 rounded-xl bg-gradient-to-br from-purple-500/10 to-blue-500/10 border border-purple-400/30">
              <h4 className="text-lg font-semibold text-white mb-6 flex items-center">
                <Activity className="w-5 h-5 mr-2 text-purple-400" />
                Performance Profile
              </h4>
              <div className="flex justify-center">
                <RadarChart data={radarChartData} size={320} />
              </div>
            </div>

            {features.length > 0 && (
              <div className="p-6 rounded-xl bg-gradient-to-br from-purple-500/10 to-pink-500/10 border border-purple-400/30">
                <h4 className="text-lg font-semibold text-white mb-6 flex items-center">
                  <Sparkles className="w-5 h-5 mr-2 text-purple-400" />
                  Enhanced Analysis
                  <span className="ml-auto bg-purple-400/20 text-purple-400 px-3 py-1 rounded-full text-sm">
                    {features.length} insights
                  </span>
                </h4>
                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {features.map((f, i) => {
                    const getStatusColor = (status) => {
                      switch(status) {
                        case 'ready':
                        case 'above_average': 
                        case 'competitive':
                          return 'text-green-400 bg-green-400/10 border-green-400/20';
                        case 'not_ready':
                        case 'below_average':
                        case 'attention':
                          return 'text-red-400 bg-red-400/10 border-red-400/20';
                        case 'needs_improvement':
                        case 'Medium':
                          return 'text-orange-400 bg-orange-400/10 border-orange-400/20';
                        default:
                          return 'text-blue-400 bg-blue-400/10 border-blue-400/20';
                      }
                    };
                    const statusColor = getStatusColor(f.status);
                    return (
                      <div key={i} className="p-4 rounded-lg bg-black/30 border border-purple-400/20 hover:border-purple-400/40 transition-all group">
                        <div className="flex items-start justify-between mb-3">
                          <span className="text-white font-medium text-sm group-hover:text-purple-300 transition-colors">
                            {f.name}
                          </span>
                          <div className="text-purple-400 opacity-70 group-hover:opacity-100 transition-opacity">
                            {f.icon}
                          </div>
                        </div>
                        <div className="mb-2">
                          <p className="text-green-400 font-bold text-lg leading-tight">
                            {f.value}
                          </p>
                        </div>
                        {f.description && (
                          <p className="text-xs text-gray-400 mb-3 leading-relaxed">
                            {f.description}
                          </p>
                        )}
                        {f.status && (
                          <div className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border mb-3 ${statusColor}`}>
                            {f.status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </div>
                        )}
                        {Array.isArray(f.items) && f.items.length > 0 && (
                          <div className="space-y-1 mb-3">
                            <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                              Key Points:
                            </div>
                            <ul className="space-y-1">
                              {f.items.slice(0, 3).map((item, idx) => (
                                <li key={idx} className="text-xs text-gray-300 flex items-start">
                                  <span className="w-1 h-1 bg-purple-400 rounded-full mt-1.5 mr-2 flex-shrink-0" />
                                  <span className="leading-relaxed">{item}</span>
                                </li>
                              ))}
                              {f.items.length > 3 && (
                                <li className="text-xs text-gray-500 italic">
                                  and {f.items.length - 3} more...
                                </li>
                              )}
                            </ul>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )
      },

      swot: {
        title: 'SWOT Analysis',
        icon: <Layers className="w-4 h-4" />,
        content: (
          <div className="space-y-6">
            <div className="grid md:grid-cols-2 gap-6">
              <div className="p-6 rounded-xl bg-gradient-to-br from-green-500/10 to-blue-500/10 border border-green-400/30">
                <div className="flex items-center mb-4">
                  <div className="p-2 rounded-lg bg-green-400/20 mr-3"><CheckCircle className="w-5 h-5 text-green-400" /></div>
                  <h4 className="text-lg font-semibold text-white">Strengths</h4>
                </div>
                <div className="space-y-3">
                  {strengths.length ? strengths.map((t, i) => (
                    <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-black/20">
                      <span className="text-green-400 text-sm font-bold mt-0.5">#{i+1}</span>
                      <p className="text-gray-300 text-sm leading-relaxed">{t}</p>
                    </div>
                  )) : <p className="text-gray-500 italic text-sm">No strengths identified</p>}
                </div>
              </div>
              <div className="p-6 rounded-xl bg-gradient-to-br from-red-500/10 to-orange-500/10 border border-red-400/30">
                <div className="flex items-center mb-4">
                  <div className="p-2 rounded-lg bg-red-400/20 mr-3"><XCircle className="w-5 h-5 text-red-400" /></div>
                  <h4 className="text-lg font-semibold text-white">Weaknesses</h4>
                </div>
                <div className="space-y-3">
                  {weaknesses.length ? weaknesses.map((t, i) => (
                    <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-black/20">
                      <span className="text-red-400 text-sm font-bold mt-0.5">#{i+1}</span>
                      <p className="text-gray-300 text-sm leading-relaxed">{t}</p>
                    </div>
                  )) : <p className="text-gray-500 italic text-sm">No weaknesses identified</p>}
                </div>
              </div>
              <div className="p-6 rounded-xl bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-400/30">
                <div className="flex items-center mb-4">
                  <div className="p-2 rounded-lg bg-blue-400/20 mr-3"><Zap className="w-5 h-5 text-blue-400" /></div>
                  <h4 className="text-lg font-semibold text-white">Opportunities</h4>
                </div>
                <div className="space-y-3">
                  {opportunities.length ? opportunities.map((t, i) => (
                    <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-black/20">
                      <span className="text-blue-400 text-sm font-bold mt-0.5">#{i+1}</span>
                      <p className="text-gray-300 text-sm leading-relaxed">{t}</p>
                    </div>
                  )) : <p className="text-gray-500 italic text-sm">No opportunities identified</p>}
                </div>
              </div>
              <div className="p-6 rounded-xl bg-gradient-to-br from-orange-500/10 to-red-500/10 border border-orange-400/30">
                <div className="flex items-center mb-4">
                  <div className="p-2 rounded-lg bg-orange-400/20 mr-3"><AlertTriangle className="w-5 h-5 text-orange-400" /></div>
                  <h4 className="text-lg font-semibold text-white">Threats</h4>
                </div>
                <div className="space-y-3">
                  {threats.length ? threats.map((t, i) => (
                    <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-black/20">
                      <span className="text-orange-400 text-sm font-bold mt-0.5">#{i+1}</span>
                      <p className="text-gray-300 text-sm leading-relaxed">{t}</p>
                    </div>
                  )) : <p className="text-gray-500 italic text-sm">No threats identified</p>}
                </div>
              </div>
            </div>
          </div>
        )
      },

      technical: {
        title: 'Technical Analysis',
        icon: <Settings className="w-4 h-4" />,
        content: (
          <div className="space-y-6">
            <div className="p-6 rounded-xl bg-gradient-to-br from-green-500/10 to-blue-500/10 border border-green-400/30">
              <h4 className="text-lg font-semibold text-white mb-6 flex items-center">
                <Code className="w-5 h-5 mr-2 text-green-400" />
                Technical Metrics
              </h4>
              <div className="space-y-4">
                <ScoreBar label="Technical Implementation" score={score.technical} icon={<Code className="w-4 h-4" />} />
                <ScoreBar label="Performance" score={score.performance} icon={<Gauge className="w-4 h-4" />} />
                <ScoreBar label="Security" score={score.security} icon={<Shield className="w-4 h-4" />} />
                <ScoreBar label="Mobile Optimization" score={score.user_experience} icon={<Smartphone className="w-4 h-4" />} />
                <ScoreBar label="Accessibility" score={score.accessibility} icon={<Eye className="w-4 h-4" />} />
                <ScoreBar label="SEO" score={score.seo} icon={<Search className="w-4 h-4" />} />
              </div>
            </div>
          </div>
        )
      },

      actions: {
        title: 'Actionable Items',
        icon: <ListChecks className="w-4 h-4" />,
        content: (
          <div className="space-y-6">
            {(() => {
              const buckets = getSmartActions();
              const all = [...buckets.critical, ...buckets.high, ...buckets.medium, ...buckets.low];
              if (!all.length) return <div className="text-center py-8 text-gray-400">No actionable items available</div>;
              return (
                <div className="space-y-6">
                  {buckets.critical.length > 0 && (
                    <div>
                      <h5 className="text-red-400 font-semibold mb-3 flex items-center">
                        <AlertTriangle className="w-4 h-4 mr-2 animate-pulse" />
                        Critical Actions
                      </h5>
                      <div className="space-y-3">
                        {buckets.critical.map((a, i) => <ActionCard key={`c${i}`} action={a} priority="critical" />)}
                      </div>
                    </div>
                  )}
                  {buckets.high.length > 0 && (
                    <div>
                      <h5 className="text-orange-400 font-semibold mb-3 flex items-center">
                        <ArrowUpRight className="w-4 h-4 mr-2" />
                        High Priority Actions
                      </h5>
                      <div className="space-y-3">
                        {buckets.high.map((a, i) => <ActionCard key={`h${i}`} action={a} priority="high" />)}
                      </div>
                    </div>
                  )}
                  {buckets.medium.length > 0 && (
                    <div>
                      <h5 className="text-yellow-400 font-semibold mb-3 flex items-center">
                        <Target className="w-4 h-4 mr-2" />
                        Medium Priority Actions
                      </h5>
                      <div className="space-y-3">
                        {buckets.medium.map((a, i) => <ActionCard key={`m${i}`} action={a} priority="medium" />)}
                      </div>
                    </div>
                  )}
                  {buckets.low.length > 0 && (
                    <div>
                      <h5 className="text-green-400 font-semibold mb-3 flex items-center">
                        <CheckCircle className="w-4 h-4 mr-2" />
                        Low Priority Actions
                      </h5>
                      <div className="space-y-3">
                        {buckets.low.map((a, i) => <ActionCard key={`l${i}`} action={a} priority="low" />)}
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        )
      },

      recommendations: {
        title: 'Recommendations',
        icon: <BookOpen className="w-4 h-4" />,
        content: (
          <div className="space-y-6">
            {recommendations.length > 0 && (
              <div className="p-6 rounded-xl bg-gradient-to-br from-purple-500/10 to-blue-500/10 border border-purple-400/30">
                <div className="flex items-center mb-6">
                  <Target className="w-6 h-6 text-purple-400 mr-3" />
                  <h4 className="text-xl font-semibold text-white">Strategic Recommendations</h4>
                  <span className="ml-auto bg-purple-400/20 text-purple-400 px-3 py-1 rounded-full text-sm">
                    {recommendations.length} items
                  </span>
                </div>
                <div className="grid gap-4">
                  {recommendations.map((rec, idx) => (
                    <div key={idx} className="bg-gradient-to-r from-purple-500/10 to-blue-500/10 border border-purple-400/30 rounded-xl p-5">
                      <div className="flex items-start gap-3">
                        <div className="p-2 rounded-lg bg-purple-400/20"><Target className="w-5 h-5 text-purple-400" /></div>
                        <div className="flex-1">
                          <span className="text-purple-400 font-semibold text-sm">#{idx + 1}</span>
                          <p className="text-gray-300 mt-1">{rec}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {recommendations.length === 0 && (
              <div className="text-center py-8 text-gray-400">No recommendations available</div>
            )}
          </div>
        )
      },
    };

    return (
      <div>
        <div className="flex flex-wrap gap-2 mb-8 p-2 bg-black/30 backdrop-blur-xl rounded-xl border border-green-400/30">
          {Object.entries(tabs).map(([key, tab]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-sm font-medium rounded-lg transition-all ${
                activeTab === key
                  ? 'bg-gradient-to-r from-green-400 to-blue-500 text-white shadow-lg shadow-green-400/25'
                  : 'text-gray-400 hover:text-white hover:bg-white/10'
              }`}
            >
              {tab.icon}
              <span>{tab.title}</span>
            </button>
          ))}
        </div>

        <div className="animate-fadeIn">
          {tabs[activeTab]?.content}
        </div>
      </div>
    );
  };

  // Conditional returns: login / upgrade / main
  if (showLogin) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 flex items-center justify-center px-4">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-to-br from-green-400/10 via-transparent to-transparent rounded-full blur-3xl" />
          <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-to-tl from-blue-400/10 via-transparent to-transparent rounded-full blur-3xl" />
        </div>

        <div className="relative z-10 max-w-md w-full">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-green-400 to-blue-500 rounded-2xl mb-4 shadow-lg shadow-green-400/25">
              <Brain className="w-10 h-10 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white mb-2">Competitor Analysis Tool</h1>
            <p className="text-gray-400">Choose your access level to continue</p>
          </div>

          <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-8 shadow-2xl">
            {!showAdminPrompt ? (
              <div className="space-y-4">
                <button
                  onClick={handleUserLogin}
                  className="w-full group relative overflow-hidden rounded-xl p-6 bg-gradient-to-r from-blue-500/10 to-green-500/10 border border-blue-400/30 hover:border-blue-400/50 transition-all duration-300"
                >
                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-3">
                      <User className="w-8 h-8 text-blue-400" />
                      <span className="text-xs bg-blue-400/20 text-blue-400 px-2 py-1 rounded-full">Free Trial</span>
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-2">Free User Access</h3>
                    <p className="text-gray-400 text-sm">Get started with {FREE_LIMIT} free analyses to explore the tool</p>
                  </div>
                  <div className="absolute inset-0 bg-gradient-to-r from-blue-400/5 to-green-400/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                </button>

                <button
                  onClick={() => setShowAdminPrompt(true)}
                  className="w-full group relative overflow-hidden rounded-xl p-6 bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-400/30 hover:border-purple-400/50 transition-all duration-300"
                >
                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-3">
                      <ShieldCheck className="w-8 h-8 text-purple-400" />
                      <span className="text-xs bg-purple-400/20 text-purple-400 px-2 py-1 rounded-full">Full Access</span>
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-2">Admin Access</h3>
                    <p className="text-gray-400 text-sm">Unlimited analyses with advanced features</p>
                  </div>
                  <div className="absolute inset-0 bg-gradient-to-r from-purple-400/5 to-pink-400/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                </button>

                {loginError && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-400/30">
                    <p className="text-red-400 text-sm">{loginError}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <button onClick={() => setShowAdminPrompt(false)} className="text-gray-400 hover:text-white transition-colors mb-2">← Back</button>
                <div className="text-center mb-6">
                  <ShieldCheck className="w-12 h-12 text-purple-400 mx-auto mb-3" />
                  <h3 className="text-xl font-semibold text-white">Admin Login</h3>
                  <p className="text-gray-400 text-sm mt-2">Enter password for unlimited access</p>
                </div>
                <input
                  type="password"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAdminLogin()}
                  placeholder="Admin password"
                  className="w-full px-4 py-3 bg-black/30 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-purple-400 focus:outline-none transition-colors"
                />
                <button
                  onClick={handleAdminLogin}
                  className="w-full py-3 bg-gradient-to-r from-purple-400 to-pink-400 text-white font-semibold rounded-lg hover:shadow-lg hover:shadow-purple-400/25 transition-all duration-300"
                >
                  Login as Admin
                </button>
                {loginError && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-400/30">
                    <p className="text-red-400 text-sm">{loginError}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (showUpgradeModal) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 flex items-center justify-center px-4">
        <div className="relative z-10 max-w-md w-full">
          <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-8 shadow-2xl">
            <div className="text-center mb-6">
              <Lock className="w-16 h-16 text-yellow-400 mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Free Limit Reached</h2>
              <p className="text-gray-400">You've used all {FREE_LIMIT} free analyses. Upgrade for unlimited access.</p>
            </div>
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-400/30">
                <h3 className="font-semibold text-white mb-2">Premium Features:</h3>
                <ul className="space-y-2 text-sm text-gray-300">
                  <li className="flex items-center"><CheckCircle className="w-4 h-4 text-green-400 mr-2" />Unlimited analyses</li>
                  <li className="flex items-center"><CheckCircle className="w-4 h-4 text-green-400 mr-2" />Priority processing</li>
                  <li className="flex items-center"><CheckCircle className="w-4 h-4 text-green-400 mr-2" />Advanced insights</li>
                  <li className="flex items-center"><CheckCircle className="w-4 h-4 text-green-400 mr-2" />Export reports</li>
                </ul>
              </div>
              <button
                onClick={() => setShowAdminPrompt(true)}
                className="w-full py-3 bg-gradient-to-r from-purple-400 to-pink-400 text-white font-semibold rounded-lg hover:shadow-lg hover:shadow-purple-400/25 transition-all"
              >
                Upgrade to Admin
              </button>
              <button
                onClick={handleLogout}
                className="w-full py-3 bg-gray-800 text-gray-300 font-semibold rounded-lg hover:bg-gray-700 transition-all"
              >
                Logout
              </button>
            </div>

            {showAdminPrompt && (
              <div className="mt-6 space-y-4 pt-6 border-t border-gray-700">
                <input
                  type="password"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAdminLogin()}
                  placeholder="Enter admin password"
                  className="w-full px-4 py-3 bg-black/30 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-purple-400 focus:outline-none"
                />
                <button
                  onClick={handleAdminLogin}
                  className="w-full py-3 bg-gradient-to-r from-purple-400 to-pink-400 text-white font-semibold rounded-lg"
                >
                  Login as Admin
                </button>
                {loginError && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-400/30">
                    <p className="text-red-400 text-sm">{loginError}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Main analysis screen
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-to-br from-green-400/10 via-transparent to-transparent rounded-full blur-3xl" />
        <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-to-tl from-blue-400/10 via-transparent to-transparent rounded-full blur-3xl" />
      </div>

      <div className="relative z-10">
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-4">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-gradient-to-br from-green-400 to-blue-500 rounded-xl shadow-lg shadow-green-400/25">
                <Brain className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Competitor Analysis</h1>
                <p className="text-gray-400 text-sm">AI-powered website analysis</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 px-4 py-2 bg-black/30 rounded-lg border border-gray-700">
                <User className="w-4 h-4 text-gray-400" />
                <span className="text-sm text-gray-300">
                  {userRole === 'admin' ? 'Admin' : (userRole || 'Free User')}
                </span>
                {(userRole === 'user' || userRole === 'viewer') && (
                  <span className="text-xs bg-blue-400/20 text-blue-400 px-2 py-0.5 rounded-full ml-2">
                    {Math.max(0, FREE_LIMIT - userSearchCount)} left
                  </span>
                )}
              </div>
              
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-4 py-2 bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500/20 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span className="text-sm">Logout</span>
              </button>
            </div>
          </div>

          <div className="max-w-4xl mx-auto mb-8">
            <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-6">
              <label className="block text-gray-300 text-sm font-medium mb-3">Enter website URL to analyze</label>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                  placeholder="https://example.com"
                  className="flex-1 px-4 py-3 bg-black/30 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-green-400 focus:outline-none transition-colors"
                  disabled={loading}
                />
                <button
                  onClick={handleAnalyze}
                  disabled={loading || !url}
                  className="px-6 py-3 bg-gradient-to-r from-green-400 to-blue-500 text-white font-semibold rounded-lg hover:shadow-lg hover:shadow-green-400/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Analyze'}
                </button>
              </div>
              
              {error && (
                <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-400/30">
                  <p className="text-red-400 text-sm">{error}</p>
                </div>
              )}
              
              {(userRole === 'user' || userRole === 'viewer') && (
                <div className="mt-4 p-3 rounded-lg bg-blue-500/10 border border-blue-400/30">
                  <p className="text-blue-400 text-sm">
                    Free tier: {userSearchCount}/{FREE_LIMIT} analyses used
                  </p>
                </div>
              )}
            </div>
          </div>

          {loading && (
            <div className="max-w-4xl mx-auto">
              <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-12">
                <div className="flex flex-col items-center justify-center">
                  <Loader2 className="w-12 h-12 text-green-400 animate-spin mb-4" />
                  <h3 className="text-xl font-semibold text-white mb-2">Analyzing Website...</h3>
                  <p className="text-gray-400 text-center">
                    Our AI is performing a comprehensive analysis of the website.
                    <br />This usually takes 10-30 seconds.
                  </p>
                </div>
              </div>
            </div>
          )}

          {!loading && analysis && (
            <div className="max-w-7xl mx-auto">
              <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-2xl font-bold text-white mb-1">Analysis Results</h2>
                    <p className="text-gray-400">{analysis.basic_analysis?.website || url}</p>
                  </div>
                  <button
                    onClick={handlePrint}
                    className="flex items-center gap-2 px-4 py-2 bg-black/30 border border-gray-700 rounded-lg hover:border-gray-600 transition-colors"
                  >
                    <Download className="w-4 h-4 text-gray-400" />
                    <span className="text-sm text-gray-300">Export PDF</span>
                  </button>
                </div>
                {renderAnalysisContent()}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CompetitorAnalysis;
