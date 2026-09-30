import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import './App.css'

const navigation = [
  { label: 'Overview', path: '/' },
  { label: 'Repositories', path: '/repositories' },
  { label: 'Analysis', path: '/analysis' },
  { label: 'Code', path: '/code' },
  { label: 'Ask CodeLens', path: '/ask' },
  { label: 'History', path: '/history' },
  { label: 'Settings', path: '/settings' },
]

const stats = [
  { label: 'Files', value: '412' },
  { label: 'Symbols', value: '1,284' },
  { label: 'Modules', value: '36' },
  { label: 'Findings', value: '14' },
]

const repositories = [
  {
    name: 'payment-service',
    branch: 'main',
    commit: 'abc1234',
    health: 'Stable',
    summary: 'Core billing and settlement flows for the payments platform.',
  },
  {
    name: 'auth-gateway',
    branch: 'feature/session-ttl',
    commit: '90fca77',
    health: 'Needs review',
    summary: 'Token validation, session enforcement, and request auth middleware.',
  },
  {
    name: 'ops-traces',
    branch: 'main',
    commit: '512ef8c',
    health: 'Monitoring',
    summary: 'Telemetry, alerts, and operational event processing for service health.',
  },
]

const findings = [
  { type: 'high_complexity', severity: 'medium', file: 'billing/settlement.py', line: 81 },
  { type: 'duplicate_logic', severity: 'low', file: 'auth/session.py', line: 143 },
  { type: 'dependency_risk', severity: 'high', file: 'checkout/checkout.py', line: 66 },
]

const files = [
  'billing/settlement.py',
  'billing/retry_policy.py',
  'auth/middleware.py',
  'checkout/controller.py',
  'observability/metrics.py',
]

const history = [
  { title: 'Repository indexed', detail: 'payment-service • 2 hours ago' },
  { title: 'Security scan completed', detail: '3 medium findings found' },
  { title: 'Complexity regression', detail: 'billing/settlement.py increased by 12%' },
]

const settings = [
  'Authentication required',
  'Auto refresh analysis jobs',
  'Hide low-confidence findings',
  'Enable evidence citations',
]

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand-block">
            <div className="brand-mark">C</div>
            <div>
              <div className="brand-name">CodeLens</div>
              <div className="brand-subtitle">Engineering signal</div>
            </div>
          </div>

          <nav className="nav" aria-label="Main navigation">
            {navigation.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'nav-item-active' : ''}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="sidebar-footer">
            <div className="mini-label">Workspace</div>
            <div className="workspace-name">codelens-platform</div>
          </div>
        </aside>

        <main className="main-panel">
          <header className="topbar">
            <div className="search-box">
              <span className="search-icon">⌕</span>
              <input type="text" value="Search codebase..." readOnly aria-label="Search codebase" />
            </div>
            <div className="topbar-actions">
              <button type="button" className="ghost-button">Notifications</button>
              <div className="user-pill">SA</div>
            </div>
          </header>

          <div className="content-area">
            <Routes>
              <Route path="/" element={<OverviewScreen />} />
              <Route path="/repositories" element={<RepositoriesScreen />} />
              <Route path="/analysis" element={<AnalysisScreen />} />
              <Route path="/code" element={<CodeScreen />} />
              <Route path="/ask" element={<AskScreen />} />
              <Route path="/history" element={<HistoryScreen />} />
              <Route path="/settings" element={<SettingsScreen />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}

function OverviewScreen() {
  return (
    <>
      <section className="page-header">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>payment-service</h1>
        </div>
        <div className="repo-meta">
          <span>main • abc1234</span>
        </div>
      </section>

      <div className="stat-grid">
        {stats.map((stat) => (
          <div key={stat.label} className="stat-card">
            <div className="stat-value">{stat.value}</div>
            <div className="stat-label">{stat.label}</div>
          </div>
        ))}
      </div>

      <div className="panel-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Repository summary</h2>
            <span className="badge success">Healthy</span>
          </div>
          <ul className="key-list">
            <li><span>Repository</span><strong>payment-service</strong></li>
            <li><span>Branch</span><strong>main</strong></li>
            <li><span>Languages</span><strong>Python, SQL</strong></li>
            <li><span>Recent analysis</span><strong>Today at 09:42</strong></li>
          </ul>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Initialization status</h2>
            <span className="badge info">Running</span>
          </div>
          <ul className="progress-list">
            <li className="done">Repository acquired</li>
            <li className="done">Files discovered</li>
            <li className="done">Languages detected</li>
            <li className="active">Parsing source files</li>
            <li>Building dependency model</li>
            <li>Running analysis</li>
          </ul>
        </section>
      </div>
    </>
  )
}

function RepositoriesScreen() {
  return (
    <>
      <section className="page-header">
        <div>
          <p className="eyebrow">Repositories</p>
          <h1>Connected sources</h1>
        </div>
        <button type="button" className="primary-button">Add repository</button>
      </section>

      <div className="list-stack">
        {repositories.map((repo) => (
          <article key={repo.name} className="repo-row panel">
            <div>
              <div className="repo-name">{repo.name}</div>
              <div className="repo-summary">{repo.summary}</div>
            </div>
            <div className="repo-meta-inline">
              <span>{repo.branch}</span>
              <span>{repo.commit}</span>
              <span className="badge muted">{repo.health}</span>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}

function AnalysisScreen() {
  return (
    <>
      <section className="page-header">
        <div>
          <p className="eyebrow">Analysis</p>
          <h1>Engineering findings</h1>
        </div>
      </section>

      <div className="panel">
        <table className="data-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Severity</th>
              <th>File</th>
              <th>Line</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((finding) => (
              <tr key={`${finding.file}-${finding.line}`}>
                <td>{finding.type}</td>
                <td><span className={`severity ${finding.severity}`}>{finding.severity}</span></td>
                <td>{finding.file}</td>
                <td>{finding.line}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function CodeScreen() {
  return (
    <>
      <section className="page-header">
        <div>
          <p className="eyebrow">Code</p>
          <h1>Codebase map</h1>
        </div>
      </section>

      <div className="code-grid">
        <aside className="panel file-panel">
          <h3>Files</h3>
          <ul className="file-list">
            {files.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
        </aside>

        <section className="panel code-panel">
          <div className="code-preview-header">
            <span className="badge muted">billing/settlement.py</span>
            <span className="badge info">Python</span>
          </div>
          <pre className="code-block">
{`def reconcile_settlement(batch):
    for item in batch.items:
        if item.status == "pending":
            attempt_retry(item)

    return summarize(batch)
`}
          </pre>
        </section>
      </div>
    </>
  )
}

function AskScreen() {
  return (
    <>
      <section className="page-header">
        <div>
          <p className="eyebrow">Ask CodeLens</p>
          <h1>Investigate the codebase</h1>
        </div>
      </section>

      <div className="panel ask-panel">
        <div className="ask-box">
          <span className="search-icon">⌕</span>
          <input type="text" value="Where is the payment retry logic handled?" readOnly aria-label="Ask CodeLens query" />
        </div>

        <div className="answer-block">
          <h3>Answer</h3>
          <p>
            Payment retry logic is implemented in the settlement pipeline, with retry behavior
            concentrated in the billing service and supported by the checkout request flow.
          </p>
          <div className="evidence-list">
            <div><strong>Evidence 1:</strong> billing/settlement.py • reconcile_settlement()</div>
            <div><strong>Evidence 2:</strong> billing/retry_policy.py • RetryPolicy.evaluate()</div>
          </div>
        </div>
      </div>
    </>
  )
}

function HistoryScreen() {
  return (
    <>
      <section className="page-header">
        <div>
          <p className="eyebrow">History</p>
          <h1>Recent events</h1>
        </div>
      </section>

      <div className="list-stack">
        {history.map((event) => (
          <article key={event.title} className="panel history-item">
            <div className="history-title">{event.title}</div>
            <div className="history-detail">{event.detail}</div>
          </article>
        ))}
      </div>
    </>
  )
}

function SettingsScreen() {
  return (
    <>
      <section className="page-header">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Workspace configuration</h1>
        </div>
      </section>

      <div className="panel settings-list">
        {settings.map((setting) => (
          <label key={setting} className="setting-row">
            <span>{setting}</span>
            <input type="checkbox" defaultChecked />
          </label>
        ))}
      </div>
    </>
  )
}

export default App
