import { Settings as SettingsIcon, Shield } from 'lucide-react';

export default function Settings({ onReconfigure }: { onReconfigure?: () => void }) {
  return (
    <div className="p-8">
      <div className="mb-8">
        <h2 className="text-xl font-semibold text-white mb-6">General Settings</h2>
        
        <div className="p-6 bg-gray-900/40 border border-gray-800 rounded-2xl mb-8 flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-lg text-white mb-1">Welcome Hub</h3>
            <p className="text-sm text-gray-500">Re-open the initial setup wizard to configure integrations</p>
          </div>
          <button onClick={onReconfigure} className="px-4 py-2 bg-accent text-black font-semibold rounded-lg hover:bg-[#2da36c] transition-colors">
            Open Setup
          </button>
        </div>

        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Settings</h1>
        <p className="text-gray-400">Manage your agent configuration and security preferences.</p>
      </div>

      <div className="max-w-3xl space-y-8">
        <section>
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <SettingsIcon size={20} className="text-accent" />
            Agent Modes
          </h2>
          <div className="p-6 rounded-2xl border border-gray-800 bg-gray-900/30 space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-medium text-white">Auto-Safe Mode</h3>
                <p className="text-gray-500 text-sm">Allow Prash to perform safe-tier actions automatically without asking.</p>
              </div>
              <div className="w-12 h-6 bg-accent rounded-full relative cursor-pointer">
                <div className="w-4 h-4 bg-background rounded-full absolute right-1 top-1"></div>
              </div>
            </div>
            
            <div className="w-full h-px bg-gray-800" />
            
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-medium text-white">Approval Tier</h3>
                <p className="text-gray-500 text-sm">Always ask before performing risky actions (e.g. deployments, rollbacks).</p>
              </div>
              <div className="w-12 h-6 bg-accent rounded-full relative cursor-pointer">
                <div className="w-4 h-4 bg-background rounded-full absolute right-1 top-1"></div>
              </div>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <Shield size={20} className="text-accent" />
            Security & Storage
          </h2>
          <div className="p-6 rounded-2xl border border-gray-800 bg-gray-900/30 space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-medium text-white">Local Execution Only</h3>
                <p className="text-gray-500 text-sm">Ensure credentials never leave the `.env` file on this machine.</p>
              </div>
              <div className="w-12 h-6 bg-accent rounded-full relative cursor-pointer">
                <div className="w-4 h-4 bg-background rounded-full absolute right-1 top-1"></div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
