import { useState } from 'react';
import { Home, FolderGit2, Blocks, Bell, Settings, ChevronDown, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  activeProject?: any;
  projects?: any[];
  onSelectProject?: (proj: any) => void;
  activeEnvironment: string;
  setActiveEnvironment: (env: string) => void;
  watcherState?: string;
  services?: any[];
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  activeProject,
  projects = [],
  onSelectProject,
  activeEnvironment,
  setActiveEnvironment,
  watcherState = 'ACTIVE',
  services = [],
}) => {
  const [showProjectsDropdown, setShowProjectsDropdown] = useState(false);

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Home },
    { id: 'projects', label: 'Projects', icon: FolderGit2 },
    { id: 'integrations', label: 'Integrations', icon: Blocks },
    { id: 'activity', label: 'Activity Log', icon: Bell },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-[#080B11] border-r border-border-subtle flex flex-col h-full select-none">
      {/* Brand Header */}
      <div className="p-5 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-accent to-emerald-400 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.3)]">
            <Sparkles size={18} className="text-gray-950" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-1.5">
              Lear <span className="text-[10px] px-1.5 py-0.2 bg-accent/20 text-accent rounded font-mono">v2.0</span>
            </h1>
            <p className="text-[10px] text-gray-500 font-mono">Infrastructure Intelligence</p>
          </div>
        </div>

        {/* Project Selector */}
        <div className="mt-5 relative">
          <button
            onClick={() => setShowProjectsDropdown(prev => !prev)}
            className="w-full p-2.5 rounded-xl bg-surface/60 hover:bg-surface border border-border-subtle flex items-center justify-between text-xs text-left cursor-pointer transition-colors"
          >
            <span className="text-gray-300 font-medium truncate">
              {activeProject?.name || 'Default Project'}
            </span>
            <ChevronDown size={14} className="text-gray-500 shrink-0" />
          </button>

          {showProjectsDropdown && projects.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 p-1 bg-surface-elevated border border-border-hover rounded-xl shadow-2xl z-30 space-y-0.5">
              {projects.map((p: any) => (
                <button
                  key={p.id}
                  onClick={() => {
                    if (onSelectProject) onSelectProject(p);
                    setShowProjectsDropdown(false);
                  }}
                  className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors cursor-pointer ${
                    p.id === activeProject?.id
                      ? 'bg-accent/15 text-accent font-semibold'
                      : 'text-gray-300 hover:bg-surface'
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>
          )}

          {/* Environment Switcher */}
          <div className="flex gap-1 mt-2.5 p-0.5 rounded-lg bg-background border border-border-subtle text-[11px] font-medium">
            {['Production', 'Staging'].map(env => (
              <button
                key={env}
                onClick={() => setActiveEnvironment(env)}
                className={`flex-1 py-1 rounded-md text-center transition-all cursor-pointer ${
                  activeEnvironment === env
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

      {/* Navigation */}
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
              <span>{item.label}</span>
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

        {/* Live Service Tree */}
        {services.length > 0 && (
          <div className="pt-4 space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 px-3 py-1 flex items-center justify-between">
              <span>Live Services</span>
              <span className="font-mono text-accent">{services.length}</span>
            </div>
            {services.map(svc => (
              <div
                key={svc.connector_id || svc.id}
                className="flex items-center justify-between px-3 py-1.5 rounded-lg text-xs text-gray-300 hover:bg-surface transition-colors"
              >
                <div className="flex items-center gap-2 truncate">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                  <span className="truncate">{svc.display_name || svc.name || svc.connector_id}</span>
                </div>
                <span className="text-[10px] text-gray-500 font-mono">LIVE</span>
              </div>
            ))}
          </div>
        )}
      </nav>

      {/* Footer / Watcher Status */}
      <div className="p-4 border-t border-border-subtle bg-surface/30">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <div className="relative flex items-center justify-center">
              <span className="w-2 h-2 rounded-full bg-accent" />
              <span className="absolute w-2 h-2 rounded-full bg-accent pulse-radar" />
            </div>
            <span className="font-mono text-[11px] text-gray-300">Watcher Stream</span>
          </div>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-accent font-semibold">
            {watcherState}
          </span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
