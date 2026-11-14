import { useEffect } from "react";
import { useStore } from "./state/store";
import { useProfile } from "./state/profile";
import Families from "./screens/Families/Families";
import FamilyCreation from "./screens/FamilyCreation/FamilyCreation";
import Sidebar from "./components/Sidebar";
import Onboarding from "./components/Onboarding";

export default function App() {
  const editing = useStore((s) => s.draft !== null);
  const { loaded, loadError, load, source, authOpen } = useProfile();
  useEffect(() => { void load(); }, [load]);
  if (!loaded) return <div className="boot">{loadError ?? "Loading…"}</div>;
  const showAuth = source === null || authOpen;
  return (
    <div className="shell">
      <Sidebar />
      <main className="main">{editing ? <FamilyCreation /> : <Families />}</main>
      {showAuth && <Onboarding />}
    </div>
  );
}
