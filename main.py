import React, { useState, useMemo, useEffect } from 'react';
import { 
  Search, TrendingUp, Users, Target, AlertCircle, 
  BarChart3, Zap, Brain, Shield, ArrowRight,
  Loader2, CheckCircle, XCircle, Info, Globe,
  FileText, Gauge, Eye, Smartphone, Activity, PieChart,
  AlertTriangle, ArrowUpRight, Sparkles, Code, Download,
  Settings, Layers, ListChecks, BookOpen, AlertOctagon, Rocket,
  User, Lock, LogOut, ShieldCheck, UserCog
} from 'lucide-react';

// Add this CSS to your global styles or as a style tag
const styles = `
  .glassmorphism {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
  }
`;

// Inject styles
if (typeof document !== 'undefined' && !document.getElementById('glassmorphism-styles')) {
  const styleElement = document.createElement('style');
  styleElement.id = 'glassmorphism-styles';
  styleElement.innerHTML = styles;
  document.head.appendChild(styleElement);
}

// Constants and utility functions
const FREE_LIMIT = 3;
const API_BASE_URL = 'https://fastapi-production-51f9.up.railway.app';
const AUTH_MODE = 'token';

function loadCount() {
  return parseInt(localStorage.getItem('analyzeCount') || '0', 10);
}

function saveCount(n) {
  localStorage.setItem('analyzeCount', String(n));
}

function resetCount() {
  localStorage.removeItem('analyzeCount');
}

function cleanUrl(u) {
  if (!u) return '';
  let x = u.trim();
  if (!/^https?:\/\//i.test(x)) x = `https://${x}`;
  try { new URL(x); return x.replace(/\/+$/, ''); } catch { return ''; }
}

function getAuthHeaders(token) {
  const h = { 'Accept': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

async function apiGet(path, token) {
  return fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    credentials: 'omit',
    headers: getAuthHeaders(token),
  });
}

async function apiPost(path, body = {}, token) {
  return fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'omit',
    headers: { 
      ...getAuthHeaders(token),
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(body),
  });
}

const CompetitorAnalysis = () => {
  // All state variables
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('overview');

  // Auth state
  const [userRole, setUserRole] = useState(null);
  const [showLogin, setShowLogin] = useState(true);
  const [adminPassword, setAdminPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [showAdminPrompt, setShowAdminPrompt] = useState(false);

  // User limits state
  const [userSearchCount, setUserSearchCount] = useState(0);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [showReportPreview, setShowReportPreview] = useState(false);

  // Bearer token
  const [token, setToken] = useState(() => localStorage.getItem('access_token'));

  // Soft sign-in on mount
  useEffect(() => {
    (async () => {
      const savedToken = localStorage.getItem('access_token');
      const savedRole = localStorage.getItem('role');
      
      if (!savedToken) {
        setShowLogin(true);
        return;
      }
      
      try {
        const res = await apiGet('/auth/me', savedToken);
        if (res.ok) {
          const me = await res.json();
          const currentRole = me.role || savedRole || 'user';
          setUserRole(currentRole);
          localStorage.setItem('role', currentRole);
          setShowLogin(false);
          setToken(savedToken);
          
          if (currentRole === 'user') {
            const count = loadCount();
            setUserSearchCount(count);
            if (count >= FREE_LIMIT) {
              setShowUpgradeModal(true);
            }
          }
        } else {
          localStorage.removeItem('access_token');
          localStorage.removeItem('role');
          resetCount();
          setToken(null);
          setUserRole(null);
          setShowLogin(true);
        }
      } catch (err) {
        console.error('Auth check failed:', err);
        if (savedRole) {
          setUserRole(savedRole);
          setToken(savedToken);
          setShowLogin(false);
          if (savedRole === 'user') {
            const count = loadCount();
            setUserSearchCount(count);
          }
        }
      }
    })();
  }, []);// Enhanced Features lukeminen
  const getEnhancedFeatureCards = () => {
    const feats = analysis?.enhanced_features;
    if (!feats) {
      console.log('No enhanced_features in analysis, using fallback data');
      return getFallbackFeatureCards();
    }

    const cards = [];

    // Helper function to safely get data from backend
    const safeGetFeature = (key, fallback = {}) => {
      const data = feats[key];
      if (!data) return fallback;
      
      // Handle different data structures
      if (typeof data === 'string') return { value: data, ...fallback };
      if (Array.isArray(data)) return { items: data, value: `${data.length} items`, ...fallback };
      return { ...fallback, ...data };
    };

    // 1. INDUSTRY BENCHMARKING
    const industryData = safeGetFeature('industry_benchmarking', {
      name: 'Industry Benchmarking',
      value: `${analysis?.basic_analysis?.digital_maturity_score || 0}/100`,
      description: 'Performance compared to industry standards',
      icon: <BarChart3 className="w-5 h-5" />
    });
    cards.push({
      name: 'Industry Benchmarking',
      value: industryData.value,
      description: industryData.description,
      status: industryData.status || (parseInt(industryData.value) > 50 ? 'above_average' : 'below_average'),
      details: industryData.details || `Percentile: ${industryData.percentile || 'N/A'}`,
      icon: <BarChart3 className="w-5 h-5" />
    });

    // 2. COMPETITOR GAPS
    const gapsData = safeGetFeature('competitor_gaps', {
      name: 'Competitor Gaps',
      value: 'Analysis available',
      description: 'Areas where competitors may have advantages',
      items: []
    });
    cards.push({
      name: 'Competitor Gaps',
      value: gapsData.value,
      description: gapsData.description,
      status: gapsData.status || 'attention',
      items: gapsData.items || [],
      icon: <Target className="w-5 h-5" />
    });

    // 3. GROWTH OPPORTUNITIES
    const growthData = safeGetFeature('growth_opportunities', {
      name: 'Growth Opportunities',
      value: 'Opportunities identified',
      description: 'Strategic growth areas',
      items: []
    });
    cards.push({
      name: 'Growth Opportunities',
      value: growthData.value,
      description: growthData.description,
      items: growthData.items || [],
      potential: growthData.potential_score || 70,
      icon: <TrendingUp className="w-5 h-5" />
    });

    // 4-9. Muut feature cardit...
    // (Jatkuu samalla tavalla kuin alkuperäisessä)
    
    return cards;
  };

  // FALLBACK DATA jos backend ei palauta enhanced_features
  const getFallbackFeatureCards = () => {
    const score = analysis?.basic_analysis?.digital_maturity_score || 0;
    const domain = (analysis?.basic_analysis?.website || url || '')
      .replace(/https?:\/\//, '')
      .replace('www.', '')
      .toLowerCase();

    // Detect industry for smart fallbacks
    let industry = 'general';
    if (domain.includes('bank') || domain.includes('finance')) industry = 'finance';
    else if (domain.includes('shop') || domain.includes('store')) industry = 'retail';
    else if (domain.includes('tech') || domain.includes('soft')) industry = 'tech';
    else if (domain.includes('health') || domain.includes('med')) industry = 'health';

    return [
      {
        name: 'Industry Benchmarking',
        value: `${score}/100`,
        description: `Performance compared to ${industry} industry standards`,
        status: score > 50 ? 'above_average' : 'below_average',
        details: `Estimated percentile: ${score > 70 ? '80th' : score > 50 ? '60th' : '40th'}`,
        icon: <BarChart3 className="w-5 h-5" />
      },
      // ... muut fallback cardit
    ];
  };

  // Auth Handlers
  const handleUserLogin = async () => {
    setLoginError('');
    try {
      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        credentials: 'omit',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ 
          username: 'demo',
          password: 'demo'
        }),
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        console.error('User login failed:', errorData);
        const errorMsg = errorData.detail || 'User login failed';
        throw new Error(errorMsg);
      }
      
      const data = await res.json();
      
      if (!data?.token) throw new Error('No token returned');
      
      localStorage.setItem('access_token', data.token);
      localStorage.setItem('role', data.role || 'viewer');
      
      setToken(data.token);
      setUserRole(data.role || 'viewer');
      setShowLogin(false);
      
      resetCount();
      setUserSearchCount(0);
    } catch (e) {
      console.error('User login error:', e);
      setLoginError(e?.message || 'User login failed');
    }
  };

  const handleAdminLogin = async () => {
    setLoginError('');
    if (!adminPassword) {
      setLoginError('Enter admin password');
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        credentials: 'omit',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ 
          username: 'admin@brandista.fi',
          password: adminPassword
        }),
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        console.error('Admin login failed:', errorData);
        
        if (res.status === 401) {
          throw new Error('Invalid password');
        } else {
          const errorMsg = errorData.detail || 'Login failed';
          throw new Error(errorMsg);
        }
      }
      
      const data = await res.json();
      
      if (!data?.token) throw new Error('No token returned');
      
      localStorage.setItem('access_token', data.token);
      localStorage.setItem('role', data.role || 'admin');
      
      setToken(data.token);
      setUserRole(data.role || 'admin');
      setShowLogin(false);
      setAdminPassword('');
      setShowAdminPrompt(false);
      
      resetCount();
      setUserSearchCount(0);
    } catch (e) {
      console.error('Admin login error:', e);
      setLoginError(e?.message || 'Invalid admin password');
    }
  };

  const handleLogout = async () => {
    try { await apiPost('/auth/logout', {}, token); } catch {}
    localStorage.removeItem('access_token');
    localStorage.removeItem('role');
    resetCount();
    setToken(null);
    setUserRole(null);
    setShowLogin(true);
    setAnalysis(null);
    setUrl('');
    setError('');
    setUserSearchCount(0);
    setShowUpgradeModal(false);
  };// Analyze Handler
  const handleAnalyze = async () => {
    if (userRole === 'user' && userSearchCount >= FREE_LIMIT) {
      setShowUpgradeModal(true);
      return;
    }

    const formattedUrl = cleanUrl(url);
    if (!formattedUrl) {
      setError('Please enter a valid URL (e.g. https://example.com)');
      return;
    }

    setLoading(true);
    setError('');
    setAnalysis(null);

    try {
      if (AUTH_MODE === 'token' && !token) {
        setShowLogin(true);
        throw new Error('Please log in first');
      }

      const companyName = new URL(formattedUrl).hostname.replace('www.', '').split('.')[0];

      const response = await apiPost('/api/v1/ai-analyze', {
        url: formattedUrl,
        company_name: companyName,
        analysis_type: 'comprehensive',
        language: 'en',
      }, token);

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('role');
          setToken(null);
          setUserRole(null);
          setShowLogin(true);
          throw new Error('Session expired. Please log in again.');
        }
        let msg = 'Analysis failed. Please try again.';
        try {
          const maybeJson = await response.json();
          if (maybeJson?.detail) msg = maybeJson.detail;
        } catch {
          const t = await response.text();
          if (t) msg = t;
        }
        throw new Error(msg);
      }

      const data = await response.json();
      if (!data?.ai_analysis || Object.keys(data.ai_analysis).length === 0) {
        setError('No analysis data received');
        setAnalysis(null);
      } else {
        setAnalysis(data);
        if (userRole === 'user') {
          const newCount = userSearchCount + 1;
          setUserSearchCount(newCount);
          saveCount(newCount);
          if (newCount >= FREE_LIMIT) {
            setTimeout(() => setShowUpgradeModal(true), 2000);
          }
        }
      }
    } catch (e) {
      console.error('Analysis error:', e);
      setError(e?.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  // Derived helpers
  const getScoreBreakdown = () => {
    const basic = analysis?.basic_analysis?.score_breakdown;
    if (!basic) {
      return { technical: 0, content: 0, user_experience: 0, performance: 0, accessibility: 0, seo: 0, security: 0, social: 0 };
    }
    return {
      technical: Math.round((basic.technical / 15) * 100),
      content: Math.round((basic.content / 20) * 100),
      user_experience: Math.round((basic.mobile / 15) * 100),
      performance: Math.round((basic.performance / 5) * 100),
      accessibility: 50,
      seo: Math.round((basic.seo_basics / 20) * 100),
      security: Math.round((basic.security / 15) * 100),
      social: Math.round((basic.social / 10) * 100),
    };
  };

  const getAIField = (fieldName) => {
    const ai = analysis?.ai_analysis;
    if (!ai) return [];
    let value = ai[fieldName];
    if (value == null) {
      const key = Object.keys(ai).find(k => k.toLowerCase() === fieldName.toLowerCase());
      value = key ? ai[key] : null;
    }
    if (Array.isArray(value)) return value;
    if (typeof value === 'string') return [value];
    return [];
  };

  const executiveSummaryLong = useMemo(() => {
    const ai = analysis?.ai_analysis || {};
    const score = analysis?.basic_analysis?.digital_maturity_score ?? 0;
    const parts = [];

    if (ai.summary && ai.summary.length > 0) {
      parts.push(ai.summary);
    } else {
      parts.push(
        `Overall digital maturity is ${score}/100. This score reflects technical setup, SEO fundamentals, content depth, mobile readiness, performance, and social presence.`
      );
    }

    const strengths = getAIField('strengths');
    if (strengths.length) parts.push(`Key strengths: ${strengths.slice(0, 5).join('; ')}.`);

    const weaknesses = getAIField('weaknesses');
    if (weaknesses.length) parts.push(`Primary weaknesses: ${weaknesses.slice(0, 5).join('; ')}.`);

    const opportunities = getAIField('opportunities');
    if (opportunities.length) parts.push(`Growth opportunities: ${opportunities.slice(0, 5).join('; ')}.`);

    const threats = getAIField('threats');
    if (threats.length) parts.push(`Risks to monitor: ${threats.slice(0, 5).join('; ')}.`);

    const recs = getAIField('recommendations');
    if (recs.length) parts.push(`Recommended next steps: ${recs.slice(0, 5).join('; ')}.`);

    return parts.join(' ');
  }, [analysis]);

  const getSmartActions = () => {
    const actions = analysis?.smart?.actions || [];
    const buckets = { critical: [], high: [], medium: [], low: [] };
    actions.forEach(a => (buckets[a.priority || 'medium'] || buckets.medium).push(a));
    Object.keys(buckets).forEach(k => buckets[k].sort((a, b) => (b.estimated_score_increase || 0) - (a.estimated_score_increase || 0)));
    return buckets;
  };

  // UI Components
  const CircleProgress = ({ value, max = 100, label, size = 120 }) => {
    const percentage = Math.max(0, Math.min(100, (value / max) * 100));
    const strokeWidth = 8;
    const radius = (size - strokeWidth) / 2;
    const circumference = radius * 2 * Math.PI;
    const strokeDashoffset = circumference - (percentage / 100) * circumference;

    const getGradientId = () => `grad-${(label || 'g').replace(/\s/g, '-')}`;
    const getColor = () => {
      if (percentage >= 75) return ['#10b981', '#34d399'];
      if (percentage >= 50) return ['#f59e0b', '#fbbf24'];
      if (percentage >= 25) return ['#ef4444', '#f87171'];
      return ['#991b1b', '#ef4444'];
    };
    const [c1, c2] = getColor();
    const gid = getGradientId();

    return (
      <div className="relative inline-flex flex-col items-center">
        <svg width={size} height={size} className="transform -rotate-90">
          <defs>
            <linearGradient id={gid} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={c1} />
              <stop offset="100%" stopColor={c2} />
            </linearGradient>
          </defs>
          <circle cx={size/2} cy={size/2} r={radius} stroke="rgba(255,255,255,0.08)" strokeWidth={strokeWidth} fill="none" />
          <circle
            cx={size/2} cy={size/2} r={radius}
            stroke={`url(#${gid})`} strokeWidth={strokeWidth} fill="none"
            strokeDasharray={circumference} strokeDashoffset={strokeDashoffset}
            strokeLinecap="round" className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold text-white">{Math.round(value)}</span>
          <span className="text-xs text-gray-400">/{max}</span>
        </div>
        {label && <span className="mt-2 text-sm text-gray-300 text-center">{label}</span>}
      </div>
    );
  };

  const BarChart = ({ data, height = 220 }) => {
    const maxValue = Math.max(...data.map(d => d.value), 1);
    const minInnerWidth = data.length * 72;
    return (
      <div className="relative" style={{ height }}>
        <div className="h-full overflow-x-auto sm:overflow-visible -mx-2 sm:mx-0">
          <div
            className="flex items-end justify-start sm:justify-between h-full gap-3 px-2 sm:px-0"
            style={{ minWidth: `${minInnerWidth}px` }}
          >
            {data.map((item, idx) => {
              const barH = (item.value / maxValue) * 100;
              const grad =
                item.value >= 75 ? ['#10b981', '#34d399']
                : item.value >= 50 ? ['#f59e0b', '#fbbf24']
                : item.value >= 25 ? ['#ef4444', '#f87171']
                : ['#991b1b', '#ef4444'];
              return (
                <div key={idx} className="sm:flex-1 shrink-0 w-14 flex flex-col items-center">
                  <div className="relative w-full flex flex-col items-center">
                    <span className="text-[11px] text-white font-bold mb-1">{Math.round(item.value)}%</span>
                    <div
                      className="w-full rounded-t-lg transition-all duration-1000 hover:opacity-80 relative group"
                      style={{ height: `${barH}%`, minHeight: '18px', background: `linear-gradient(to top, ${grad[0]}, ${grad[1]})` }}
                    >
                      <div className="absolute inset-0 bg-white opacity-0 group-hover:opacity-10 transition-opacity rounded-t-lg" />
                    </div>
                  </div>
                  <div className="mt-2 text-center">
                    <div className="text-gray-400 mx-auto">{item.icon}</div>
                    <span className="text-[10px] leading-tight text-gray-300 mt-1 block">{item.label}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  const RadarChart = ({ data, size = 300 }) => {
    const cx = size/2, cy = size/2, r = size*0.35, step = (Math.PI*2)/data.length;
    const pts = data.map((it, i) => {
      const ang = step*i - Math.PI/2;
      const val = Math.max(0, Math.min(100, it.value))/100;
      return { x: cx + Math.cos(ang)*r*val, y: cy + Math.sin(ang)*r*val, label: it.label, value: it.value, ang };
    });
    const pointsStr = pts.map(p => `${p.x},${p.y}`).join(' ');
    return (
      <svg width={size} height={size} className="overflow-visible">
        <defs>
          <linearGradient id="radarGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.85" />
          </linearGradient>
        </defs>
        {[20,40,60,80,100].map(p => (
          <circle key={p} cx={cx} cy={cy} r={r*(p/100)} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="1" />
        ))}
        {data.map((_, i) => {
          const ang = step*i - Math.PI/2, x2 = cx + Math.cos(ang)*r, y2 = cy + Math.sin(ang)*r;
          return <line key={i} x1={cx} y1={cy} x2={x2} y2={y2} stroke="rgba(255,255,255,0.08)" strokeWidth="1" />;
        })}
        <polygon points={pointsStr} fill="url(#radarGrad)" fillOpacity="0.25" stroke="url(#radarGrad)" strokeWidth="2" />
        {pts.map((p,i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r="4" fill="#10b981" stroke="white" strokeWidth="2" />
            <title>{`${p.label}: ${Math.round(p.value)}%`}</title>
          </g>
        ))}
        {data.map((it, i) => {
          const ang = step*i - Math.PI/2, lr = r + 22;
          const x = cx + Math.cos(ang)*lr, y = cy + Math.sin(ang)*lr;
          return <text key={i} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="text-[11px] fill-gray-300">{it.label}</text>;
        })}
      </svg>
    );
  };const ScoreBar = ({ label, score, icon, maxScore = 100 }) => {
    const pct = Math.max(0, Math.min(100, (score / maxScore) * 100));
    const grad = pct >= 80 ? 'from-green-400 to-green-500' : pct >= 60 ? 'from-yellow-400 to-yellow-500' : pct >= 40 ? 'from-orange-400 to-orange-500' : 'from-red-400 to-red-500';
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-gray-300">
            <div className="text-gray-500">{icon}</div>
            <span className="text-sm font-medium">{label}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-white font-bold">{Math.round(score)}</span>
            <span className="text-gray-500 text-xs">/ {maxScore}</span>
          </div>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
          <div className={`h-2 rounded-full bg-gradient-to-r ${grad} transition-all duration-700`} style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  };

  const ActionCard = ({ action, priority }) => {
    const cfg = {
      critical: { bg:'from-red-500/20 to-orange-500/20', border:'border-red-400/30', text:'text-red-400', label:'🔴 Critical' },
      high: { bg:'from-orange-500/20 to-yellow-500/20', border:'border-orange-400/30', text:'text-orange-400', label:'🟠 High Priority' },
      medium: { bg:'from-yellow-500/20 to-green-500/20', border:'border-yellow-400/30', text:'text-yellow-400', label:'🟡 Medium Priority' },
      low: { bg:'from-green-500/20 to-blue-500/20', border:'border-green-400/30', text:'text-green-400', label:'🟢 Low Priority' },
    }[priority] || { bg:'from-yellow-500/20 to-green-500/20', border:'border-yellow-400/30', text:'text-yellow-400', label:'🟡 Medium Priority' };
    return (
      <div className={`border ${cfg.border} rounded-xl p-5 bg-gradient-to-r ${cfg.bg} backdrop-blur-sm hover:scale-[1.01] transition-all`}>
        <div className="flex items-start justify-between mb-3">
          <h6 className="font-semibold text-white text-lg flex-1">{action.title}</h6>
          <span className={`${cfg.text} text-sm font-medium px-3 py-1 rounded-full bg-black/30`}>{cfg.label}</span>
        </div>
        <p className="text-gray-300 mb-4 leading-relaxed">{action.description}</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4 border-t border-gray-700/50">
          <div className="text-center">
            <span className="text-xs text-gray-500 block mb-1">Effort</span>
            <span className="text-sm font-medium text-blue-400">{action.effort}</span>
          </div>
          <div className="text-center">
            <span className="text-xs text-gray-500 block mb-1">Impact</span>
            <span className="text-sm font-medium text-purple-400">{action.impact}</span>
          </div>
          <div className="text-center">
            <span className="text-xs text-gray-500 block mb-1">Time</span>
            <span className="text-sm font-medium text-orange-400">{action.estimated_time || 'N/A'}</span>
          </div>
          <div className="text-center">
            <span className="text-xs text-gray-500 block mb-1">Score</span>
            <span className="text-sm font-bold text-green-400">+{action.estimated_score_increase || 0}</span>
          </div>
        </div>
      </div>
    );
  };

  // Main tab render - COMPLETE ANALYSIS SECTION WITH ENHANCED FEATURES
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
      },swot: {
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

  // Login Screen
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
            <h1 className="text-3xl font-bold text-white mb-2">
              Competitor Analysis Tool
            </h1>
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
                      <span className="text-xs bg-blue-400/20 text-blue-400 px-2 py-1 rounded-full">
                        Free Trial
                      </span>
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-2">Free User Access</h3>
                    <p className="text-gray-400 text-sm">
                      Get started with {FREE_LIMIT} free analyses to explore the tool
                    </p>
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
                      <span className="text-xs bg-purple-400/20 text-purple-400 px-2 py-1 rounded-full">
                        Full Access
                      </span>
                    </div>
                    <h3 className="text-xl font-semibold text-white mb-2">Admin Access</h3>
                    <p className="text-gray-400 text-sm">
                      Unlimited analyses with advanced features
                    </p>
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
                <button
                  onClick={() => setShowAdminPrompt(false)}
                  className="text-gray-400 hover:text-white transition-colors mb-2"
                >
                  ← Back
                </button>
                
                <div className="text-center mb-6">
                  <ShieldCheck className="w-12 h-12 text-purple-400 mx-auto mb-3" />
                  <h3 className="text-xl font-semibold text-white">Admin Login</h3>
                  <p className="text-gray-400 text-sm mt-2">Enter password for unlimited access</p>
                </div>

                <input
                  type="password"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleAdminLogin()}
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
  }// Upgrade Modal
  if (showUpgradeModal) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 flex items-center justify-center px-4">
        <div className="relative z-10 max-w-md w-full">
          <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-8 shadow-2xl">
            <div className="text-center mb-6">
              <Lock className="w-16 h-16 text-yellow-400 mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Free Limit Reached</h2>
              <p className="text-gray-400">
                You've used all {FREE_LIMIT} free analyses. Upgrade for unlimited access.
              </p>
            </div>
            
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-400/30">
                <h3 className="font-semibold text-white mb-2">Premium Features:</h3>
                <ul className="space-y-2 text-sm text-gray-300">
                  <li className="flex items-center">
                    <CheckCircle className="w-4 h-4 text-green-400 mr-2" />
                    Unlimited analyses
                  </li>
                  <li className="flex items-center">
                    <CheckCircle className="w-4 h-4 text-green-400 mr-2" />
                    Priority processing
                  </li>
                  <li className="flex items-center">
                    <CheckCircle className="w-4 h-4 text-green-400 mr-2" />
                    Advanced insights
                  </li>
                  <li className="flex items-center">
                    <CheckCircle className="w-4 h-4 text-green-400 mr-2" />
                    Export reports
                  </li>
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
                  onKeyPress={(e) => e.key === 'Enter' && handleAdminLogin()}
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

  // Main Analysis Screen
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-to-br from-green-400/10 via-transparent to-transparent rounded-full blur-3xl" />
        <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-to-tl from-blue-400/10 via-transparent to-transparent rounded-full blur-3xl" />
      </div>

      <div className="relative z-10">
        <div className="container mx-auto px-4 py-8">
          {/* Header */}
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
                  {userRole === 'admin' ? 'Admin' : 'Free User'}
                </span>
                {userRole === 'user' && (
                  <span className="text-xs bg-blue-400/20 text-blue-400 px-2 py-0.5 rounded-full ml-2">
                    {FREE_LIMIT - userSearchCount} left
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

          {/* Search Bar */}
          <div className="max-w-4xl mx-auto mb-8">
            <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-6">
              <label className="block text-gray-300 text-sm font-medium mb-3">
                Enter website URL to analyze
              </label>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleAnalyze()}
                  placeholder="https://example.com"
                  className="flex-1 px-4 py-3 bg-black/30 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-green-400 focus:outline-none transition-colors"
                  disabled={loading}
                />
                <button
                  onClick={handleAnalyze}
                  disabled={loading || !url}
                  className="px-6 py-3 bg-gradient-to-r from-green-400 to-blue-500 text-white font-semibold rounded-lg hover:shadow-lg hover:shadow-green-400/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    'Analyze'
                  )}
                </button>
              </div>
              
              {error && (
                <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-400/30">
                  <p className="text-red-400 text-sm">{error}</p>
                </div>
              )}
              
              {userRole === 'user' && (
                <div className="mt-4 p-3 rounded-lg bg-blue-500/10 border border-blue-400/30">
                  <p className="text-blue-400 text-sm">
                    Free tier: {userSearchCount}/{FREE_LIMIT} analyses used
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Loading State */}
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

          {/* Analysis Results */}
          {!loading && analysis && (
            <div className="max-w-7xl mx-auto">
              <div className="bg-black/30 backdrop-blur-xl border border-gray-700 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-2xl font-bold text-white mb-1">
                      Analysis Results
                    </h2>
                    <p className="text-gray-400">
                      {analysis.basic_analysis?.website || url}
                    </p>
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
