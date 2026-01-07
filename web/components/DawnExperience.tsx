'use client';

import { useCallback, useMemo, useState } from 'react';
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
import type { AgentRunSummary, FeedRecord, IndexExcelResponse, PreviewTable } from '@/lib/types';

type ViewMode = 'welcome' | 'workspace';

export default function DawnExperience() {
  type TileConfig = {
    title: string;
    span: string;
    render: () => JSX.Element;
    priority?: number;
  };

  const [viewMode, setViewMode] = useState<ViewMode>('welcome');
  const [source, setSource] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewTable | null>(null);
  const [profile, setProfile] = useState<IndexExcelResponse | null>(null);
  const [activeFeed, setActiveFeed] = useState<FeedRecord | null>(null);
  const [agentResult, setAgentResult] = useState<AgentRunSummary | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);

  // Auto-transition to workspace when data is indexed
  const autoTransitionToWorkspace = useCallback(() => {
    if (profile && viewMode === 'welcome') {
      setViewMode('workspace');
    }
  }, [profile, viewMode]);

  const completedStages: WorkflowStage[] = useMemo(() => {
    const stages: WorkflowStage[] = [];
    if (preview) stages.push('upload', 'preview');
    if (profile) stages.push('index');
    if (agentResult) stages.push('agents');
    return stages;
  }, [preview, profile, agentResult]);

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

  const [collapsedTiles, setCollapsedTiles] = useState<Record<string, boolean>>({});

  // Simplified tile order for cleaner UI
  const [tileOrder, setTileOrder] = useState<string[]>(() => [
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
  ]);

  const tiles = useMemo<Record<string, TileConfig>>(
    () => ({
      upload: {
        title: 'Upload',
        span: 'col-span-1 sm:col-span-2 xl:col-span-6',
        priority: 1,
        render: () => (
          <UploadPanel
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
        span: 'col-span-1 sm:col-span-2 xl:col-span-5',
        render: () => <WorkspaceOverviewPanel preview={preview} summary={profile} activeFeed={activeFeed} />
      },
      preview: {
        title: 'Preview',
        span: 'col-span-1 sm:col-span-2 xl:col-span-7',
        render: () => <PreviewPanel preview={preview} />
      },
      agent: {
        title: 'Agent swarm',
        span: 'col-span-1 sm:col-span-2 xl:col-span-5',
        render: () => <AgentPanel activeFeedId={activeFeed?.identifier} onRun={(res) => setAgentResult(res)} />
      },
      contextChat: {
        title: 'Context chat',
        span: 'col-span-1 sm:col-span-2 xl:col-span-5',
        render: () => <ContextChatPanel disabled={!profile} />
      },
      agentOrbit: {
        title: 'Swarm telemetry',
        span: 'col-span-1 sm:col-span-2 xl:col-span-5',
        render: () => <AgentOrbitPanel result={agentResult} />
      },
      charts: {
        title: 'Charts',
        span: 'col-span-1 sm:col-span-2 xl:col-span-6',
        render: () => <ChartsPanel summary={profile?.summary} />
      },
      insight: {
        title: 'Insights',
        span: 'col-span-1 sm:col-span-2 xl:col-span-6',
        render: () => <InsightPanel summary={profile?.summary} />
      },
      feedIngest: {
        title: 'Feed ingest',
        span: 'col-span-1 sm:col-span-2 xl:col-span-6',
        render: () => <FeedIngestPanel />
      },
      actionPlan: {
        title: 'Action plan',
        span: 'col-span-1 sm:col-span-2 xl:col-span-6',
        render: () => <ActionPlanPanel feed={activeFeed} summary={profile} />
      },
      contextNotes: {
        title: 'Context notes',
        span: 'col-span-1 sm:col-span-2 xl:col-span-6',
        render: () => <ContextNotesPanel source={source} />
      },
      context: {
        title: 'Context sources',
        span: 'col-span-1 sm:col-span-2 xl:col-span-6',
        render: () => <ContextPanel selectedSource={source} onSourceChange={setSource} />
      },
      feedGallery: {
        title: 'Feeds',
        span: 'col-span-1 sm:col-span-2 xl:col-span-7',
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
        span: 'col-span-1 sm:col-span-2 xl:col-span-5',
        render: () => <JobsPanel />
      }
    }),
    [activeFeed, agentResult, preview, profile, source]
  );

  const toggleTile = (id: string) =>
    setCollapsedTiles((prev) => ({
      ...prev,
      [id]: !prev[id]
    }));

  const moveTile = (id: string, delta: number) =>
    setTileOrder((prev) => {
      const next = [...prev];
      const index = next.indexOf(id);
      if (index === -1) return prev;
      const targetIndex = Math.min(next.length - 1, Math.max(0, index + delta));
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      return next;
    });

  return (
    <div className="space-y-8">
      {/* Dashboard Header */}
      <DashboardHeader
        preview={preview}
        profile={profile}
        agentResult={agentResult}
      />

      {/* Main workspace */}
      <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
        <DawnSidebar />
        <div className="min-w-0 flex-1">
          {/* Activity feed sidebar */}
          <div className="mb-6">
            <ActivityFeed activities={activities} maxItems={5} />
          </div>

          {/* Tiles grid */}
          <div className="grid auto-rows-[minmax(160px,_auto)] grid-flow-row-dense grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-12">
            {tileOrder.map((tileId) => {
              const tile = tiles[tileId as keyof typeof tiles];
              if (!tile) return null;
              const collapsed = !!collapsedTiles[tileId];
              return (
                <div key={tileId} className={`relative ${tile.span} transition-all`}>
                  {collapsed ? (
                    <div className="flex h-full min-h-[120px] items-center justify-between rounded-3xl border border-dashed border-white/15 bg-white/5 px-5 py-4 hover:bg-white/10 transition-colors">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.35em] text-slate-500">Collapsed</p>
                        <p className="text-sm font-semibold text-white mt-1">{tile.title}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => toggleTile(tileId)}
                        className="rounded-full border border-white/10 bg-black/40 px-3 py-1 text-xs text-amber-200 hover:border-white/30"
                      >
                        Expand
                      </button>
                    </div>
                  ) : (
                    <>
                      {tile.render()}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
