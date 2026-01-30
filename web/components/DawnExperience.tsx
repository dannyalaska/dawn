'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import DawnSidebar from '@/components/layout/DawnSidebar';
import DashboardHeader from '@/components/layout/DashboardHeader';
import UploadPanel from '@/components/panels/UploadPanel';
import PreviewPanel from '@/components/panels/PreviewPanel';
import InsightPanel from '@/components/panels/InsightPanel';
import ContextPanel from '@/components/panels/ContextPanel';
import FeedGallery from '@/components/panels/FeedGallery';
import ContextChatPanel from '@/components/panels/ContextChatPanel';
import AgentOrbitPanel from '@/components/panels/AgentOrbitPanel';
import ContextNotesPanel from '@/components/panels/ContextNotesPanel';
import AgentPanel from '@/components/panels/AgentPanel';
import JobsPanel from '@/components/panels/JobsPanel';
import FeedIngestPanel from '@/components/panels/FeedIngestPanel';
import ActionPlanPanel from '@/components/panels/ActionPlanPanel';
import ChartsPanel from '@/components/panels/ChartsPanel';
import WorkspaceOverviewPanel from '@/components/panels/WorkspaceOverviewPanel';
import ActivityFeed, { type ActivityItem } from '@/components/ui/ActivityFeed';
import { DemoModeOverlay } from '@/components/ui/DemoMode';
import { useDemoMode } from '@/hooks/useDemoMode';
import type { AgentRunSummary, FeedRecord, IndexExcelResponse, PreviewTable } from '@/lib/types';

export default function DawnExperience() {
  type TileConfig = {
    title: string;
    description: string;
    preview: string;
    kicker: string;
    accent: string;
    render: () => JSX.Element;
    priority?: number;
  };

  const [source, setSource] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewTable | null>(null);
  const [profile, setProfile] = useState<IndexExcelResponse | null>(null);
  const [activeFeed, setActiveFeed] = useState<FeedRecord | null>(null);
  const [lastUploadFile, setLastUploadFile] = useState<File | null>(null);
  const [agentResult, setAgentResult] = useState<AgentRunSummary | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [expandedTileId, setExpandedTileId] = useState<string | null>(null);
  const [expandAll, setExpandAll] = useState(false);
  const [layoutMode, setLayoutMode] = useState<'wide' | 'tall'>('wide');
  const demoMode = useDemoMode();

  useEffect(() => {
    const updateLayout = () => {
      const width = window.innerWidth || 0;
      const height = window.innerHeight || 0;
      const ratio = height ? width / height : 1;
      const isWide = ratio >= 1.02 && width >= 900;
      setLayoutMode(isWide ? 'wide' : 'tall');
    };
    updateLayout();
    window.addEventListener('resize', updateLayout);
    return () => window.removeEventListener('resize', updateLayout);
  }, []);

  useEffect(() => {
    const handleReset = () => {
      setSource(null);
      setPreview(null);
      setProfile(null);
      setActiveFeed(null);
      setLastUploadFile(null);
      setAgentResult(null);
      setActivities([]);
    };
    window.addEventListener('workspace:reset', handleReset);
    return () => window.removeEventListener('workspace:reset', handleReset);
  }, []);

  useEffect(() => {
    const handleFocusTile = (event: Event) => {
      const customEvent = event as CustomEvent;
      const tileId = customEvent.detail?.tileId ?? null;
      if (!tileId) {
        setExpandedTileId(null);
        return;
      }
      setExpandAll(false);
      setExpandedTileId(tileId);
    };

    window.addEventListener('demo:focus-tile', handleFocusTile);
    return () => window.removeEventListener('demo:focus-tile', handleFocusTile);
  }, []);

  useEffect(() => {
    if (!expandedTileId || expandAll) return;
    const tile = document.querySelector(`[data-demo-target='${expandedTileId}']`);
    if (!(tile instanceof HTMLElement)) return;
    const rafId = requestAnimationFrame(() => {
      tile.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    const timeoutId = window.setTimeout(() => {
      tile.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 350);
    return () => {
      cancelAnimationFrame(rafId);
      window.clearTimeout(timeoutId);
    };
  }, [expandedTileId, expandAll]);

  // Activity logging
  const addActivity = useCallback((type: ActivityItem['type'], message: string, detail?: string) => {
    const newActivity: ActivityItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      type,
      message,
      detail,
      timestamp: new Date()
    };
    setActivities((prev) => [newActivity, ...prev.slice(0, 49)]);
  }, []);

  useEffect(() => {
    const handleDemoUpload = (event: Event) => {
      const customEvent = event as CustomEvent;
      const fileName = customEvent.detail?.file?.name ?? 'demo workbook';
      addActivity('upload', 'Demo upload started', fileName);
    };
    const handleDemoPreview = () => {
      addActivity('profile', 'Preview generated', 'Columns + rows scanned');
    };
    const handleDemoIndex = () => {
      addActivity('index', 'Indexing complete', 'Insights ready');
    };
    const handleDemoChat = (event: Event) => {
      const customEvent = event as CustomEvent;
      const question = customEvent.detail?.question ?? 'Demo question';
      addActivity('chat', 'Asked a data question', question);
    };
    const handleDemoAgent = () => {
      addActivity('agent', 'Agent swarm launched', 'Summarizing anomalies');
    };

    window.addEventListener('demo:upload-file', handleDemoUpload);
    window.addEventListener('demo:preview-file', handleDemoPreview);
    window.addEventListener('demo:index-file', handleDemoIndex);
    window.addEventListener('demo:chat-question', handleDemoChat);
    window.addEventListener('demo:agent-trigger', handleDemoAgent);

    return () => {
      window.removeEventListener('demo:upload-file', handleDemoUpload);
      window.removeEventListener('demo:preview-file', handleDemoPreview);
      window.removeEventListener('demo:index-file', handleDemoIndex);
      window.removeEventListener('demo:chat-question', handleDemoChat);
      window.removeEventListener('demo:agent-trigger', handleDemoAgent);
    };
  }, [addActivity]);

  // Simplified tile order for cleaner UI
  const tileOrder = useMemo(
    () => [
      'upload',
      'contextChat',
      'agent',
      'preview',
      'charts',
      'agentOrbit',
      'insight',
      'feedGallery',
      'context',
      'contextNotes',
      'workspace',
      'actionPlan',
      'feedIngest',
      'jobs'
    ],
    []
  );

  const tiles = useMemo<Record<string, TileConfig>>(
    () => ({
      upload: {
        title: 'Upload',
        kicker: 'Ingest',
        description: 'Drop in a workbook and start instantly.',
        preview: 'Preview your data and build context in seconds.',
        accent: 'from-amber-400/20 via-amber-300/10 to-pink-400/20',
        priority: 1,
        render: () => (
          <UploadPanel
            onFileSelected={setLastUploadFile}
            onPreviewed={(data) => {
              setPreview(data);
              if (data) {
                addActivity('profile', `Previewed ${data.name}`, `${data.shape[0]} rows × ${data.shape[1]} columns`);
              }
            }}
            onProfiled={(sourceKey, summary) => {
              if (sourceKey) setSource(sourceKey);
              setProfile(summary);
              if (summary) {
                addActivity('index', `Indexed ${summary.source}`, `${summary.indexed_chunks} context chunks created`);
              }
            }}
          />
        )
      },
      workspace: {
        title: 'Workspace overview',
        kicker: 'Overview',
        description: 'Track the latest context and feed changes.',
        preview: 'Stay on top of indexing, feeds, and activity.',
        accent: 'from-slate-400/20 via-slate-300/10 to-sky-400/20',
        render: () => <WorkspaceOverviewPanel preview={preview} summary={profile} activeFeed={activeFeed} />
      },
      preview: {
        title: 'Preview',
        kicker: 'Preview',
        description: 'Inspect rows, columns, and schema.',
        preview: 'Scan the sample rows and column details.',
        accent: 'from-sky-400/20 via-cyan-300/10 to-emerald-300/20',
        render: () => <PreviewPanel preview={preview} />
      },
      agent: {
        title: 'Agent swarm',
        kicker: 'Agents',
        description: 'Run multi-agent analysis and reports.',
        preview: 'Launch an agent swarm for deeper insights.',
        accent: 'from-pink-500/20 via-rose-400/10 to-amber-300/20',
        render: () => (
          <AgentPanel
            activeFeedId={activeFeed?.identifier}
            uploadFile={lastUploadFile}
            uploadSheet={preview?.sheet ?? profile?.sheet ?? null}
            onFeedReady={(feed) => setActiveFeed(feed)}
            onRun={(res) => setAgentResult(res)}
          />
        )
      },
      contextChat: {
        title: 'Context chat',
        kicker: 'RAG',
        description: 'Ask questions and get cited answers.',
        preview: 'Chat with your data using retrieval.',
        accent: 'from-emerald-400/20 via-lime-300/10 to-amber-300/20',
        render: () => (
          <ContextChatPanel
            disabled={!source && !activeFeed}
            source={source ?? null}
            activeFeedId={activeFeed?.identifier ?? null}
            memory={
              preview?.sha16 && (preview?.sheet || profile?.sheet)
                ? { sha16: preview.sha16, sheet: (preview.sheet ?? profile?.sheet) as string }
                : profile?.sha16 && profile?.sheet
                  ? { sha16: profile.sha16, sheet: profile.sheet }
                  : null
            }
          />
        )
      },
      agentOrbit: {
        title: 'Swarm telemetry',
        kicker: 'Telemetry',
        description: 'Watch agents collaborate live.',
        preview: 'Follow the swarm plan and outputs.',
        accent: 'from-slate-400/20 via-amber-300/10 to-orange-300/20',
        render: () => <AgentOrbitPanel result={agentResult} />
      },
      charts: {
        title: 'Charts',
        kicker: 'Charts',
        description: 'Instant visual summaries.',
        preview: 'Explore key distributions and metrics.',
        accent: 'from-indigo-400/20 via-sky-300/10 to-emerald-300/20',
        render: () => <ChartsPanel summary={profile?.summary} />
      },
      insight: {
        title: 'Insights',
        kicker: 'Insights',
        description: 'Top trends and metrics.',
        preview: 'Surface the most important signals.',
        accent: 'from-amber-300/20 via-pink-300/10 to-sky-300/20',
        render: () => <InsightPanel summary={profile?.summary} />
      },
      feedIngest: {
        title: 'Feed ingest',
        kicker: 'Feeds',
        description: 'Register feeds for ongoing analysis.',
        preview: 'Connect datasets for continuous updates.',
        accent: 'from-emerald-300/20 via-teal-300/10 to-sky-300/20',
        render: () => (
          <FeedIngestPanel
            defaultFile={lastUploadFile}
            defaultSheet={preview?.sheet ?? profile?.sheet ?? null}
            sheetOptions={preview?.sheet_names ?? []}
            onFeedReady={(feed) => setActiveFeed(feed)}
          />
        )
      },
      actionPlan: {
        title: 'Action plan',
        kicker: 'Plan',
        description: 'Auto-prioritized next steps.',
        preview: 'Let agents suggest what to do next.',
        accent: 'from-rose-400/20 via-amber-300/10 to-lime-300/20',
        render: () => <ActionPlanPanel feed={activeFeed} summary={profile} />
      },
      contextNotes: {
        title: 'Context notes',
        kicker: 'Notes',
        description: 'Edit context to guide the model.',
        preview: 'Add notes and definitions to improve answers.',
        accent: 'from-slate-400/20 via-sky-300/10 to-emerald-300/20',
        render: () => <ContextNotesPanel source={source} />
      },
      context: {
        title: 'Context sources',
        kicker: 'Sources',
        description: 'Pick the source for retrieval.',
        preview: 'Choose which dataset powers the answers.',
        accent: 'from-sky-400/20 via-emerald-300/10 to-amber-300/20',
        render: () => <ContextPanel selectedSource={source} onSourceChange={setSource} />
      },
      feedGallery: {
        title: 'Feeds',
        kicker: 'Library',
        description: 'Browse available datasets.',
        preview: 'Open feeds and jump between sources.',
        accent: 'from-amber-300/20 via-slate-300/10 to-sky-300/20',
        render: () => (
          <FeedGallery
            onSelectSource={setSource}
            onSelectFeed={({ feed, source: src }) => {
              setActiveFeed(feed);
              if (src) setSource(src);
            }}
            activeSource={source}
            activeFeedId={activeFeed?.identifier ?? null}
          />
        )
      },
      jobs: {
        title: 'Jobs',
        kicker: 'Jobs',
        description: 'Monitor background tasks.',
        preview: 'Track scheduling and run status.',
        accent: 'from-slate-400/20 via-slate-300/10 to-emerald-300/20',
        render: () => <JobsPanel />
      }
    }),
    [activeFeed, agentResult, preview, profile, source]
  );

  const toggleTile = (tileId: string) => {
    if (expandAll) return;
    if (demoMode.isActive) {
      demoMode.stopDemo();
    }
    setExpandedTileId((prev) => (prev === tileId ? null : tileId));
  };

  const gridCols =
    expandAll
      ? 'grid-cols-1'
      : layoutMode === 'wide'
        ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
        : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2';

  const renderTile = (tileId: string, tile: TileConfig, expanded: boolean) => {
    const canToggle = !expandAll;
    const canExpand = canToggle && !expanded;
    const canCollapse = canToggle && expanded;

    return (
      <div key={tileId} className={`group relative ${expanded ? 'col-span-full' : ''}`} data-demo-target={tileId}>
        <div
          role={canExpand ? 'button' : undefined}
          tabIndex={canExpand ? 0 : -1}
          aria-expanded={expanded}
          onClick={canExpand ? () => toggleTile(tileId) : undefined}
          onKeyDown={(event) => {
            if (!canExpand) return;
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              toggleTile(tileId);
            }
          }}
          className={`relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 shadow-lg transition-all duration-300 ${
            expanded ? 'p-6' : 'cursor-pointer p-5 hover:-translate-y-1 hover:border-amber-300/40'
          }`}
        >
          <div className={`absolute inset-0 bg-gradient-to-br ${tile.accent} opacity-0 transition-opacity group-hover:opacity-100`} />
          <div className="relative">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.35em] text-slate-400">{tile.kicker}</p>
                <h3 className="mt-2 text-lg font-semibold text-white">{tile.title}</h3>
                <p className="mt-2 text-sm text-slate-300">{tile.preview}</p>
              </div>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                toggleTile(tileId);
              }}
              disabled={expandAll}
              className="rounded-full border border-white/10 bg-black/40 px-3 py-1 text-[10px] uppercase tracking-[0.3em] text-amber-200 hover:border-white/30 disabled:opacity-50"
              aria-label={`${expanded ? 'Collapse' : 'Expand'} ${tile.title}`}
              title={expandAll ? 'Expanded' : expanded ? 'Collapse' : 'Expand'}
            >
              {expandAll ? 'Expanded' : expanded ? 'Collapse' : 'Expand'}
            </button>
          </div>
            <div className={`mt-4 space-y-2 transition-opacity ${expanded ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
              <p className="text-sm text-slate-200">{tile.description}</p>
              <div className="space-y-2">
                <div className="h-2 w-4/5 rounded-full bg-white/20" />
                <div className="h-2 w-2/3 rounded-full bg-white/10" />
                <div className="h-2 w-1/2 rounded-full bg-white/5" />
              </div>
            </div>
            {expanded && (
              <div className="mt-6" data-tile-expanded={tileId}>
                {tile.render()}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const workspaceLayout = layoutMode === 'wide' ? 'flex-row items-start' : 'flex-col';

  return (
    <div className="space-y-8">
      <DemoModeOverlay
        isVisible={demoMode.isActive}
        currentStep={demoMode.currentStep}
        totalSteps={demoMode.totalSteps}
        step={demoMode.currentStepData}
        onClose={demoMode.stopDemo}
      />
      {/* Dashboard Header */}
      <DashboardHeader
        preview={preview}
        profile={profile}
        agentResult={agentResult}
      />

      {/* Main workspace */}
      <div className={`flex gap-8 ${workspaceLayout}`}>
        <DawnSidebar />
        <div className="min-w-0 flex-1">
          {/* Activity feed sidebar */}
          <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
            <ActivityFeed activities={activities} maxItems={5} />
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setExpandAll((prev) => !prev);
                  setExpandedTileId(null);
                }}
                className="rounded-full border border-white/10 bg-black/40 px-4 py-2 text-xs uppercase tracking-[0.3em] text-amber-200 hover:border-white/30"
              >
                {expandAll ? 'Collapse all' : 'Expand all'}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (demoMode.isActive) {
                    demoMode.stopDemo();
                    return;
                  }
                  void demoMode.startDemo();
                }}
                className="rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-xs font-semibold text-slate-900 shadow-aurora hover:shadow-lg"
              >
                {demoMode.isActive ? 'Stop Demo' : 'Run Demo'}
              </button>
            </div>
          </div>

          {/* Expanded tile */}
          {!expandAll && expandedTileId && tiles[expandedTileId] && (
            <div className="mb-8">
              {renderTile(expandedTileId, tiles[expandedTileId], true)}
            </div>
          )}

          {/* Tiles grid */}
          <div className={`grid auto-rows-[minmax(180px,_auto)] gap-6 ${gridCols}`}>
            {tileOrder
              .filter((tileId) => expandAll || !expandedTileId || tileId !== expandedTileId)
              .map((tileId) => {
                const tile = tiles[tileId as keyof typeof tiles];
                if (!tile) return null;
                const expanded = expandAll;
                return renderTile(tileId, tile, expanded);
              })}
          </div>
        </div>
      </div>
    </div>
  );
}
