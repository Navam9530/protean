import { create } from "zustand";
import { api, ApiError } from "../api";

export interface ProfileData {
  source: "hostname" | "github" | null; // null until the first-run choice is made
  owner: string; // id prefix + display name
  avatarUrl: string | null;
}

export interface LoginStatus {
  state: "idle" | "pending" | "authorized" | "denied" | "expired" | "error";
  userCode?: string;
  verificationUri?: string;
  expiresIn?: number;
  error?: string | null;
  profile?: ProfileData | null;
}

interface Profile extends ProfileData {
  loaded: boolean;
  loadError: string | null;
  login: LoginStatus | null; // null = choice screen, otherwise device-flow progress
  /** Re-opens the sign-in popup (after the user previously skipped it). */
  authOpen: boolean;
  load: () => Promise<void>;
  openAuth: () => void;
  closeAuth: () => void;
  startLogin: () => Promise<void>;
  backToChoice: () => Promise<void>;
  continueWithHostname: () => Promise<void>;
  logout: () => Promise<void>;
}

const POLL_MS = 2000;
let timer: ReturnType<typeof setInterval> | undefined;
const stopPolling = () => { clearInterval(timer); timer = undefined; };

export const useProfile = create<Profile>()((set, get) => {
  const apply = (p: ProfileData) => set({ ...p, loaded: true, loadError: null });
  const fail = (e: unknown) => set({ login: { state: "error", error: (e as Error).message } });

  async function poll() {
    try {
      const s = await api<LoginStatus>("/auth/github/status");
      if (s.state === "pending") return set({ login: s });
      stopPolling();
      if (s.state === "authorized") {
        await get().load();
        set({ login: null, authOpen: false });
      } else set({ login: s });
    } catch (e) { stopPolling(); fail(e); }
  }

  return {
    source: null,
    owner: "",
    avatarUrl: null,
    loaded: false,
    loadError: null,
    login: null,
    authOpen: false,

    load: async () => {
      try { apply(await api<ProfileData>("/profile")); }
      catch (e) { set({ loadError: (e as Error).message }); }
    },
    openAuth: () => set({ authOpen: true, login: null }),
    closeAuth: () => { void get().backToChoice(); set({ authOpen: false }); },

    startLogin: async () => {
      // Open the tab now, inside the click, or the popup blocker stops it; point it at GitHub once we have the URL.
      const tab = window.open("about:blank", "_blank");
      try {
        const s = await api<LoginStatus>("/auth/github/device", "POST");
        set({ login: s });
        if (tab && s.verificationUri) { tab.opener = null; tab.location.href = s.verificationUri; }
        else tab?.close();
        stopPolling();
        timer = setInterval(poll, POLL_MS);
      } catch (e) {
        tab?.close();
        if (e instanceof ApiError && e.code === "already_signed_in") { await get().load(); set({ login: null, authOpen: false }); }
        else fail(e);
      }
    },
    backToChoice: async () => {
      stopPolling();
      const pending = get().login?.state === "pending";
      set({ login: null });
      if (pending) await api("/auth/github/cancel", "POST").catch(() => {});
    },
    logout: async () => {
      try { apply(await api<ProfileData>("/auth/github/logout", "POST")); }
      catch (e) { set({ loadError: (e as Error).message }); }
    },
    continueWithHostname: async () => {
      try { apply(await api<ProfileData>("/profile/skip-github", "POST")); set({ authOpen: false }); }
      catch (e) { fail(e); }
    },
  };
});
