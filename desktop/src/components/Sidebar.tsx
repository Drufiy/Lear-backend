import { useState, useRef, useEffect } from 'react';
import { Home, FolderGit2, Blocks, Bell, Settings, ChevronDown, Sparkles, Activity, Plus, Layers, Eye, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLear } from '../context/LearContext';

export interface SidebarProps {
  activeTab?: string;
  setActiveTab?: (tab: string) => void;
  activeProject?: any;
  projects?: any[];
  onSelectProject?: (proj: any) => void;
  activeEnvironment?: string;
  setActiveEnvironment?: (env: string) => void;
  watcherState?: string;
  services?: any[];
  unreadNotificationsCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = (props) => {
  const context = useLear();

  // Use props if explicitly passed, otherwise fallback to context
  const activeTab = props.activeTab ?? context.activeTab;
  const setActiveTab = props.setActiveTab ?? context.setActiveTab;
  const projects = props.projects ?? context.projects;
  const activeProject = props.activeProject ?? context.activeProject;
  const activeEnvironment = props.activeEnvironment ?? context.activeEnvironment;
  const setActiveEnvironment = props.setActiveEnvironment ?? context.selectEnvironment;
  const watcherState = props.watcherState ?? context.watcherState;
  const activeServices = props.services ?? context.activeServices;
  const unreadCount = props.unreadNotificationsCount ?? context.unreadCount;

  const [showProjectsDropdown, setShowProjectsDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowProjectsDropdown(false);
      }
    };
    if (showProjectsDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showProjectsDropdown]);

  const environments = context.environments.length > 0 ? context.environments : ['Production'];

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Home },
    { id: 'projects', label: 'Projects', icon: FolderGit2 },
    { id: 'integrations', label: 'Integrations', icon: Blocks },
    { id: 'activity', label: 'Activity Log', icon: Activity },
    { id: 'notifications', label: 'Notifications', icon: Bell, badge: unreadCount },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  const handleSelectProject = (projectId: string) => {
    if (props.onSelectProject) {
      if (projectId === 'all') {
        props.onSelectProject({ id: 'all', name: 'All Projects' });
      } else {
        const found = projects.find((p: any) => p.id === projectId);
        if (found) props.onSelectProject(found);
      }
    } else {
      context.selectProject(projectId);
    }
    setShowProjectsDropdown(false);
  };

  const handleNewProjectClick = () => {
    setShowProjectsDropdown(false);
    context.setOpenCreateProjectModal(true);
    setActiveTab('projects');
  };

  // Status dot color mapping
  const getStatusDot = (status: string) => {
    switch (status) {
      case 'error':
        return 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]';
      case 'degraded':
        return 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]';
      case 'deploying':
        return 'bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.6)]';
      case 'healthy':
      default:
        return 'bg-accent shadow-[0_0_8px_rgba(255,58,137,0.6)]';
    }
  };

  return (
    <aside className="w-64 bg-[#080B11] border-r border-border-subtle flex flex-col h-full select-none">
      {/* Brand Header */}
      <div className="p-5 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-accent to-pink-400 flex items-center justify-center shadow-[0_0_15px_rgba(255,58,137,0.3)]">
              <Sparkles size={18} className="text-gray-950" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <h1 className="text-lg font-bold tracking-tight text-white">Lear</h1>
                <span className="text-[10px] px-1.5 py-0.2 bg-accent/20 text-accent rounded font-mono font-semibold">
                  v{context.appVersion}
                </span>
                {/* Aggregate Status Dot */}
                <span
                  title={`Infrastructure Health: ${context.aggregateStatus.toUpperCase()}`}
                  className={`w-2 h-2 rounded-full animate-pulse transition-colors ${getStatusDot(context.aggregateStatus)}`}
                />
              </div>
              <p className="text-[10px] text-gray-500 font-mono">Infrastructure Intelligence</p>
            </div>
          </div>

          {/* Connection Count Badge */}
          {context.connectedCount > 0 && (
            <div
              title={`${context.connectedCount} configured backend connectors`}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface border border-border-subtle text-[10px] font-mono text-gray-400"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-ping" />
              <span>{context.connectedCount}</span>
            </div>
          )}
        </div>

        {/* Project Selector (B1, B4, B5, B6) */}
        <div className="mt-5 relative" ref={dropdownRef}>
          <button
            onClick={() => setShowProjectsDropdown(prev => !prev)}
            className="w-full p-2.5 rounded-xl bg-surface/60 hover:bg-surface border border-border-subtle flex items-center justify-between text-xs text-left cursor-pointer transition-colors"
          >
            <div className="flex items-center gap-2 truncate">
              {context.activeProjectId === 'all' ? (
                <Layers size={13} className="text-accent shrink-0" />
              ) : (
                <FolderGit2 size={13} className="text-gray-400 shrink-0" />
              )}
              <span className="text-gray-200 font-medium truncate">
                {activeProject?.name || 'Default Project'}
              </span>
            </div>
            <ChevronDown
              size={14}
              className={`text-gray-500 shrink-0 transition-transform duration-200 ${
                showProjectsDropdown ? 'rotate-180 text-accent' : ''
              }`}
            />
          </button>

          <AnimatePresence>
            {showProjectsDropdown && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.15 }}
                className="absolute top-full left-0 right-0 mt-1 p-1 bg-surface-elevated border border-border-hover rounded-xl shadow-2xl z-30 space-y-0.5 backdrop-blur-xl"
              >
                {/* B4: "All Projects" Option */}
                <button
                  onClick={() => handleSelectProject('all')}
                  className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors cursor-pointer flex items-center gap-2 ${
                    context.activeProjectId === 'all'
                      ? 'bg-accent/15 text-accent font-semibold'
                      : 'text-gray-300 hover:bg-surface'
                  }`}
                >
                  <Layers size={13} />
                  <span>All Projects</span>
                </button>

                <div className="border-t border-border-subtle my-1" />

                {/* Real Projects List */}
                <div className="max-h-48 overflow-y-auto space-y-0.5">
                  {projects.map((p: any) => (
                    <button
                      key={p.id}
                      onClick={() => handleSelectProject(p.id)}
                      className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors cursor-pointer flex items-center justify-between ${
                        p.id === context.activeProjectId
                          ? 'bg-accent/15 text-accent font-semibold'
                          : 'text-gray-300 hover:bg-surface'
                      }`}
                    >
                      <span className="truncate">{p.name}</span>
                      {p.environments && (
                        <span className="text-[10px] text-gray-500 font-mono">
                          {p.environments.length} env
                        </span>
                      )}
                    </button>
                  ))}
                </div>

                <div className="border-t border-border-subtle my-1" />

                {/* B5: "+ New Project" Option */}
                <button
                  onClick={handleNewProjectClick}
                  className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-accent hover:bg-accent/10 transition-colors cursor-pointer flex items-center gap-2 font-medium"
                >
                  <Plus size={13} />
                  <span>New Project</span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Dynamic Environment Switcher */}
          <div className="flex gap-1 mt-2.5 p-0.5 rounded-lg bg-background border border-border-subtle text-[11px] font-medium">
            {environments.map(env => (
              <button
                key={env}
                onClick={() => setActiveEnvironment(env)}
                className={`flex-1 py-1 rounded-md text-center transition-all cursor-pointer truncate px-1.5 ${
                  activeEnvironment.toLowerCase() === env.toLowerCase()
                    ? 'bg-surface-elevated text-accent font-semibold shadow'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {env}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Navigation Menu */}
      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 px-3 py-1">
          Menu
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium transition-all relative ${
                isActive
                  ? 'bg-accent/10 text-accent font-semibold'
                  : 'text-gray-400 hover:bg-surface hover:text-white'
              }`}
            >
              <Icon size={16} className={isActive ? 'text-accent' : 'text-gray-500'} />
              <span className="flex-1 text-left">{item.label}</span>
              {item.badge !== undefined && item.badge > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-accent/20 text-accent text-[10px] font-mono font-bold">
                  {item.badge}
                </span>
              )}
              {isActive && (
                <motion.div
                  layoutId="sidebar-active"
                  className="absolute left-0 w-1 h-5 bg-accent rounded-r-full"
                  initial={false}
                  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                />
              )}
            </button>
          );
        })}

        {/* Live Watch Status Section (C1-C6) */}
        <div className="pt-4 space-y-1">
          <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 px-3 py-1 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Eye size={12} className="text-accent" />
              <span>Watched Resources</span>
            </span>
            <span className="font-mono text-accent">
              {context.activeWatches.length > 0 ? context.activeWatches.length : activeServices.length}
            </span>
          </div>

          {/* If there are real active watch handles from backend */}
          {context.activeWatches.length > 0 ? (
            context.activeWatches.map(watch => (
              <div
                key={watch.watch_id}
                className="group flex items-center justify-between px-3 py-1.5 rounded-lg text-xs text-gray-300 hover:bg-surface transition-colors"
              >
                <div className="flex items-center gap-2 truncate">
                  <span
                    className={`w-1.5 h-1.5 rounded-full animate-pulse shrink-0 ${getStatusDot(watch.status)}`}
                  />
                  <span className="truncate font-mono text-[11px]">{watch.target}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[9px] px-1 py-0.2 rounded bg-surface border border-border-subtle text-gray-400 font-mono uppercase">
                    {watch.connector}
                  </span>
                  <button
                    onClick={() => context.stopWatch(watch.connector, watch.target, watch.watch_id)}
                    title="Stop watching"
                    className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-rose-400 transition-opacity cursor-pointer p-0.5"
                  >
                    <X size={11} />
                  </button>
                </div>
              </div>
            ))
          ) : activeServices.length > 0 ? (
            // If no active watches yet, show active environment services with 1-click watch
            activeServices.map((svc: any) => (
              <div
                key={svc.connector_id + (svc.resource_id || '')}
                className="group flex items-center justify-between px-3 py-1.5 rounded-lg text-xs text-gray-300 hover:bg-surface transition-colors"
              >
                <div className="flex items-center gap-2 truncate">
                  <span className="w-1.5 h-1.5 rounded-full bg-gray-500 shrink-0" />
                  <span className="truncate text-xs">{svc.display_name || svc.resource_id || svc.connector_id}</span>
                </div>
                <button
                  onClick={() => context.startWatch(svc.connector_id, svc.resource_id || 'default')}
                  title="Start continuous watch stream"
                  className="text-[10px] px-1.5 py-0.2 rounded bg-accent/10 hover:bg-accent/20 text-accent font-mono transition-colors cursor-pointer"
                >
                  Watch
                </button>
              </div>
            ))
          ) : (
            <div className="px-3 py-2 text-[11px] text-gray-500 italic">
              No services linked in this environment
            </div>
          )}
        </div>
      </nav>

      {/* Footer / Watcher Status */}
      <div className="p-4 border-t border-border-subtle bg-surface/30">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <div className="relative flex items-center justify-center">
              <span
                className={`w-2 h-2 rounded-full ${
                  watcherState === 'ALERTING'
                    ? 'bg-rose-500'
                    : watcherState === 'DEGRADED'
                    ? 'bg-amber-400'
                    : 'bg-accent'
                }`}
              />
              <span
                className={`absolute w-2 h-2 rounded-full pulse-radar ${
                  watcherState === 'ALERTING'
                    ? 'bg-rose-500'
                    : watcherState === 'DEGRADED'
                    ? 'bg-amber-400'
                    : 'bg-accent'
                }`}
              />
            </div>
            <span className="font-mono text-[11px] text-gray-300">Watcher Stream</span>
          </div>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-semibold font-mono ${
              watcherState === 'ALERTING'
                ? 'bg-rose-500/15 text-rose-400'
                : watcherState === 'DEGRADED'
                ? 'bg-amber-400/15 text-amber-400'
                : 'bg-accent/15 text-accent'
            }`}
          >
            {watcherState}
          </span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
