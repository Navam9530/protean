import { useEffect } from "react";
import { useStore } from "./state/store";
import { useProfile } from "./state/profile";
import Families from "./screens/Families/Families";
import FamilyCreation from "./screens/FamilyCreation/FamilyCreation";
import Sidebar from "./components/Sidebar";
import Onboarding from "./components/Onboarding";
import MarketplaceDrawer from "./components/MarketplaceDrawer";
import { useMarketplace } from "./state/marketplace";

export default function App() {
  const editing = useStore((s) => s.draft !== null);
  const marketplaceOpen = useMarketplace((m) => m.target !== null);
  const { loaded, loadError, load, source, authOpen } = useProfile();
  const refresh = useStore((s) => s.refresh);
  useEffect(() => { void load(); void refresh(); }, [load, refresh]);
  if (!loaded) return <div className="boot">{loadError ?? "Loading…"}</div>;
  const showAuth = source === null || authOpen;
  return (
    <div className="shell">
      <Sidebar />
      <main className="main">{editing ? <FamilyCreation /> : <Families />}</main>
      {marketplaceOpen && <MarketplaceDrawer />}
      {showAuth && <Onboarding />}
    </div>
  );
}
