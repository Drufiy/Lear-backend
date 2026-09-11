import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import useNotifications, { AppNotification } from '../hooks/useNotifications';
import useWebSocket from '../hooks/useWebSocket';

export interface ServiceItem {
  connector_id: string;
  resource_id?: string;
  display_name?: string;
}

export interface Environment {
  name: string;
  services: ServiceItem[];
}

export interface Project {
  id: string;
  name: string;
  created_at?: string;
  environments: Environment[];
}

export interface ActiveWatch {
  watch_id: string;
  connector: string;
  target: string;
  status: 'healthy' | 'degraded' | 'error' | 'deploying';
  last_event?: string;
  last_timestamp?: string;
}

export type AggregateStatus = 'healthy' | 'degraded' | 'error';
export type WatcherState = 'IDLE' | 'STARTING' | 'ACTIVE' | 'DEGRADED' | 'ALERTING' | 'ERROR';

interface LearContextType {
  // Projects
  projects: Project[];
  activeProjectId: string;
  activeProject: Project | null;
  selectProject: (id: string) => void;
  refreshProjects: () => Promise<void>;

  // Environment
  activeEnvironment: string;
  selectEnvironment: (env: string) => void;
  environments: string[];

  // Navigation
  activeTab: string;
  setActiveTab: (tab: string) => void;
  openCreateProjectModal: boolean;
  setOpenCreateProjectModal: (open: boolean) => void;
  selectedProjectIdForDetail: string | null;
  viewProjectDetail: (id: string) => void;
  clearProjectDetail: () => void;

  // Global Copilot / Chatbot
  chatOpen: boolean;
  chatContext: { connectorId?: string; resourceId?: string } | null;
  openChat: (ctx?: { connectorId?: string; resourceId?: string } | null) => void;
  closeChat: () => void;

  // Active Services
  activeServices: ServiceItem[];

  // Connectors & Watches
  connectedCount: number;
  activeWatches: ActiveWatch[];
  watcherState: WatcherState;
  aggregateStatus: AggregateStatus;
  appVersion: string;
  startWatch: (connectorId: string, target: string) => Promise<boolean>;
  stopWatch: (connectorId: string, target?: string, watchId?: string) => Promise<boolean>;

  // Notifications
  unreadCount: number;
  toasts: AppNotification[];
  dismissToast: (id: string) => void;
}

const LearContext = createContext<LearContextType | undefined>(undefined);

const LOCAL_STORAGE_PROJECT_KEY = 'lear_active_project_id';
const LOCAL_STORAGE_ENV_KEY = 'lear_active_environment';

export const LearProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string>(() => {
    return localStorage.getItem(LOCAL_STORAGE_PROJECT_KEY) || 'default';
  });
  const [activeEnvironment, setActiveEnvironment] = useState<string>(() => {
    return localStorage.getItem(LOCAL_STORAGE_ENV_KEY) || 'Production';
  });
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [openCreateProjectModal, setOpenCreateProjectModal] = useState(false);
  const [selectedProjectIdForDetail, setSelectedProjectIdForDetail] = useState<string | null>(null);

  const [chatOpen, setChatOpen] = useState(false);
  const [chatContext, setChatContext] = useState<{ connectorId?: string; resourceId?: string } | null>(null);

  const viewProjectDetail = useCallback((id: string) => {
    setSelectedProjectIdForDetail(id);
    setActiveTab('projects');
  }, []);

  const clearProjectDetail = useCallback(() => {
    setSelectedProjectIdForDetail(null);
  }, []);

  const openChat = useCallback((ctx?: { connectorId?: string; resourceId?: string } | null) => {
    setChatContext(ctx || null);
    setChatOpen(true);
  }, []);

  const closeChat = useCallback(() => {
    setChatOpen(false);
    setChatContext(null);
  }, []);

  const [connectedCount, setConnectedCount] = useState<number>(0);
  const [activeWatches, setActiveWatches] = useState<ActiveWatch[]>([]);
  const [watcherState, setWatcherState] = useState<WatcherState>('IDLE');
  const [appVersion, setAppVersion] = useState<string>('2.0.0');

  const { toasts, unreadCount, dismissToast } = useNotifications();
  const { isConnected, lastEvent } = useWebSocket();

  // 1. Fetch system version & configured connectors count
  const fetchMetadata = useCallback(async () => {
    try {
      const resVer = await fetch('/api/system/version');
      if (resVer.ok) {
        const vData = await resVer.json();
        if (vData.version) setAppVersion(vData.version);
      }
    } catch {
      // Fallback to default version
    }

    try {
      const resConn = await fetch('/api/connectors');
      if (resConn.ok) {
        const cData = await resConn.json();
        const configured = (cData.connectors || []).filter((c: any) => c.configured);
        setConnectedCount(configured.length);
      }
    } catch (e) {
      console.error('Error fetching connectors metadata:', e);
    }
  }, []);

  // 2. Fetch Projects
  const refreshProjects = useCallback(async () => {
    try {
      const res = await fetch('/api/projects');
      if (res.ok) {
        const data = await res.json();
        const list: Project[] = data.projects || [];
        setProjects(list);
      }
    } catch (e) {
      console.error('Error fetching projects:', e);
    }
  }, []);

  // 3. Fetch Active Watches from backend
  const fetchActiveWatches = useCallback(async () => {
    try {
      const res = await fetch('/api/watch/active');
      if (res.ok) {
        const data = await res.json();
        const serverWatches: ActiveWatch[] = (data.watches || []).map((w: any) => ({
          watch_id: w.watch_id,
          connector: w.connector,
          target: w.target,
          status: (w.status || 'healthy') as ActiveWatch['status'],
        }));
        setActiveWatches(serverWatches);
        if (serverWatches.length > 0) {
          setWatcherState('ACTIVE');
        }
      }
    } catch (e) {
      console.error('Error fetching active watches:', e);
    }
  }, []);

  // Initial loads
  useEffect(() => {
    fetchMetadata();
    refreshProjects();
    fetchActiveWatches();
  }, [fetchMetadata, refreshProjects, fetchActiveWatches]);

  // Update watches on live incoming WebSocket events
  useEffect(() => {
    if (!lastEvent) return;

    const etype = (lastEvent.event_type || '').toLowerCase();
    const summary = (lastEvent.summary || '').toLowerCase();
    const isError = etype.includes('fail') || etype.includes('alarm') || summary.includes('error') || etype.includes('crash');
    const isWarn = etype.includes('spike') || etype.includes('warn') || summary.includes('degraded');

    const evSeverity: ActiveWatch['status'] = isError ? 'error' : isWarn ? 'degraded' : 'healthy';

    if (isError) {
      setWatcherState('ALERTING');
    } else if (isWarn) {
      setWatcherState('DEGRADED');
    } else if (activeWatches.length > 0) {
      setWatcherState('ACTIVE');
    }

    if (lastEvent.watch_id) {
      setActiveWatches(prev => {
        const exists = prev.find(w => w.watch_id === lastEvent.watch_id);
        if (exists) {
          return prev.map(w =>
            w.watch_id === lastEvent.watch_id
              ? { ...w, status: evSeverity, last_event: lastEvent.summary, last_timestamp: lastEvent.timestamp }
              : w
          );
        } else {
          return [
            ...prev,
            {
              watch_id: lastEvent.watch_id!,
              connector: lastEvent.connector || 'custom',
              target: lastEvent.watch_id!.split(':')[1] || lastEvent.watch_id!,
              status: evSeverity,
              last_event: lastEvent.summary,
              last_timestamp: lastEvent.timestamp,
            },
          ];
        }
      });
    }
  }, [lastEvent, activeWatches.length]);

  // Set watcherState based on socket connection
  useEffect(() => {
    if (!isConnected) {
      setWatcherState(prev => (prev === 'IDLE' ? 'IDLE' : 'ERROR'));
    } else if (activeWatches.length > 0 && watcherState === 'IDLE') {
      setWatcherState('ACTIVE');
    }
  }, [isConnected, activeWatches.length, watcherState]);

  // Compute Active Project (supports 'all' aggregate)
  const activeProject = useMemo<Project | null>(() => {
    if (projects.length === 0) return null;

    if (activeProjectId === 'all') {
      // Create unified aggregate project
      const envMap = new Map<string, ServiceItem[]>();
      projects.forEach(p => {
        (p.environments || []).forEach(env => {
          const current = envMap.get(env.name) || [];
          envMap.set(env.name, [...current, ...(env.services || [])]);
        });
      });

      const aggregatedEnvs: Environment[] = Array.from(envMap.entries()).map(([name, services]) => ({
        name,
        services,
      }));

      return {
        id: 'all',
        name: 'All Projects',
        environments: aggregatedEnvs.length > 0 ? aggregatedEnvs : [{ name: 'Production', services: [] }],
      };
    }

    return projects.find(p => p.id === activeProjectId) || projects[0];
  }, [projects, activeProjectId]);

  // Derive dynamic environments for the active project
  const environments = useMemo<string[]>(() => {
    if (!activeProject || !activeProject.environments || activeProject.environments.length === 0) {
      return ['Production'];
    }
    return activeProject.environments.map(e => e.name);
  }, [activeProject]);

  // Sync activeEnvironment if current is invalid for the active project
  useEffect(() => {
    if (environments.length > 0) {
      const match = environments.find(e => e.toLowerCase() === activeEnvironment.toLowerCase());
      if (!match) {
        setActiveEnvironment(environments[0]);
        localStorage.setItem(LOCAL_STORAGE_ENV_KEY, environments[0]);
      }
    }
  }, [environments, activeEnvironment]);

  // Project selection handler with persistence
  const selectProject = useCallback((id: string) => {
    setActiveProjectId(id);
    localStorage.setItem(LOCAL_STORAGE_PROJECT_KEY, id);
  }, []);

  // Environment selection handler with persistence
  const selectEnvironment = useCallback((env: string) => {
    setActiveEnvironment(env);
    localStorage.setItem(LOCAL_STORAGE_ENV_KEY, env);
  }, []);

  // Compute active services for the current project + environment
  const activeServices = useMemo<ServiceItem[]>(() => {
    if (!activeProject || !activeProject.environments) return [];
    const envObj = activeProject.environments.find(
      e => e.name.toLowerCase() === activeEnvironment.toLowerCase()
    );
    return envObj ? envObj.services || [] : [];
  }, [activeProject, activeEnvironment]);

  // Compute aggregate infrastructure status
  const aggregateStatus = useMemo<AggregateStatus>(() => {
    if (activeWatches.some(w => w.status === 'error')) return 'error';
    if (activeWatches.some(w => w.status === 'degraded')) return 'degraded';
    if (watcherState === 'ALERTING') return 'error';
    if (watcherState === 'DEGRADED') return 'degraded';
    return 'healthy';
  }, [activeWatches, watcherState]);

  // Start watching a resource
  const startWatch = useCallback(async (connectorId: string, target: string) => {
    try {
      const res = await fetch(`/api/connectors/${connectorId}/watch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
      });
      if (res.ok) {
        const data = await res.json();
        const wid = data.watch_id || `${connectorId}:${target}`;
        setActiveWatches(prev => [
          ...prev.filter(w => w.watch_id !== wid),
          { watch_id: wid, connector: connectorId, target, status: 'healthy' },
        ]);
        setWatcherState('ACTIVE');
        return true;
      }
    } catch (e) {
      console.error('Error starting watch:', e);
    }
    return false;
  }, []);

  // Stop watching a resource
  const stopWatch = useCallback(async (connectorId: string, target?: string, watchId?: string) => {
    const wid = watchId || (target ? `${connectorId}:${target}` : null);
    try {
      const params = new URLSearchParams();
      if (wid) params.append('watch_id', wid);
      else if (target) params.append('target', target);

      const res = await fetch(`/api/connectors/${connectorId}/watch?${params.toString()}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setActiveWatches(prev => prev.filter(w => w.watch_id !== wid));
        return true;
      }
    } catch (e) {
      console.error('Error stopping watch:', e);
    }
    return false;
  }, []);

  const value = useMemo(
    () => ({
      projects,
      activeProjectId,
      activeProject,
      selectProject,
      refreshProjects,
      activeEnvironment,
      selectEnvironment,
      environments,
      activeTab,
      setActiveTab,
      openCreateProjectModal,
      setOpenCreateProjectModal,
      selectedProjectIdForDetail,
      viewProjectDetail,
      clearProjectDetail,
      chatOpen,
      chatContext,
      openChat,
      closeChat,
      activeServices,
      connectedCount,
      activeWatches,
      watcherState,
      aggregateStatus,
      appVersion,
      startWatch,
      stopWatch,
      unreadCount,
      toasts,
      dismissToast,
    }),
    [
      projects,
      activeProjectId,
      activeProject,
      selectProject,
      refreshProjects,
      activeEnvironment,
      selectEnvironment,
      environments,
      activeTab,
      openCreateProjectModal,
      selectedProjectIdForDetail,
      viewProjectDetail,
      clearProjectDetail,
      chatOpen,
      chatContext,
      openChat,
      closeChat,
      activeServices,
      connectedCount,
      activeWatches,
      watcherState,
      aggregateStatus,
      appVersion,
      startWatch,
      stopWatch,
      unreadCount,
      toasts,
      dismissToast,
    ]
  );

  return <LearContext.Provider value={value}>{children}</LearContext.Provider>;
};

export const useLear = (): LearContextType => {
  const context = useContext(LearContext);
  if (!context) {
    throw new Error('useLear must be used within a LearProvider');
  }
  return context;
};

export default LearContext;
