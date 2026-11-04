import { Component, useEffect, useMemo, useState, type ErrorInfo, type ReactNode } from 'react';
import { AlertBanner, AppShell, Pictogram, SideNav, Skeleton, TopBar } from '@permit-engine/ui';
import { Banner } from './components/Banner';
import { PositionLabel, ReplayButtons, ReplayTrack } from './components/ReplayControls';
import { loadDemo } from './data';
import { Replay, ReplayContext, buildTimeline, type ReplayContextValue } from './replay';
import type { DemoData } from './types';
import { AboutView } from './views/AboutView';
import { CaseView } from './views/CaseView';
import { LearningView } from './views/LearningView';
import { ProblemsView } from './views/ProblemsView';
import { ReplayView } from './views/ReplayView';
import { RulesView } from './views/RulesView';
import { RulingsView } from './views/RulingsView';

type Route =
  | { view: 'replay' | 'rulings' | 'problems' | 'learning' | 'rules' | 'about' }
  | { view: 'case'; id: string };

function parseHash(hash: string, previous: Route): Route {
  const h = hash.replace(/^#/, '');
  if (!h || h === '/') return { view: 'replay' };
  // The shell's skip link uses a plain fragment. It is not a route.
  if (!h.startsWith('/')) return previous;
  const parts = h.split('?')[0].split('/').filter(Boolean);
  if (parts[0] === 'case' && parts[1]) return { view: 'case', id: decodeURIComponent(parts[1]) };
  if (parts[0] === 'rulings' || parts[0] === 'problems' || parts[0] === 'learning' || parts[0] === 'rules' || parts[0] === 'about') return { view: parts[0] };
  return { view: 'replay' };
}

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash, { view: 'replay' }));
  useEffect(() => {
    const onChange = () => {
      setRoute((prev) => {
        const next = parseHash(window.location.hash, prev);
        if (next !== prev) window.scrollTo(0, 0);
        return next;
      });
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

function readOptions() {
  const fromHash = window.location.hash.includes('?') ? window.location.hash.split('?')[1] : '';
  const params = new URLSearchParams(window.location.search || fromHash);
  const speed = Number(params.get('speed'));
  return {
    video: params.get('video') === '1',
    speed: Number.isFinite(speed) && speed > 0 ? Math.min(64, Math.max(0.25, speed)) : 1,
  };
}

class ViewBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) {
    return { error: e.message };
  }
  componentDidCatch(e: Error, info: ErrorInfo) {
    console.error(e, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return <AlertBanner tone="danger" title="This view could not be drawn from the export">{this.state.error}</AlertBanner>;
    }
    return this.props.children;
  }
}

function RouteView({ route }: { route: Route }) {
  switch (route.view) {
    case 'case': return <CaseView key={route.id} id={route.id} />;
    case 'rulings': return <RulingsView />;
    case 'problems': return <ProblemsView />;
    case 'learning': return <LearningView />;
    case 'rules': return <RulesView />;
    case 'about': return <AboutView />;
    default: return <ReplayView />;
  }
}

const NAV_SECTIONS = [
  {
    id: 'watch',
    items: [
      { id: 'replay', label: 'Replay', icon: 'home' as const, href: '#/' },
      { id: 'rulings', label: 'Officer rulings', icon: 'scale' as const, href: '#/rulings' },
      { id: 'problems', label: 'Problem cases', icon: 'alert' as const, href: '#/problems' },
      { id: 'learning', label: 'Learning', icon: 'layers' as const, href: '#/learning' },
    ],
  },
  {
    id: 'read',
    title: 'Read',
    items: [
      { id: 'rules', label: 'Rules', icon: 'book' as const, href: '#/rules' },
      { id: 'about', label: 'About this demo', icon: 'info' as const, href: '#/about' },
    ],
  },
];

function Frame({ route, value }: { route: Route; value: ReplayContextValue }) {
  const current = route.view === 'case' ? 'replay' : route.view;
  const keyForBoundary = route.view === 'case' ? `case-${route.id}` : route.view;
  if (value.video) {
    return (
      <div className="d-videoframe">
        <header className="d-videohead">
          <span className="d-videohead__name">Permit Engine</span>
          <PositionLabel />
        </header>
        <ReplayTrack readOnly />
        <main className="d-videomain">
          <ViewBoundary key={keyForBoundary}><RouteView route={route} /></ViewBoundary>
        </main>
        <Banner />
      </div>
    );
  }
  return (
    <>
      <AppShell
        sidebar={(
          <SideNav
            brand={{ name: 'Permit Engine', subtitle: 'Street race permits', mark: <Pictogram name="rules-engine" size={32} />, href: '#/' }}
            sections={NAV_SECTIONS}
            current={current}
            footer={<span>Replayed in your browser from a finished run. Nothing runs on a server.</span>}
          />
        )}
        topbar={(
          <div className="d-topwrap">
            <TopBar start={<PositionLabel />} actions={<ReplayButtons />} showThemeToggle={false} />
            <ReplayTrack />
          </div>
        )}
      >
        <ViewBoundary key={keyForBoundary}><RouteView route={route} /></ViewBoundary>
      </AppShell>
      <Banner />
    </>
  );
}

export function App() {
  const [data, setData] = useState<DemoData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const route = useRoute();

  useEffect(() => {
    loadDemo().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  const value = useMemo<ReplayContextValue | null>(() => {
    if (!data) return null;
    const options = readOptions();
    const timeline = buildTimeline(data);
    return { data, timeline, replay: new Replay(timeline, options), video: options.video };
  }, [data]);

  useEffect(() => {
    value?.replay.start();
    return () => value?.replay.stop();
  }, [value]);

  return (
    <div className={`pe-app d-app${value?.video ? ' d-app--video' : ''}`}>
      {error && (
        <div className="d-loading">
          <AlertBanner tone="danger" title="The replay could not load">Check that the data folder sits next to this page. {error}</AlertBanner>
        </div>
      )}
      {!error && !value && (
        <div className="d-loading"><Skeleton variant="text" lines={6} label="Loading the replay" /></div>
      )}
      {value && (
        <ReplayContext.Provider value={value}>
          <Frame route={route} value={value} />
        </ReplayContext.Provider>
      )}
    </div>
  );
}
