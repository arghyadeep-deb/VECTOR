/* ============================================================================
   VECTOR · data.js
   DEMO SEED DATA for the offline/dev page only. backend.js clears every seeded
   dataset the moment a backend connects, so none of this is ever shown as live.
   Seed data for the demo / offline mode. Mirrors the backend data models so a
   live backend can replace any of these via the VECTOR adapter (see core.js).
   Owner: Arghyadeep Deb · KIIT CSE 2023-27
   ========================================================================== */
(function (global) {
  'use strict';

  const OWNER = 'Arghyadeep Deb';

  // ---- 33 districts (from spec §11) -------------------------------------
  const DISTRICTS = [
    'governance','security','coding','time_calendar','communications','memory_curator',
    'research','intelligence','skills','languages','interview_prep','learning','finance',
    'health','reflection','startups','investment','content','agency','karpathy_lab',
    'projects','relationships','privacy','pattern_detective','news_trends','calls','ops',
    'data_analytics','personal_growth','documentation','qa','chief_of_staff','marketing'
  ];

  // ---- HP → model tiers (spec §10) --------------------------------------
  function tierFor(hp){
    // Tier names only: which model an agent really uses comes from the backend (agent.model).
    if (hp >= 800) return { tier:'ELITE',    model:'' };
    if (hp >= 700) return { tier:'STRONG',   model:'' };
    if (hp >= 500) return { tier:'HEALTHY',  model:'' };
    if (hp >= 300) return { tier:'WEAK',     model:'' };
    if (hp >  0)   return { tier:'CRITICAL', model:'' };
    return { tier:'GHOST', model:'' };
  }

  const AGENT_NAMES = {
    governance:['Chairman','Arbiter'], security:['ThreatScout','MalwareHunter','NodeGuard'],
    coding:['GitBot','CodeReviewer','BugHunter','ArchitectBot'],
    research:['ArxivMiner','RedditScout','NewsAggregator'],
    finance:['UPIParser','BudgetAnalyst','TaxWatch'],
    health:['SleepTracker','FatigueMonitor'], reflection:['NightReviewer'],
    karpathy_lab:['MLTracker'], projects:['DeadlineWatcher','ProjectPlanner'],
    interview_prep:['MockInterviewer'], investment:['StockAnalyst'],
    intelligence:['PatternDetective','AnomalyHunter'], news_trends:['MarketTrendsBot'],
    chief_of_staff:['NoiseFilter'], ops:['SREMonitor']
  };

  function buildAgents(){
    const out = [];
    let i = 0;
    const seedHP = [932,861,804,788,742,710,690,655,612,588,540,512,498,455,420,388,355,312,295,260,210,140,0];
    for (const d of DISTRICTS){
      const names = AGENT_NAMES[d] || [d.split('_').map(s=>s[0].toUpperCase()+s.slice(1)).join('') + 'Bot'];
      for (const n of names){
        const hp = seedHP[i % seedHP.length];
        const t = tierFor(hp);
        out.push({
          id: 'agt_'+(i+1), name: n, district: d,
          health_points: hp, generation: 1 + (i % 4),
          tier: t.tier, model: t.model,
          last_active: ['12s','44s','2m','5m','11m','38m','1h'][i % 7]
        });
        i++;
      }
    }
    return out;
  }

  const GOALS = {
    LONG: [
      { id:'g1', title:'Ship VECTOR Phase 1', progress:0.62, priority:10, tags:['vector','build'] },
      { id:'g2', title:'DSA / placement prep', progress:0.41, priority:9, tags:['career','dsa'] }
    ],
    MID: [
      { id:'g3', title:'Karpathy ML playlist', progress:0.55, priority:8, tags:['ml','learning'] },
      { id:'g4', title:'KIIT attendance ≥ 75%', progress:0.78, priority:7, tags:['kiit','academic'] }
    ],
    SHORT: [
      { id:'g5', title:'Daily git commit', progress:0.90, priority:6, tags:['habit'] },
      { id:'g6', title:'Reply to pending DMs', progress:0.33, priority:4, tags:['comms'] }
    ]
  };

  const COUNCIL = [
    { id:'cs_03', question:'Auto-merge depend<br>bot PRs over weekend?', stakes:'high',
      recommendation:'defer', confidence:0.71, when:'2h ago',
      votes:[['claude-sonnet-4.6','against'],['kimi-k2.6','for'],['qwen3:14b','against']] },
    { id:'cs_02', question:'Increase daily token<br>budget to ₹180?', stakes:'low',
      recommendation:'proceed', confidence:0.88, when:'yesterday',
      votes:[['claude-sonnet-4.6','for'],['kimi-k2.6','for'],['qwen3:14b','for']] },
    { id:'cs_01', question:'Allow PC keystroke<br>automation in IDE?', stakes:'critical',
      recommendation:'reject', confidence:0.94, when:'2d ago',
      votes:[['claude-sonnet-4.6','against'],['kimi-k2.6','against'],['qwen3:14b','for']] }
  ];

  const APPROVALS = [
    { action_id:'act_7741', action_type:'pc.launch_app', params:'code .', level:'YELLOW', proposed_by:'GitBot', expires:26 },
    { action_id:'act_7742', action_type:'pc.type', params:'git push origin main', level:'RED', proposed_by:'GitBot', expires:18 }
  ];

  const MEMORY = [
    { event_type:'DECISION_MADE', importance:'high',   content:'Routed "scan startup HN feed" → startups district', when:'34s' },
    { event_type:'AGENT_HP_CHANGED', importance:'normal', content:'CodeReviewer +50 (task done: review PR #218)', when:'2m' },
    { event_type:'ANOMALY_DETECTED', importance:'critical', content:'Unusual outbound traffic on :11434 — flagged', when:'9m' },
    { event_type:'HYPOTHESIS_SURFACED', importance:'normal', content:'User most productive 22:00-01:00 (conf 0.82)', when:'21m' },
    { event_type:'TASK_ROUTED', importance:'normal', content:'KIIT attendance check scheduled → 08:30', when:'1h' }
  ];

  const STOCKS = [
    ['NIFTY 50','24,318.40',+0.62],['SENSEX','79,943.21',+0.55],['RELIANCE','2,914.10',-0.34],
    ['TCS','3,880.55',+1.12],['INFY','1,642.30',+0.41],['HDFCBANK','1,701.95',-0.18],
    ['NVDA','1,154.20',+2.31],['AAPL','214.86',+0.28],['BTC-USD','67,420',-1.04],['ETH-USD','3,512',-0.77]
  ];

  const NEWS = [
    'IRGC vows to pass Iranian currency through Strait of Hormuz amid foreign-minister visit',
    'NVIDIA unveils next-gen inference stack — 2.4× throughput on local models',
    'India UPI crosses 18B monthly transactions for first time',
    'Open-weight model release matches frontier reasoning at 1/8 the cost',
    'KIIT announces revised end-sem schedule for CSE 2023 batch'
  ];

  const TRACKS = [
    { title:'Still Into You', artist:'Paramore', dur:216, pos:124, art:'#d9456b' },
    { title:'Back In Black',  artist:'AC/DC',    dur:255, pos:0,   art:'#222' },
    { title:'Thunderstruck',  artist:'AC/DC',    dur:292, pos:0,   art:'#3a2f1a' }
  ];

  // Map: lat/lng "pins" rendered on the abstract dark map — localized to the
  // owner's actual base (KIIT, Bhubaneswar, Odisha) instead of generic demo geo
  const MAP = {
    label:'BHUBANESWAR · ODISHA, IN',
    center:[20.296,85.824], zoom:10,
    pins:[
      { name:'KIIT Campus', x:0.50, y:0.30, kind:'home' },
      { name:'Bhubaneswar', x:0.48, y:0.52, kind:'node' },
      { name:'Cuttack',     x:0.58, y:0.22, kind:'node' },
      { name:'Khordha',     x:0.30, y:0.66, kind:'node' },
      { name:'Puri',        x:0.40, y:0.86, kind:'node' },
      { name:'Konark',      x:0.68, y:0.80, kind:'alert' }
    ]
  };

  global.VECTOR_DATA = {
    OWNER, DISTRICTS, tierFor, agents: buildAgents(),
    GOALS, COUNCIL, APPROVALS, MEMORY, STOCKS, NEWS, TRACKS, MAP
  };
})(window);
